from flask import Blueprint as FlaskBlueprint
from flask import abort
from flask_restful import marshal_with, fields, reqparse

from pebbles.forms import LockForm
from pebbles.models import db, Lock
from pebbles.server import restful
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

locks = FlaskBlueprint('locks', __name__)

lock_fields = {
    'id': fields.String,
    'owner': fields.String,
    'acquired_at': fields.DateTime
}


class LockList(restful.Resource):

    @auth.login_required
    @requires_admin
    @marshal_with(lock_fields)
    def get(self):
        return Lock.query.all()


class LockView(restful.Resource):
    del_parser = reqparse.RequestParser()
    del_parser.add_argument('owner', type=str, location='args', default=None)

    @auth.login_required
    @requires_admin
    @marshal_with(lock_fields)
    def get(self, lock_id):
        q = Lock.query.filter_by(id=lock_id)
        lock = q.first()
        if not lock:
            abort(404)
        return lock

    @auth.login_required
    @requires_admin
    @marshal_with(lock_fields)
    def put(self, lock_id):
        form = LockForm()
        form.validate()
        lock = Lock(lock_id, form.owner.data)
        if lock.owner is None or lock.owner == '':
            abort(400)

        db.session.add(lock)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            abort(409)
        return lock

    @auth.login_required
    @requires_admin
    def delete(self, lock_id):
        args = self.del_parser.parse_args()
        q = Lock.query.filter_by(id=lock_id)
        if 'owner' in args and args['owner']:
            q = q.filter_by(owner=args.get('owner'))
        lock = q.first()
        if not lock:
            abort(404)
        db.session.delete(lock)
        db.session.commit()
