from flask import abort
from flask import Blueprint as FlaskBlueprint
from flask.ext.restful import marshal_with, fields, reqparse

from pouta_blueprints.server import restful
from pouta_blueprints.views.commons import auth
from pouta_blueprints.utils import requires_admin
from pouta_blueprints.models import db, User


quota = FlaskBlueprint('quota', __name__)

parser = reqparse.RequestParser()
types = ('absolute', 'relative')
parser.add_argument('type')
parser.add_argument('value', type=float)

quota_fields = {
    'id': fields.String,
    'credits_quota': fields.Float
}


def parse_arguments():
    try:
        args = parser.parse_args()
        if not args['type'] in types:
            raise RuntimeError("Invalid arguement type = %s" % args['type'])
        if not args['value'] > 0:
            raise RuntimeError("Invalid arguement value = %s" % args['value'])
    except:
        abort(422)
        return

    return args


@quota.route('/quota')
class Quota(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def put(self):
        args = parse_arguments()
        results = []

        for user in User.query.all():
            if args['type'] == 'relative':
                user.credits_quota = user.quota + args['value']
            elif args['type'] == 'absolute':
                user.credits_quota = args['value']
            results.append({'id': user.id, 'credits_quota': user.credits_quota})

        db.session.commit()
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

        if args['type'] == 'relative':
            user.credits_quota = user.credits_quota + args['value']
        elif args['type'] == 'absolute':
            user.credits_quota = args['value']

        db.session.commit()
        return {'id': user.id, 'credits_quota': user.credits_quota}
