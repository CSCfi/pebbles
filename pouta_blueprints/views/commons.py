from flask.ext.restful import fields
from flask.ext.httpauth import HTTPBasicAuth
from flask import g

from pouta_blueprints.models import SystemToken, User

user_fields = {
    'id': fields.String,
    'email': fields.String,
    'is_active': fields.Boolean,
    'is_admin': fields.Boolean,
    'is_deleted': fields.Boolean,
}

auth = HTTPBasicAuth()
auth.authenticate_header = lambda: "Authentication Required"


@auth.verify_password
def verify_password(userid_or_token, password):
    # first check for system tokens
    if SystemToken.verify(userid_or_token):
        g.user = User('system', is_admin=True)
        return True

    g.user = User.verify_auth_token(userid_or_token)
    if not g.user:
        g.user = User.query.filter_by(email=userid_or_token).first()
        if not g.user or not g.user.check_password(password):
            return False
    return True
