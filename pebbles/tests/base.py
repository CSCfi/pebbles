from flask_testing import TestCase

from pebbles.config import TestConfig
from pebbles.models import db
from pebbles.server import app


class BaseTestCase(TestCase):
    def create_app(self):
        app.dynamic_config = TestConfig()
        app.config.from_object(app.dynamic_config)
        app.config['TESTING'] = True
        return app

    def setUp(self):
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
