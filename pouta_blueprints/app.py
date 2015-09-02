import sys

from flask import Flask

from pouta_blueprints.models import db, Variable
from pouta_blueprints.config import BaseConfig, TestConfig

app = Flask(__name__)
test_run = set(['test', 'covtest']).intersection(set(sys.argv))

if test_run:
    app.dynamic_config = TestConfig()
else:
    app.dynamic_config = BaseConfig()

app.config.from_object(app.dynamic_config)

db.init_app(app)
with app.app_context():
    db.create_all()

    # Do not populate variables into DB when running tests, as these are
    # populated during the test case setup phase.
    if not test_run:
        Variable.sync_local_config_to_db(BaseConfig, app.dynamic_config)
