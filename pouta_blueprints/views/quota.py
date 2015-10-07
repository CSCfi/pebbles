from flask import abort, g
from flask import Blueprint as FlaskBlueprint
from flask.ext.restful import marshal_with, fields, reqparse

from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin
from pouta_blueprints.models import db, User

quota = FlaskBlueprint('quota', __name__)

parser = reqparse.RequestParser()
quota_update_functions = {
    'absolute': lambda user, value: value,
    'relative': lambda user, value: user.credits_quota + value
}
parser.add_argument('type')
parser.add_argument('value', type=float)

quota_fields = {
    'id': fields.String,
    'credits_quota': fields.Float,
    'credits_spent': fields.Float,
}


def parse_arguments():
    try:
        args = parser.parse_args()
        if not args['type'] in quota_update_functions.keys():
            raise RuntimeError("Invalid arguement type = %s" % args['type'])
    except:
        abort(422)

    return args


def update_user_quota(user, update_type, value):
    try:
        fun = quota_update_functions[update_type]
        user.credits_quota = fun(user, value)
    except:
        abort(422)


@quota.route('/quota')
class Quota(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def put(self):
        args = parse_arguments()
        results = []

        for user in User.query.all():
            update_user_quota(user, args['type'], args['value'])
            results.append({'id': user.id, 'credits_quota': user.credits_quota})

        db.session.commit()
        return results

    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def get(self):
        results = []
        for user in User.query.all():
            results.append({
                'id': user.id,
                'credits_quota': user.credits_quota,
                'credits_spent': user.calculate_credits_spent()
            })

        return results


@quota.route('/quota/<string:user_id>')
class UserQuota(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def put(self, user_id):
        args = parse_arguments()

        user = User.query.filter_by(id=user_id).first()
        if not user:
            abort(404)

        update_user_quota(user, args['type'], args['value'])

        db.session.commit()
        return {'id': user.id, 'credits_quota': user.credits_quota}

    @auth.login_required
    @marshal_with(quota_fields)
    def get(self, user_id):
        user = User.query.filter_by(id=user_id).first()
        if not user:
            abort(404)
        if not g.user.is_admin and user_id != g.user.id:
            abort(403)

        return {'id': user.id, 'credits_quota': user.credits_quota, 'credits_spent': user.calculate_credits_spent()}
