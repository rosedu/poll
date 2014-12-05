import flask
from flask.ext.script import Manager
from flask.ext.sqlalchemy import SQLAlchemy

app = flask.Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('settings.py')
db = SQLAlchemy(app)


class Person(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    secretkey = db.Column(db.String)


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
