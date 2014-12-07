import string
import flask
from flask.ext.script import Manager
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.mail import Mail, Message

KEY_VOCABULARY = string.ascii_letters + string.digits

app = flask.Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('settings.py')
db = SQLAlchemy(app)
mail = Mail(app)


class Person(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    secretkey = db.Column(db.String, unique=True)

    memberships = db.relationship('PollMember', lazy='dynamic', backref='person')
    emails = db.relationship('Email', lazy='dynamic', backref='person')


class Email(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String, unique=True, nullable=False)
    person_id = db.Column(db.ForeignKey('person.id'))


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

    @property
    def votes_total(self):
        return self.votes_yee + self.votes_nay + self.votes_abs


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
            for email in user.emails:
                if email.address in app.config.get('ADMIN_EMAILS', []):
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


@app.route('/get_secretkey', methods=['GET', 'POST'])
def get_secretkey():
    if flask.request.method == 'POST':
        addr = flask.request.form['address']
        email = Email.query.filter_by(address=addr).first()
        if email:
            person = email.person
            if not person.secretkey:
                person.secretkey = random_key()
                db.session.commit()
            msg = Message("ROSEdu Poll login", recipients=[addr])
            msg.body = flask.render_template(
                'secretkey_email.txt',
                secretkey=person.secretkey,
            )
            mail.send(msg)
            flask.flash('Email sent')
            return flask.redirect(flask.url_for('home'))

        else:
            flask.flash('No such email in the database')


    return flask.render_template('get_secretkey.html')


@app.route('/')
def home():
    poll_query = Poll.query
    if not flask.g.is_admin:
        poll_query = poll_query.filter_by(isvisible=True)

    return flask.render_template(
        'home.html',
        poll_list=poll_query.all(),
        group_list=Group.query.all(),
        people_with_keys=Person.query.filter(Person.secretkey != None).count(),
    )


@app.route('/_crashme', methods=['GET', 'POST'])
def crashme():
    if flask.request.method == 'POST':
        raise RuntimeError("Crashing, as requested.")
    else:
        return '<form method="post"><button type="submit">err</button></form>'



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


@app.route('/poll/<slug>/open', methods=['POST'], defaults={'newstate': True})
@app.route('/poll/<slug>/close', methods=['POST'], defaults={'newstate': False})
def set_poll_open(slug, newstate):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    if not flask.g.is_admin:
        flask.abort(403)
    poll.isopen = newstate
    db.session.commit()
    flask.flash("poll %s is %s" % (slug, 'open' if newstate else 'closed'))
    return flask.redirect(flask.url_for('home'))


@app.route('/poll/<slug>/show', methods=['POST'], defaults={'newstate': True})
@app.route('/poll/<slug>/hide', methods=['POST'], defaults={'newstate': False})
def set_poll_visible(slug, newstate):
    poll = Poll.query.filter_by(slug=slug).first_or_404()
    if not flask.g.is_admin:
        flask.abort(403)
    poll.isvisible = newstate
    db.session.commit()
    flask.flash("poll %s is %s" % (slug, 'visible' if newstate else 'hidden'))
    return flask.redirect(flask.url_for('home'))


@app.route('/vote', methods=['POST'])
def vote():
    form = flask.request.form
    db.session.execute('BEGIN IMMEDIATE TRANSACTION')
    poll = Poll.query.filter_by(slug=form['poll']).first_or_404()
    member = poll.get_current_member()
    if not member:
        flask.abort(403)

    if member.voted:
        flask.flash("you've already voted")
        return flask.redirect(flask.url_for('home'))

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
    db.create_all()

    import yaml
    with open(spec_path) as f:
        data = yaml.load(f)

    email_map = {}
    person_map = {}

    for row in data['people']:
        person = get_or_create(Person, id=row['id'])
        assert person.id
        person_map[person.id] = person
        person.name = row['name']

        for addr in row['emails']:
            email_map[addr] = person

    current_email_map = dict((e.address, e) for e in Email.query)
    for to_remove in set(current_email_map) - set(email_map):
        db.session.delete(current_email_map[to_remove])

    for addr, person in email_map.items():
        email_map[addr] = email = get_or_create(Email, address=addr)
        email.person = person

    for slug, gdata in data['groups'].items():
        group = get_or_create(Group, slug=slug)
        group.name = gdata['name']
        print 'group', slug, group.name, '...'
        current_members = set(group.members)
        new_members = set(email_map[m].person for m in gdata['members'])

        for person in new_members - current_members:
            print 'adding:', person.name
            group.members.append(person)

        for person in current_members - new_members:
            print 'removing:', email
            group.members.remove(person)

    db.session.commit()
