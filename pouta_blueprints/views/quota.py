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
    'quota': fields.Float
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

        for user in User.query.all():
            user.credits = args['value']

        db.session.commit()
        return {'quota': args['value']}


@quota.route('/quota/<string:user_id>')
class UserQuota(restful.Resource):

    @auth.login_required
    @requires_admin
    @marshal_with(quota_fields)
    def put(self, user_id):
        args = parse_arguments()
        user = User.query.filter_by(id=user_id)
        user.credits = args['value']
        db.session.commit()
        return {'quota': args['value']}
