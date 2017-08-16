from flask import url_for
from flask.ext.script import Manager, Server, Shell
from flask_migrate import MigrateCommand, Migrate
from werkzeug.contrib.profiler import ProfilerMiddleware
import getpass
from pebbles import models
from pebbles.config import BaseConfig
from pebbles.server import app
from pebbles.views.commons import create_user, create_worker
from pebbles.models import db
from pebbles.tests.fixtures import primary_test_setup

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
def configvars():
    """ Displays the currently used config vars in the system """
    config_vars = vars(BaseConfig)
    dynamic_config = BaseConfig()
    for var in config_vars:
        if not var.startswith('__') and var.isupper():
            print("%s : %s" % (var, dynamic_config[var]))


@manager.command
def test(failfast=False, pattern='test*.py', verbosity=1):
    """Runs the unit tests without coverage."""
    import unittest
    verb_level = int(verbosity)
    tests = unittest.TestLoader().discover('pebbles.tests', pattern=pattern)
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
    tests = unittest.TestLoader().discover('pebbles.tests', pattern=pattern)
    res = unittest.TextTestRunner(verbosity=verb_level, failfast=failfast).run(tests)
    if res.wasSuccessful():
        return 0
    else:
        return 1


@manager.command
def coverage():
    """Runs the unit tests with coverage."""
    import coverage
    import unittest
    cov = coverage.coverage(
        branch=True,
        include='pebbles/*'
    )
    cov.start()
    tests = unittest.TestLoader().discover('pebbles.tests')
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
def fixtures():
    """ Insert the same fixtures as in tests to make manually testing UI simpler.
    """
    primary_test_setup(type('', (), {})())


@manager.command
def createuser(email=None, password=None, admin=False):
    """Creates new user"""
    if not email:
        email = input("email: ")
    if not password:
        password = getpass.getpass("password: ")
    create_user(email, password=password, is_admin=admin)

@manager.command
def purgehost(name):
    """Purges a docker driver host by host name from NamespacedKeyValues so
    it can be safely deleted via OpenStack UI"""
    from pebbles.models import NamespacedKeyValue, db
    q_ = db.session.query(NamespacedKeyValue).filter(
        NamespacedKeyValue.key.contains(name))
    for obj in q_:
        db.session.delete(obj)
    db.session.commit()


@manager.command
def createworker():
    """Creates background worker"""
    create_worker()


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
