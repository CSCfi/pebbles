from flask.ext.restful import fields
from flask.ext.httpauth import HTTPBasicAuth
from flask import g

from pouta_blueprints.models import db, SystemToken, User
from pouta_blueprints.server import app

user_fields = {
    'id': fields.String,
    'email': fields.String,
    'credits': fields.Float,
    'credits_spent': fields.Float,
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

    g.user = User.verify_auth_token(userid_or_token, app.config['SECRET_KEY'])
    if not g.user:
        g.user = User.query.filter_by(email=userid_or_token).first()
        if not g.user or not g.user.check_password(password):
            return False
    return True


def create_worker():
    return create_user('worker@pouta_blueprints', app.config['SECRET_KEY'], is_admin=True)


def create_user(email, password, is_admin=False):
    if User.query.filter_by(email=email).first():
        raise RuntimeError("user %s already exists" % email)
    user = User(email, password, is_admin=is_admin)
    db.session.add(user)
    db.session.commit()
    return user
