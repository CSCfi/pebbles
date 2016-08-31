from flask import url_for
from flask.ext.script import Manager, Server, Shell
from flask_migrate import MigrateCommand, Migrate
from werkzeug.contrib.profiler import ProfilerMiddleware
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
migrate = Migrate(app, models.db)


def _make_context():
    return dict(app=app, db=db, models=models)

manager.add_command("shell", Shell(make_context=_make_context, use_bpython=True))
manager.add_command("runserver", Server())
manager.add_command("db", MigrateCommand)


@manager.command
def test(failfast=False, pattern='test*.py', verbosity=1):
    """Runs the unit tests without coverage."""
    import unittest
    verb_level = int(verbosity)
    tests = unittest.TestLoader().discover('pouta_blueprints.tests', pattern=pattern)
    res = unittest.TextTestRunner(verbosity=verb_level, failfast=failfast).run(tests)
    if res.wasSuccessful():
        return 0
    else:
        return 1


@manager.command
def selenium(failfast=False, pattern='selenium_test*.py', verbosity=1):
    """Runs the selenium tests."""
    import unittest
    verb_level = int(verbosity)
    tests = unittest.TestLoader().discover('pouta_blueprints.tests', pattern=pattern)
    res = unittest.TextTestRunner(verbosity=verb_level, failfast=failfast).run(tests)
    if res.wasSuccessful():
        return 0
    else:
        return 1


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
def profile():
    app.config['PROFILE'] = True
    app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[50])
    app.run(debug=True)


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


@manager.command
def list_routes():

    try:
        from urllib.parse import unquote
    except ImportError:
        from urllib import unquote

    from terminaltables import AsciiTable

    route_data = [
        ['endpoint', 'methods', 'url']
    ]
    for rule in app.url_map.iter_rules():

        options = {}
        for arg in rule.arguments:
            options[arg] = "[{0}]".format(arg)

        methods = ','.join(rule.methods)
        url = url_for(rule.endpoint, **options)
        line = [unquote(x) for x in (rule.endpoint, methods, url)]
        route_data.append(line)

    print(AsciiTable(route_data).table)

if __name__ == '__main__':
    manager.run()
