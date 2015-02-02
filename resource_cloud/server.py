from flask.ext import restful
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.httpauth import HTTPBasicAuth

import resource_cloud.app as appm

app = appm.get_app()

db = SQLAlchemy(app)

api = restful.Api(app)
auth = HTTPBasicAuth()
auth.authenticate_header = lambda: "Authentication Required"


import resource_cloud.views
