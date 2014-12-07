import string
import flask
from flask.ext.script import Manager
from flask.ext.sqlalchemy import SQLAlchemy

KEY_VOCABULARY = string.ascii_letters + string.digits

app = flask.Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('settings.py')
db = SQLAlchemy(app)


class Person(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    secretkey = db.Column(db.String, unique=True)

    memberships = db.relationship('PollMember', lazy='dynamic', backref='person')


group_member = db.Table(
    'group_member',
    db.Column('group_id', db.ForeignKey('group.id')),
    db.Column('person_id', db.ForeignKey('person.id')),
)


class Group(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    slug = db.Column(db.String, unique=True)

    members = db.relationship('Person', secondary=group_member)


class Poll(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    slug = db.Column(db.String, unique=True)
    isopen = db.Column(db.Boolean, default=True, nullable=False)
    isvisible = db.Column(db.Boolean, default=True, nullable=False)
    votes_yee = db.Column(db.Integer, default=0, nullable=False)
    votes_nay = db.Column(db.Integer, default=0, nullable=False)
    votes_abs = db.Column(db.Integer, default=0, nullable=False)

    members = db.relationship('PollMember', lazy='dynamic', backref='poll')

    def get_current_member(self):
        if flask.g.user:
            for member in flask.g.user.memberships:
                if member.poll == self:
                    return member

    def user_can_vote(self):
        member = self.get_current_member()
        return (member and not member.voted)

    def has_not_voted(self):
        return [m.person for m in self.members if not m.voted]


class PollMember(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.ForeignKey('person.id'))
    poll_id = db.Column(db.ForeignKey('poll.id'))
    voted = db.Column(db.Boolean, default=False, nullable=False)


@app.before_request
def authenticate_request():
    flask.g.user = None
    flask.g.is_admin = False
    secretkey = flask.session.get('secretkey')
    if secretkey:
        user = Person.query.filter_by(secretkey=secretkey).first()
        if user:
            flask.g.user = user
            if user.email in app.config.get('ADMIN_EMAILS', []):
                flask.g.is_admin = True


@app.route('/login/<secretkey>')
def login(secretkey):
    flask.session['secretkey'] = secretkey
    return flask.redirect(flask.url_for('home'))


@app.route('/logout')
def logout():
    flask.session.pop('secretkey', None)
    flask.flash('logged out')
    return flask.redirect(flask.url_for('home'))


@app.route('/')
def home():
    return flask.render_template(
        'home.html',
        poll_list=Poll.query.filter_by(isopen=True).all(),
        group_list=Group.query.all(),
    )


@app.route('/create_poll/<slug>', methods=['GET', 'POST'])
def create_poll(slug):
    group = Group.query.filter_by(slug=slug).first_or_404()
    if flask.request.method == 'POST':
        form = flask.request.form
        poll = Poll(name=form['name'], slug=form['slug'])
        db.session.add(poll)
        for p in group.members:
            poll.members.append(PollMember(person=p))
        db.session.commit()
        flask.flash('poll created')
        return flask.redirect(flask.url_for('home'))

    return flask.render_template('create_poll.html', group=group)


@app.route('/vote', methods=['POST'])
def vote():
    form = flask.request.form
    db.session.execute('BEGIN IMMEDIATE TRANSACTION')
    poll = Poll.query.filter_by(slug=form['poll']).first_or_404()
    member = poll.get_current_member()
    if not member:
        flask.abort(403)

    member.voted = True
    if form['vote'] == 'yee':
        poll.votes_yee += 1
    elif form['vote'] == 'nay':
        poll.votes_nay += 1
    elif form['vote'] == 'abs':
        poll.votes_abs += 1
    else:
        flask.abort(400)

    db.session.commit()
    flask.flash('vote saved')
    return flask.redirect(flask.url_for('home'))


manager = Manager(app)


@manager.command
def syncdb():
    db.create_all()


def random_key():
    import random
    rnd = random.SystemRandom()
    return ''.join(rnd.choice(KEY_VOCABULARY) for _ in xrange(12))


def get_or_create(model, **kv):
    row = model.query.filter_by(**kv).first()
    if row is None:
        row = model(**kv)
        db.session.add(row)
        db.session.flush()
    return row


@manager.command
def set_people(spec_path):
    import yaml
    with open(spec_path) as f:
        data = yaml.load(f)

    for row in data['people']:
        person = get_or_create(Person, email=row['email'])
        person.name = row['name']
        if person.secretkey is None:
            person.secretkey = random_key()

    for slug, gdata in data['groups'].items():
        group = get_or_create(Group, slug=slug)
        group.name = gdata['name']
        current_members = set(p.email for p in group.members)
        new_members = set(gdata['members'])

        for email in new_members - current_members:
            print 'adding:', email
            person = Person.query.filter_by(email=email).one()
            group.members.append(person)

        for email in current_members - new_members:
            print 'removing:', email
            person = Person.query.filter_by(email=email).one()
            group.members.remove(person)

    db.session.commit()
