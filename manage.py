from flask import url_for
from flask_script import Manager, Server, Shell
from flask_migrate import MigrateCommand, Migrate
from werkzeug.middleware.profiler import ProfilerMiddleware
import getpass
from six.moves import input
from pebbles import models
from pebbles.config import BaseConfig
from pebbles.server import app
from pebbles.views import commons
from pebbles.views.commons import create_user, create_worker, create_system_workspaces
from pebbles.models import db
from pebbles.tests.fixtures import primary_test_setup

import random
import string

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
def createuser(eppn=None, password=None, admin=False):
    """Creates new user"""
    if not eppn:
        eppn = input("email: ")
    if not password:
        password = getpass.getpass("password: ")
    return create_user(eppn=eppn, password=password, is_admin=admin, email_id=eppn)

@manager.command
def initialize_system(eppn=None, password=None):
    """Initializes the system using provided admin credentials"""
    db.create_all()
    admin_user = createuser(eppn=eppn, password=password, admin=True)
    create_worker()
    create_system_workspaces(admin_user)
    commons.register_plugins()

@manager.command
def register_plugins(plugin_name=None):
    """Registers all known plugins"""
    commons.register_plugins()

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
def createuser_bulk(user_prefix=None, domain_name=None, admin=False):
    """Creates new demo users"""
    no_of_accounts = int(input("Enter the number of demo user accounts needed: "))
    print("\nFind the demo user accounts and their respective passwords.\
             \nPLEASE COPY THESE BEFORE CLOSING THE WINDOW \n")
    if not domain_name:
        domain_name = "example.org"
    if not user_prefix:
        user_prefix = "demouser"
    for i in range(no_of_accounts):
        retry = 1
        # eg: demo_user_Rgv4@example.com
        user = user_prefix + "_" + ''.join(random.choice(string.ascii_lowercase +
                                           string.digits) for _ in range(3)) + "@" + domain_name
        password = ''.join(random.choice(string.ascii_uppercase +
                           string.ascii_lowercase + string.digits) for _ in range(8))
        a = create_user(user, password, is_admin=admin)
        if (not a and retry < 5):
            retry += 1
            no_of_accounts += 1
        else:
            print("User name: %s\t Password: %s" % (user, password))
    print("\n")


@manager.command
def createworker():
    """Creates background worker"""
    create_worker()


@manager.command
def list_routes():

    # noinspection PyCompatibility
    from urllib.parse import unquote

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

    for line in route_data:
        print('%-40s %-40s %-100s' % (line[0], line[1], line[2]))


if __name__ == '__main__':
    manager.run()
