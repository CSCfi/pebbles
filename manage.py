from flask import url_for
from flask_script import Manager, Server, Shell
from flask_migrate import MigrateCommand, Migrate
from werkzeug.contrib.profiler import ProfilerMiddleware
import getpass
from pebbles import models
from pebbles.config import BaseConfig
from pebbles.server import app
from pebbles.views.commons import create_user, create_worker
from pebbles.models import db, BlueprintTemplate, Group, Blueprint, Plugin
from pebbles.tests.fixtures import primary_test_setup


import json
import random
import string

import requests
import base64
import datetime

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
def createuser(eppn=None, password=None, admin=False):
    """Creates new user"""
    if not eppn:
        eppn = input("email: ")
    if not password:
        password = getpass.getpass("password: ")
    create_user(eppn=eppn, password=password, is_admin=admin, email_id=eppn)


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


methods = {
    'GET': requests.get,
    'POST': requests.post,
    'PUT': requests.put,
    'PATCH': requests.patch,
    'DELETE': requests.delete,
}


def get_auth_token(creds, headers=None):
    if not headers:
        headers = {}
    headers = {'Accept': 'text/plain'}
    response = make_request('POST', 'http://api:8889/api/v1/sessions', headers=headers, data=json.dumps(creds))
    try:
        token = '%s:' % response.json()['token']
        return base64.b64encode(bytes(token.encode('ascii'))).decode('utf-8')
    except KeyError:
        pass


def make_request(method='GET', path='/', headers=None, data=None):
    assert method in methods

    if not headers:
        headers = {}

    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'

    return methods[method](path, headers=headers, data=data)


def make_authenticated_request(method='GET', path='/', headers=None, data=None, creds=None, auth_token=None):
    assert method in methods

    if not headers:
        headers = {}

    headers = {'Content-type': 'application/json',
               'Accept': 'application/json',
               'token': auth_token,
               'Authorization': 'Basic %s' % auth_token}
    return methods[method](path, data=data, headers=headers, verify=False)


def make_authenticated_admin_request(method='GET', path='/', headers=None, data=None):
    ADMIN_TOKEN = get_auth_token({'eppn': 'admin_val@example.org', 'password': 'admin_user'})
    if ADMIN_TOKEN:
        return make_authenticated_request(method, path, headers, data, auth_token=ADMIN_TOKEN)


def launch_instance(user, password):
    auth_token = get_auth_token(creds={'eppn': user, 'password': password})
    if auth_token:
        response = make_authenticated_request(
            method='GET',
            path='http://api:8889/api/v1/blueprints',
            headers=None, auth_token=auth_token)
        for i in response.json():
            response = make_authenticated_request(
                method='POST',
                path='http://api:8889/api/v1/instances',
                data=json.dumps({'blueprint': i['id']}),
                headers=None, auth_token=auth_token)


def group_join_codes():
    group_join_code = []
    group = Group.query.all()
    for q in group:
        group_join_code.append(q.join_code)
    return group_join_code


def create_blueprint(user, password, group_name, blueprint_template_id):
    blueprint_prefix = "demoblueprint"
    name = blueprint_prefix + "_" + ''.join(random.choice(string.ascii_lowercase +
                                           string.digits) for _ in range(3))
    group = Group.query.filter_by(name=group_name).first()
    data = {'name': name, 'config': {'foo': 'bar'}, 'is_enabled': True, 'template_id': blueprint_template_id, 'group_id': group.id}
    auth_token = get_auth_token(creds={'eppn': user, 'password': password})
    if auth_token:
        make_authenticated_request(method='POST', path='http://api:8889/api/v1/blueprints', headers=None, data=json.dumps(data), auth_token=auth_token)
        blueprint = Blueprint.query.filter_by(name=name).first()
        if blueprint:
            make_authenticated_request(
                method='PUT',
                path='http://api:8889/api/v1/blueprints/%s' % blueprint.id, headers=None,
                data=json.dumps(data), auth_token=auth_token)
            print("BLUEPRINT: %s " % name)


def create_blueprint_template(user, password, no_of_blueprint_templates=1):
    no_of_blueprint_templates = 1
    blueprint_template_prefix = "demoblueprinttemplate"
    template_driver = Plugin.query.filter_by(name='DummyDriver').first()
    for i in range(no_of_blueprint_templates):
        name = blueprint_template_prefix + "_" + ''.join(random.choice(string.ascii_lowercase +
                                           string.digits) for _ in range(3))
        data = {'name': name, 'config': {"maximum_lifetime": '3m'}, 'is_enabled': True, 'plugin': template_driver.id, 'allowed_attrs': {'allowed_attrs': ['maximum_lifetime']}}
        make_authenticated_admin_request(
            method='POST',
            path='http://api:8889/api/v1/blueprint_templates',
            data=json.dumps(data)
        )
        blueprint_template = BlueprintTemplate.query.filter_by(name=name).first()
        if blueprint_template:
            make_authenticated_admin_request(
                method='PUT',
                path='http://api:8889/api/v1/blueprint_templates/%s' % blueprint_template.id,
                data=json.dumps(data))
            print("BLUEPRINT TEMPLATE: %s" % (name))
            return blueprint_template.id


def create_group(user, password):
    group_prefix = "demogroup"
    name = group_prefix + "_" + ''.join(random.choice(string.ascii_lowercase +
                                           string.digits) for _ in range(3))
    data = {'name': name, 'description': 'Group Details', 'user_config': {}}
    auth_token = get_auth_token(creds={'eppn': user, 'password': password})
    if auth_token:
        make_authenticated_request(method='POST', path='http://api:8889/api/v1/groups', headers=None, data=json.dumps(data), auth_token=auth_token)
        print("GROUP: %s" % (name))
        return name


def create_accounts_func(domain_name=None, user_prefix=None, no_of_actual_accounts=None, make_accounts_group_owner=None, group_join_code=None, blueprint_template_id=None):
    for i in range(no_of_actual_accounts):
        retry = 1
        # eg: demo_user_Rgv4@example.com
        user = user_prefix + "_" + ''.join(random.choice(string.ascii_lowercase +
                                           string.digits) for _ in range(3)) + "@" + domain_name
        password = ''.join(random.choice(string.ascii_uppercase +
                           string.ascii_lowercase + string.digits) for _ in range(8))
        user_create = create_user(eppn=user, password=password, is_admin=False, email_id=user)
        if not user_create:
            continue
        if make_accounts_group_owner:
            response = make_authenticated_admin_request(
                method='PUT',
                path='http://api:8889/api/v1/users/%s/user_group_owner' % user_create.id,
                data=json.dumps({'make_group_owner': True})
            )
            # create a group
            if response.status_code == 200:
                group_name = create_group(user, password)
                if group_name and blueprint_template_id:
                    create_blueprint(user, password, group_name, blueprint_template_id)
                else:
                    print("cannot create blueprint")
            else:
                print("could not make group owner %s" % user)

        elif not make_accounts_group_owner:
            auth_token = get_auth_token(creds={'eppn': user, 'password': password})
            if auth_token:
                response = make_authenticated_request(
                    method='PUT',
                    path='http://api:8889/api/v1/groups/group_join/%s' % random.choice(group_join_code[1:]),
                    headers=None,
                    auth_token=auth_token)

        launch_instance(user, password)

        if (not user_create and retry < 5):
            retry += 1
            no_of_actual_accounts += 1
        else:
            print("USER: %s\t PASSWORD: %s" % (user, password))


@manager.command
def create_bulk_db(admin=False):
    print("\n")
    group_join_code = []
    """Creates one admin user. Admin user will create one blueprint template if chosen.
       Creates new demo group owners and users. Each group owner will create one group,
       one blueprint(if template was created by admin) and launch an instance. Each regular
       user will join a random group and launch an instance if possible."""
    no_of_group_owner_accounts = int(input("Enter the number of group owner accounts needed: "))
    no_of_regular_accounts = int(input("Enter the number of regualar accounts needed: "))
    start_time = datetime.datetime.now()
    blueprint_creation = int(input("Do you want to create blueprints enter(1 or 0): "))
    create_user('admin_val@example.org', 'admin_user', is_admin=True)
    if blueprint_creation:
        blueprint_template_id = create_blueprint_template('admin_val@example.org', 'admin_user', 1)
    else:
        blueprint_template_id = None
    domain_name = "example.org"
    user_prefix_owner = "demogroupowneruser"
    user_prefix_regular = "demoregularuser"
    create_accounts_func(domain_name=domain_name, user_prefix=user_prefix_owner, no_of_actual_accounts=no_of_group_owner_accounts, make_accounts_group_owner=True, group_join_code=None, blueprint_template_id=blueprint_template_id)
    group_join_code = group_join_codes()
    create_accounts_func(domain_name=domain_name, user_prefix=user_prefix_regular, no_of_actual_accounts=no_of_regular_accounts, make_accounts_group_owner=False, group_join_code=group_join_code, blueprint_template_id=None)
    end_time = datetime.datetime.now()
    print("************************")
    print("Time when started is %s" % start_time)
    print("Time now is %s" % end_time)
    print("Total Time taken %s\n" % (end_time - start_time))


if __name__ == '__main__':
    manager.run()
