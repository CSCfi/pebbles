#!/usr/bin/env python
import getpass
import logging
import os
import random
import string
import sys
import time
from typing import List

import click
import yaml
from flask.cli import FlaskGroup
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

import pebbles.models
import pebbles.views.commons
from pebbles import models
from pebbles.app import create_app, db
from pebbles.config import RuntimeConfig
from pebbles.models import User, Application, ApplicationTemplate
from pebbles.utils import create_password

# ensure UNITTEST environment before importing app
if {'test', 'coverage'}.intersection(set(sys.argv)):
    os.environ['UNITTEST'] = '1'
# set FLASK_APP to point to our app
os.environ['FLASK_APP'] = 'pebbles.app:create_app()'

app = create_app()
cli = FlaskGroup()


@cli.command('configvars')
def configvars():
    """ Displays the currently used config vars in the system """
    config_vars = vars(RuntimeConfig)
    dynamic_config = RuntimeConfig()
    for var in config_vars:
        if not var.startswith('__') and var.isupper():
            print("%s : %s" % (var, dynamic_config[var]))


@cli.command('test')
def test(failfast=False, pattern='test*.py', verbosity=1):
    """Runs the unit tests without coverage."""
    import pytest
    exit(pytest.main('tests'.split()))


@cli.command('createuser')
@click.option('-e', 'ext_id', help='ext_id')
@click.option('-p', 'password', help='password')
@click.option('-a', 'admin', default=False, help='admin user (default False)')
@click.option('-l', 'lifetime_in_days', default=0, help='lifetime in days (default no limit)')
def createuser(ext_id=None, password=None, admin=False, lifetime_in_days=0):
    """Creates new user"""
    if not ext_id:
        ext_id = input("email: ")
    if not password:
        password = getpass.getpass("password: ")
    expiry_ts = time.time() + 3600 * 24 * lifetime_in_days if lifetime_in_days else None

    return pebbles.views.commons.create_user(ext_id=ext_id, password=password, is_admin=admin, email_id=ext_id,
                                             expiry_ts=expiry_ts)


@cli.command('create_database')
def create_database():
    """Creates database"""
    db.create_all()


@cli.command('initialize_system')
@click.option('-e', 'ext_id')
@click.option('-p', 'password')
def initialize_system(ext_id=None, password=None):
    """Initializes the system using provided admin credentials"""
    db.create_all()
    admin_user = pebbles.views.commons.create_user(ext_id=ext_id, password=password, is_admin=True)
    pebbles.views.commons.create_worker()
    pebbles.views.commons.create_system_workspaces(admin_user)


@cli.command('update_password')
@click.option('--ext-id', required=True, help='ext_id of the user')
@click.option('--password', required=False, help='new password')
def update_password(ext_id, password=None):
    """Update password for an existing user."""
    stmt = select(User).where(User.ext_id == ext_id)
    user = db.session.execute(stmt).scalar_one_or_none()

    if not user:
        print(f"User '{ext_id}' does not exist")
        sys.exit(1)

    if not password:
        password = getpass.getpass("Password: ")
        password_repeat = getpass.getpass("Repeat password for confirmation: ")
        if password != password_repeat:
            print("Passwords do not match.")
            sys.exit(1)

    user.set_password(password)
    db.session.commit()
    print(f"Password updated for user '{ext_id}'")


@cli.command('createuser_bulk')
@click.option('-u', 'user_prefix', help='account prefix (default demouser)')
@click.option('-d', 'domain_name', help='account domain name (default example.org)')
@click.option('-c', 'count', default=0, help='count')
@click.option('-l', 'lifetime_in_days', default=0, help='lifetime in days (default no limit)')
def createuser_bulk(user_prefix=None, domain_name=None, count=0, lifetime_in_days=0):
    """Creates new demo users"""
    if not count:
        count = int(input('Enter the number of demo user accounts needed: '))
    print()
    print('Find the demo user accounts and their respective passwords below.')
    if lifetime_in_days:
        print('The accounts expire after %d day(s).' % lifetime_in_days)
    print('Remember to copy these before you close the window.')
    print()

    if not domain_name:
        domain_name = 'example.org'
    if not user_prefix:
        user_prefix = 'demouser'

    expiry_ts = time.time() + 3600 * 24 * lifetime_in_days if lifetime_in_days else None

    for i in range(count):
        for retry in range(5):
            # eg: demo_user_Rgv4@example.com
            ext_id = user_prefix + "_" + ''.join(
                random.choice(string.ascii_lowercase + string.digits) for _ in range(3)) + "@" + domain_name

            password = create_password(8)

            a = pebbles.views.commons.create_user(ext_id, password, expiry_ts=expiry_ts)
            if a:
                print('Username: %s\t Password: %s' % (ext_id, password))
                break

    print("\n")


@cli.command('createuser_list_samepwd')
@click.argument('ext_id_string')
@click.option('-p', 'password', help='shared password')
@click.option('-l', 'lifetime_in_days', default=0, help='lifetime in days (default no limit)')
def createuser_list_samepwd(ext_id_string=None, password=None, lifetime_in_days=0):
    """Creates new users with shared password. Takes a comma separated string of ext_ids as an argument"""
    if not ext_id_string:
        ext_id_string = input("TO CREATE USER\n Enter comma separated list of ext_ids without space: \
                             \neg: qua00@hui,qua01@hui,qua02@hui \n")
    if not password:
        password = getpass.getpass("password: ")

    expiry_ts = time.time() + 3600 * 24 * lifetime_in_days if lifetime_in_days else None

    ext_id_list = [x for x in ext_id_string.split(',')]
    print("List of users to create %s " % ext_id_list)
    for ext_id in ext_id_list:
        pebbles.views.commons.create_user(ext_id, password, expiry_ts=expiry_ts)


@cli.command('deleteuser_bulk')
@click.argument('ext_id_string')
def deleteuser_bulk(ext_id_string=None):
    """Deletes a list of users, takes comma separated list of ext_ids as an argument"""
    from pebbles.models import User
    if not ext_id_string:
        ext_id_string = input("TO DELETE USER\n Enter comma separated list of ext_ids without space: \
                             \neg: qua00@hui,qua01@hui,qua02@hui \n")

    ext_id_list = [x for x in ext_id_string.split(',')]
    print("List of users to delete %s " % ext_id_list)
    for ext_id in ext_id_list:
        user = User.query.filter_by(ext_id=ext_id).first()
        if user:
            user.delete()
        else:
            print("User %s not found " % (ext_id))
    db.session.commit()


@cli.command('createworker')
def createworker():
    """Creates an admin account for worker"""
    pebbles.views.commons.create_worker()


@cli.command('load_data')
@click.argument('file')
@click.option('-u', 'update', is_flag=True, help='update existing entries')
def load_data(file, update=False):
    """
    Loads an annotated YAML file into database. Use -u/--update to update existing entries instead of skipping.
    """
    with open(file, 'r') as f:
        data = models.load_yaml(f)
        for obj in data['data']:
            try:
                db.session.add(obj)
                db.session.commit()
                logging.info('inserted %s %s' % (
                    type(obj).__name__,
                    getattr(obj, 'id', '')
                ))
            except IntegrityError:
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


@cli.command('reset_worker_password')
def reset_worker_password():
    """Resets worker password to application secret key"""
    worker = User.query.filter_by(ext_id='worker@pebbles').first()
    worker.set_password(app.config['SECRET_KEY'])
    db.session.add(worker)
    db.session.commit()


@cli.command('check_data')
@click.argument('datadir')
def check_data(datadir):
    """
    Checks given applications and templates YAML data files in given directory for consistency.
    """
    applications_file = datadir + '/applications.yaml'
    templates_file = datadir + '/application_templates.yaml'
    application_data: List[Application] = models.load_yaml(open(applications_file, 'r')).get('data')
    template_data: List[ApplicationTemplate] = models.load_yaml(open(templates_file, 'r')).get('data')

    # check for duplicate ids
    ids: List[string] = []
    for application in application_data:
        if application.id in ids:
            logging.error('ERROR: duplicate application id "%s"' % application.id)
            exit(1)
        ids.append(application.id)
    ids = []
    for template in template_data:
        if template.id in ids:
            logging.error('ERROR: duplicate template id "%s"' % template.id)
            exit(1)
        ids.append(template.id)

    # check application consistency with template data
    for application in application_data:
        # find the template this application refers to
        template = next((t for t in template_data if t.id == application.template_id), None)

        # template has to exist
        if not template:
            logging.error('ERROR: application "%s" refers to unknown template' % application.name)
            exit(1)

        # check that we have copied the attributes from the template correctly
        if yaml.safe_dump(application.base_config) != yaml.safe_dump(template.base_config):
            logging.error('ERROR: application "%s" base_config differs from template' % application.name)
            exit(1)
        if application.application_type != template.application_type:
            logging.error('ERROR: application "%s" application_type differs from template' % application.name)
            exit(1)
        if yaml.safe_dump(application.attribute_limits) != yaml.safe_dump(template.attribute_limits):
            logging.error('ERROR: application "%s" attribute_limits differs from template' % application.name)
            exit(1)

    logging.info('checked %d applications against %d templates, no errors found', len(application_data),
                 len(template_data))


@cli.command('list_application_images')
def list_application_images():
    """
    Lists images used by active applications
    """
    applications = models.list_active_applications()
    images = []
    # collect the images per application
    for a in applications:
        image = a.config.get('image_url', '')
        if image:
            if image not in images:
                images.append(image)
        else:
            image = a.base_config.get('image', '')
            if image not in images:
                images.append(image)

    # filter out strings that are obviously wrong (image_url in config can basically have anything)
    print('\n'.join([image for image in sorted(images) if '/' in image and ' ' not in image]))


@cli.command('replace_application_image')
@click.argument('old_image')
@click.argument('new_image')
@click.option('-d', 'dry_run', is_flag=True, help='dry-run, do not commit changes')
def replace_application_image(old_image, new_image, dry_run=False):
    """
    Changes application image in all active applications in both base_config and config
    """
    if dry_run:
        print('\n*** Dry run: no changes made ***\n')

    print(f'Changing image reference {old_image} to {new_image} in all active applications')
    applications = models.list_active_applications()
    print(f'Found total {len(applications)} active applications in active workspaces')

    changed_applications = set()
    # collect the images per application
    for a in applications:
        if a.replace_application_image(old_image, new_image):
            changed_applications.add(a)

    if changed_applications:
        print('Updated %d applications:' % len(changed_applications))
        for a in sorted(changed_applications, key=lambda a: a.id):
            print('  %32s %s' % (a.id, a.name))
        if dry_run:
            print('\n*** Dry run: no changes made ***\n')
        else:
            db.session.commit()
            print('Changes commited')
    else:
        print('No changes')


if __name__ == '__main__':
    cli()
