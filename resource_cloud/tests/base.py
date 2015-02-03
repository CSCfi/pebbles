from flask.ext.testing import TestCase

from resource_cloud.server import app, db


class BaseTestCase(TestCase):
    def create_app(self):
        app.config.from_object('resource_cloud.config.TestConfig')
        app.config['TESTING'] = True
        return app

    def setUp(self):
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
