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
    isopen = db.Column(db.Boolean, default=False, nullable=False)
    isvisible = db.Column(db.Boolean, default=True, nullable=False)
    votes_yee = db.Column(db.Integer, default=0, nullable=False)
    votes_nay = db.Column(db.Integer, default=0, nullable=False)
    votes_abs = db.Column(db.Integer, default=0, nullable=False)


class PollMember(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.ForeignKey('person.id'))
    poll_id = db.Column(db.ForeignKey('poll.id'))
    voted = db.Column(db.Boolean, default=False, nullable=False)


@app.route('/')
def home():
    return 'hi'


manager = Manager(app)


@manager.command
def syncdb():
    db.create_all()


def random_key():
    import random
    rnd = random.SystemRandom()
    return ''.join(rnd.choice(KEY_VOCABULARY) for _ in xrange(12))


@manager.command
def create_person(name, email):
    person = Person(name=name, email=email, secretkey=random_key())
    db.session.add(person)
    db.session.commit()


def get_or_create(model, **kv):
    row = model.query.filter_by(**kv).first()
    if row is None:
        row = model(**kv)
        db.session.add(row)
        db.session.flush()
    return row


@manager.command
def set_group(spec_path):
    import yaml
    with open(spec_path) as f:
        data = yaml.load(f)

    group = get_or_create(Group, slug=data['slug'])
    current_members = set(p.email for p in group.members)
    new_members = set(data['members'])

    for email in new_members - current_members:
        print 'adding:', email
        person = Person.query.filter_by(email=email).one()
        group.members.append(person)

    for email in current_members - new_members:
        print 'removing:', email
        person = Person.query.filter_by(email=email).one()
        group.members.remove(person)

    db.session.commit()
