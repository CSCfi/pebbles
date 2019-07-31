from flask_restful import marshal_with, fields, reqparse
from flask import abort
from flask import Blueprint as FlaskBlueprint

from pebbles.models import NotebookEnability, db
from pebbles.views.commons import auth
from pebbles.server import restful
from pebbles.utils import requires_admin

notebooks_enability = FlaskBlueprint('notebooks_enability', __name__)

notebook_enability_fields = {
    'id': fields.String,
    'is_notebooks_enable': fields.Boolean,
}


class NotebookEnabilityList(restful.Resource):

    @auth.login_required
    @marshal_with(notebook_enability_fields)
    def get(self):
        results = []
        for item in NotebookEnability.query.all():
            results.append(item)

        return results


class NotebookEnabilityView(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('make_disable', type=bool, default=False)
    parser.add_argument('make_enable', type=bool, default=False)

    @auth.login_required
    @requires_admin
    def patch(self, notebooks_enability_id):
        args = self.parser.parse_args()
        notebooks_en = NotebookEnability.query.filter_by(id=notebooks_enability_id).first()
        if not notebooks_en:
            abort(404)

        if args.get('make_disable'):
            notebooks_en.is_notebooks_enable = False
            db.session.commit()

        if args.get('make_enable'):
            notebooks_en.is_notebooks_enable = True
            db.session.commit()
