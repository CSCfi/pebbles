import yaml

from flask import Flask
from flask.ext import restful
from flask.ext.restful import reqparse, Api
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.httpauth import HTTPBasicAuth

app = Flask(__name__)
app.config.from_object('resource_cloud.config')

db = SQLAlchemy(app)
api = restful.Api(app)
auth = HTTPBasicAuth()


import resource_cloud.views
