from flask.ext.script import Manager, Server, Shell
import getpass
from pouta_blueprints import models
from pouta_blueprints.server import app
from pouta_blueprints.views.commons import create_user, create_worker
from pouta_blueprints.models import db, Variable
from pouta_blueprints.config import BaseConfig

# 2to3 fix for input
try:
    input = raw_input
except NameError:
    pass

manager = Manager(app)


def _make_context():
    return dict(app=app, db=db, models=models)

manager.add_command("shell", Shell(make_context=_make_context, use_bpython=True))
manager.add_command("runserver", Server())


@manager.command
def test(failfast=None):
    """Runs the unit tests without coverage."""
    import unittest
    tests = unittest.TestLoader().discover('pouta_blueprints.tests')
    unittest.TextTestRunner(verbosity=2, failfast=failfast).run(tests)


@manager.command
def cov():
    """Runs the unit tests with coverage."""
    import coverage
    import unittest
    cov = coverage.coverage(
        branch=True,
        include='pouta_blueprints/*'
    )
    cov.start()
    tests = unittest.TestLoader().discover('pouta_blueprints.tests')
    unittest.TextTestRunner(verbosity=2).run(tests)
    cov.stop()
    cov.save()
    print('Coverage Summary:')
    cov.report()


@manager.command
def createuser(email=None, password=None, admin=False):
    """Creates new user"""
    if not email:
        email = input("email: ")
    if not password:
        password = getpass.getpass("password: ")
    create_user(email, password=password, is_admin=admin)


@manager.command
def createworker():
    """Creates background worker"""
    create_worker()


@manager.command
def syncconf():
    """Synchronizes configuration from filesystem to database"""
    Variable.sync_local_config_to_db(BaseConfig, BaseConfig(), force_sync=True)


if __name__ == '__main__':
    manager.run()
