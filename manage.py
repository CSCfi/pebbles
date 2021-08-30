#!/usr/bin/env python
import logging
import warnings
import getpass
import random
import string

from flask import url_for
from flask_migrate import MigrateCommand, Migrate
from flask_script import Manager, Server, Shell
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.profiler import ProfilerMiddleware

import pebbles.tests.fixtures
from pebbles import models
from pebbles.config import BaseConfig
from pebbles.models import db, User
from pebbles.server import app
from pebbles.views.commons import create_user, create_worker, create_system_workspaces

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
def createuser(ext_id=None, password=None, admin=False):
    """Creates new user"""
    if not ext_id:
        ext_id = input("email: ")
    if not password:
        password = getpass.getpass("password: ")
    return create_user(ext_id=ext_id, password=password, is_admin=admin, email_id=ext_id)


@manager.command
def create_database():
    """Creates database"""
    db.create_all()


@manager.command
def initialize_system(ext_id=None, password=None):
    """Initializes the system using provided admin credentials"""
    create_database()
    admin_user = createuser(ext_id=ext_id, password=password, admin=True)
    create_worker()
    create_system_workspaces(admin_user)


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
        if not a and retry < 5:
            retry += 1
            no_of_accounts += 1
        else:
            print("User name: %s\t Password: %s" % (user, password))
    print("\n")


@manager.command
def createworker():
    """Creates an admin account for worker"""
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


@manager.command
def load_test_data(file):
    print()
    print('deprecated, use load_data instead')
    print()
    load_data(file)

@manager.command
def load_data(file, update=False):
    """
    Loads an annotated YAML file into database. Use -u/--update to update existing entries instead of skipping.
    """
    with open(file, 'r') as f:
        data = pebbles.tests.fixtures.load_yaml(f)
        for obj in data['data']:
                try:
                    db.session.add(obj)
                    db.session.commit()
                    logging.info('inserted %s %s' % (
                        type(obj).__name__,
                        getattr(obj, 'id', '')
                    ))
                except IntegrityError as e:
                    db.session.rollback()
                    if update:
                        db.session.merge(obj)
                        db.session.commit()
                        logging.info('updated %s %s' % (
                            type(obj).__name__,
                            getattr(obj, 'id', '')
                        ))
                    else:
                        logging.info('skipping %s %s, it already exists' % (
                            type(obj).__name__,
                            getattr(obj, 'id', '')
                        ))

@manager.command
def reset_worker_password():
    """Resets worker password to application secret key"""
    worker = User.query.filter_by(ext_id='worker@pebbles').first()
    worker.set_password(app.config['SECRET_KEY'])
    db.session.add(worker)
    db.session.commit()


if __name__ == '__main__':
    manager.run()
