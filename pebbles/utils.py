import base64
import importlib
import logging
import random
from functools import wraps
from logging.handlers import RotatingFileHandler
import re

import yaml
from flask import abort, g
from yaml import YAMLError

from pebbles.config import LOG_FORMAT

# PASSWORD_CHARACTERS created with:
# re.sub(r'[Ol10]', '', string.ascii_uppercase + string.ascii_lowercase)
PASSWORD_CHARACTERS = "ABCDEFGHIJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def create_password(length=8):
    password = ''.join(random.choice(PASSWORD_CHARACTERS) for _ in range(length))
    return password


def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def requires_workspace_owner_or_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user.is_admin and not g.user.is_workspace_owner:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def memoize(func):
    """
    Generic memoization implementation suitable for decorator use
    """
    cache = {}

    def inner(x):
        if x not in cache:
            cache[x] = func(x)
        return cache[x]

    return inner


def check_attribute_limit_format(limits):
    """Check attribute limit format. Return None if AOK, error string otherwise"""
    for limit in limits:
        name = limit.get('name', None)
        min = limit.get('min', None)
        max = limit.get('max', None)
        if name is None or min is None or max is None:
            return 'each limit needs to have name, min and max defined'
        if type(min) not in (int, float):
            return 'min value for %s is not a number' % name
        if type(max) not in (int, float):
            return 'max value for %s is not a number' % name
        if min > max:
            return 'min > max for %s' % name

    return None


def check_config_against_attribute_limits(config, limits):
    """Check application config against attribute limits. Return None if AOK, error string otherwise"""
    for limit in limits:
        if limit['name'] in config:
            name = limit['name']
            value = config[name]
            if type(value) not in (int, float):
                return 'value for attribute %s is not a number' % name
            if value < limit['min'] or value > limit['max']:
                return 'value %s for attribute %s does not fall within allowed range %s to %s' % \
                    (value, name, limit['min'], limit['max'])

    return None


def get_provisioning_config(application):
    """Render provisioning config for application"""

    app_config = application.config if application.config else {}
    provisioning_config = application.base_config.copy()

    # pick attribute values with a limited range (for lifetime and memory)
    error = check_config_against_attribute_limits(app_config, application.attribute_limits)
    if error:
        raise ValueError('application %s config check failed: %s ' % (application.id, error))
    for limit in application.attribute_limits:
        if limit['name'] in app_config:
            name = limit['name']
            value = app_config[name]
            provisioning_config[name] = value

    # set memory_limit from memory_gib
    provisioning_config['memory_limit'] = '%dMi' % round(float(provisioning_config['memory_gib']) * 1024)

    # here we pick configuration options from app config to custom_config that is used in provisioning
    custom_config = {}
    # common autodownload options
    if app_config.get('download_method'):
        method = app_config.get('download_method')
        if method in ('http-get', 'git-clone'):
            custom_config['download_method'] = method
            custom_config['download_url'] = app_config.get('download_url')
        elif method != 'none':
            logging.warning('unknown download_method %s', method)

    # application type specific configs
    if application.application_type == 'jupyter':
        if app_config.get('jupyter_interface') in ('notebook', 'lab'):
            custom_config['jupyter_interface'] = app_config.get('jupyter_interface')
        else:
            custom_config['jupyter_interface'] = 'lab'

    elif application.application_type == 'rstudio':
        # nothing special required for rstudio yet
        pass
    else:
        logging.warning('unknown application_type %s', application.application_type)

    # pick the persistent work folder option
    if app_config.get('enable_user_work_folder'):
        custom_config['enable_user_work_folder'] = app_config.get('enable_user_work_folder')

    # customize image url
    if app_config.get('image_url'):
        provisioning_config['image'] = app_config.get('image_url')

    # customize image pull policy
    if app_config.get('always_pull_image'):
        provisioning_config['image_pull_policy'] = 'Always'

    # pick custom environment variables
    if app_config.get('environment_vars'):
        # tidy up first, input from the user could be malformed
        app_config_env_dict = env_string_to_dict(app_config.get('environment_vars', ''))
        provisioning_config_env_dict = env_string_to_dict(provisioning_config.get('environment_vars', ''))
        # merge custom values to provisioning environments, potentially overriding existing values
        provisioning_config_env_dict = provisioning_config_env_dict | app_config_env_dict
        custom_config['environment_vars'] = ' '.join(['%s=%s' % (i[0], i[1]) for i in app_config_env_dict.items()])
        provisioning_config['environment_vars'] = ' '.join(
            ['%s=%s' % (i[0], i[1]) for i in provisioning_config_env_dict.items()]
        )

    # enable shared folder for non-public workspaces - this should be refined later
    if application.workspace.name.startswith('System.'):
        custom_config['enable_shared_folder'] = False
    elif 'enable_shared_folder' in app_config:
        custom_config['enable_shared_folder'] = app_config.get('enable_shared_folder')
    else:
        custom_config['enable_shared_folder'] = True

    # global settings from workspace
    provisioning_config['scheduler_tolerations'] = application.workspace.config.get('scheduler_tolerations', [])
    try:
        provisioning_config['user_work_folder_size_gib'] = int(application.workspace.config.get(
            'user_work_folder_size_gib',
            app_config.get('user_work_folder_size', 1)
        ))
    except ValueError:
        logging.warning('invalid user work folder size in application %s', application.id)
        provisioning_config['user_work_folder_size_gib'] = 1

    # assign cluster from workspace
    provisioning_config['cluster'] = application.workspace.cluster

    provisioning_config['custom_config'] = custom_config

    return provisioning_config


def env_string_to_dict(keyval_string):
    """ Extract a dictionary from space separated key=val formatted string """
    res = dict()
    for keyval in keyval_string.split():
        if '=' not in keyval:
            continue
        tokens = keyval.split('=')
        if len(tokens) != 2:
            continue
        key, val = tokens
        if not key:
            continue
        res[key] = val
    return res


def get_application_fields_from_config(application, field_name):
    """Hybrid fields for Application model which need processing"""
    provisioning_config = get_provisioning_config(application)

    if field_name == 'cost_multiplier':
        cost_multiplier = 1.0  # Default value
        if 'cost_multiplier' in provisioning_config:
            try:
                cost_multiplier = float(provisioning_config['cost_multiplier'])
            except ValueError:
                pass
        return cost_multiplier


def b64encode_string(content):
    """convenience function to base64 encode a string to UTF-8"""
    return base64.b64encode(content.encode('utf-8')).decode('utf-8')


def init_logging(config, log_name):
    """set up logging"""
    logging.basicConfig(
        level=logging.DEBUG if config.DEBUG else logging.INFO,
        format=LOG_FORMAT
    )
    if config.ENABLE_FILE_LOGGING:
        logfile = '%s/%s.log' % (config.LOG_DIRECTORY, log_name)
        logging.debug('enabling file logging to %s', logfile)
        handler = RotatingFileHandler(filename=logfile, maxBytes=10 * 1024 * 1024, backupCount=5)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.getLogger().addHandler(handler)


def load_cluster_config(
        load_passwords=True,
        cluster_config_file='/run/secrets/pebbles/cluster-config.yaml',
        cluster_passwords_file='/run/secrets/pebbles/cluster-passwords.yaml',
):
    """load configuration for clusters where the application sessions are executed"""

    try:
        cluster_config = yaml.safe_load(open(cluster_config_file, 'r'))
    except (IOError, ValueError) as e:
        logging.warning("Unable to parse cluster data from path %s", cluster_config_file)
        raise e

    # just the config (used by API)
    if not load_passwords:
        logging.debug('found clusters: %s', [x['name'] for x in cluster_config.get('clusters')])
        return cluster_config

    # merge password info into the config
    try:
        cluster_passwords = yaml.safe_load(open(cluster_passwords_file, 'r'))
    except (IOError, ValueError) as e:
        logging.warning("Unable to parse cluster passwords from path %s", cluster_passwords_file)
        raise e

    for cluster in cluster_config.get('clusters'):
        cluster_name = cluster.get('name')
        password_data = cluster_passwords.get(cluster_name)
        if not password_data:
            continue
        logging.debug('setting password data for cluster %s' % cluster_name)
        if isinstance(password_data, str):
            # simple string is password in an old style structure
            cluster['password'] = password_data
        else:
            cluster['password'] = password_data.get('password')
            cluster['monitoringToken'] = password_data.get('monitoringToken')

    return cluster_config


def find_driver_class(driver_name):
    """tries to find a provisioning driver by name"""
    driver_class = None
    for module in 'kubernetes_driver', 'openshift_template_driver':
        driver_class = getattr(
            importlib.import_module('pebbles.drivers.provisioning.%s' % module),
            driver_name,
            None
        )
        if driver_class:
            break

    return driver_class


def load_auth_config(path):
    try:
        return yaml.safe_load(open(path))
    except IOError as e:
        logging.warning('cannot open auth-config.yaml, error %s', e)
    except YAMLError as e:
        logging.warning('cannot parse auth-config.yaml, error %s', e)
    return None


def read_list_from_text_file(path):
    """
    Reads a text file and returns the contents as a list excluding any items that
    do not begin with an alphabetic character
    """
    with open(path, 'r') as f:
        items = f.read().splitlines()
    items = [item.strip() for item in items if item.strip() and re.match(r'[a-zA-Z]', item.strip()[0])]
    return items
