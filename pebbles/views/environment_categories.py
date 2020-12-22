import flask_restful as restful
from flask_restful import fields
from flask_restful import marshal_with

from pebbles.views.commons import auth

environment_category_fields = {
    'name': fields.String,
    'labels': fields.List(fields.String)
}


class EnvironmentCategoryList(restful.Resource):
    @auth.login_required
    @marshal_with(environment_category_fields)
    def get(self):
        categories = [
            dict(
                name='Machine Learning',
                labels=['machine learning', 'tensorflow', 'keras']
            ),
            dict(
                name='Data Analytics',
                labels=['analytics', 'statistics']
            ),
        ]
        return categories
