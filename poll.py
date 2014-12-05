import flask
from flask.ext.script import Manager
from flask.ext.sqlalchemy import SQLAlchemy

app = flask.Flask(__name__)
db = SQLAlchemy(app)


@app.route('/')
def home():
    return 'hi'


manager = Manager(app)
