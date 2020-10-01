import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, g
from flask_restful import marshal_with, fields, reqparse

from pebbles.models import db, User
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

quota = FlaskBlueprint('quota', __name__)

parser = reqparse.RequestParser()

workspace_quota_update_functions = {
    'absolute': lambda user, value: value,
    'relative': lambda user, value: user.workspace_quota + value
}
environment_quota_update_functions = {
    'absolute': lambda user, value: value,
    'relative': lambda user, value: user.environment_quota + value
}

parser.add_argument('type')
parser.add_argument('value', type=float)
parser.add_argument('credits_type', type=str)

quota_fields = {
    'id': fields.String,
    'environment_quota': fields.Integer,
    'workspace_quota': fields.Integer,
}


def parse_arguments():
    try:
        args = parser.parse_args()
        if not args['type'] in ('absolute', 'relative'):
            raise RuntimeError("Invalid arguement type = %s" % args['type'])
        return args
    except:
        abort(422)


def update_user_quota(user, update_type, value, credits_type):
    try:
        if credits_type == 'workspace_quota_value' and user.is_workspace_owner:
            if not user.workspace_quota:
                user.workspace_quota = 0  # can also add real time value from db here
            fun = workspace_quota_update_functions[update_type]
            user.workspace_quota = fun(user, value)
        elif credits_type == 'environment_quota_value' and user.is_workspace_owner:
            if not user.environment_quota:
                user.environment_quota = 0
            fun = environment_quota_update_functions[update_type]
            user.environment_quota = fun(user, value)

    except:
        abort(422)


class Quota(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def get(self):
        results = []
        for user in User.query.all():
            results.append(
                dict(id=user.id, environment_quota=user.environment_quota, workspace_quota=user.workspace_quota)
            )

        return results


class UserQuota(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def put(self, user_id):
        args = parse_arguments()
        user = User.query.filter_by(id=user_id).first()
        if not user:
            abort(404)

        update_user_quota(user, args['type'], args['value'], args['credits_type'])

        db.session.commit()
        return dict(id=user.id, environment_quota=user.environment_quota, workspace_quota=user.workspace_quota)

    @auth.login_required
    @marshal_with(quota_fields)
    def get(self, user_id):
        user = User.query.filter_by(id=user_id).first()
        if not user:
            abort(404)
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)

        return dict(id=user.id, environment_quota=user.environment_quota, workspace_quota=user.workspace_quota)
