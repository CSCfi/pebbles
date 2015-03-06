from flask.ext import restful
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.httpauth import HTTPBasicAuth

import pouta_blueprints.app as appm

app = appm.get_app()

db = SQLAlchemy(app)

api = restful.Api(app)
auth = HTTPBasicAuth()
auth.authenticate_header = lambda: "Authentication Required"

import pouta_blueprints.views
pouta_blueprints.views.setup_resource_urls(api_service=api)
