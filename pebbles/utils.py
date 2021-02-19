import base64
import importlib
import logging
import re
from functools import wraps
from logging.handlers import RotatingFileHandler

import yaml
from flask import abort, g

from pebbles.config import LOG_FORMAT


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


def parse_maximum_lifetime(max_life_str):
    m = re.match(r'^(\d+d\s?)?(\d{1,2}h\s?)?(\d{1,2}m\s?)??$', max_life_str)
    if m:
        days = hours = mins = 0
        if m.group(1):
            days = int(m.group(1).strip()[:-1])
        if m.group(2):
            hours = int(m.group(2).strip()[:-1])
        if m.group(3):
            mins = int(m.group(3).strip()[:-1])

        maximum_lifetime = days * 86400 + hours * 3600 + mins * 60
        return maximum_lifetime
    else:
        raise ValueError


def parse_ports_string(ports_str):
    ports_list = []
    ports_str = ports_str.replace(',', ' ')
    ports = ports_str.split(' ')
    ports = filter(None, ports)
    for port in ports:
        if ':' in port:
            (from_port, to_port) = parse_port_range(port)
        else:
            try:
                from_port = int(port)
                to_port = int(port)
            except ValueError:
                raise ValueError('Port is not an integer')

        if 0 < from_port < 65536 and 0 < to_port < 65536:
            ports_list.append((from_port, to_port))
        else:
            raise ValueError('Error parsing the input port string')
    return ports_list


def parse_port_range(port_range):
    m = re.match(r'(\d+):(\d+)', port_range)
    if m:
        if int(m.group(1)) < int(m.group(2)):
            return int(m.group(1)), int(m.group(2))
        else:
            raise ValueError('Port range invalid')
    else:
        raise ValueError('No port range found')


def get_full_environment_config(environment):
    """Get the full config for environment"""

    # old style override of template base_config with environment config
    template = environment.template
    allowed_attrs = template.allowed_attrs
    full_config = template.base_config
    env_config = environment.config if environment.config else {}
    for attr in allowed_attrs:
        if attr in env_config:
            full_config[attr] = env_config[attr]

    # here we pick configuration options from environment to full_config that is used in provisioning
    custom_config = {}
    # common autodownload options
    if env_config.get('download_method'):
        method = env_config.get('download_method')
        if method in ('http-get', 'git-clone'):
            custom_config['download_method'] = method
            custom_config['download_url'] = env_config.get('download_url')
        else:
            logging.warning('unknown download_method', method)

    # environment type specific configs
    if template.environment_type == 'jupyter':
        if env_config.get('jupyter_interface') in ('notebook', 'lab'):
            custom_config['jupyter_interface'] = env_config.get('jupyter_interface')
        else:
            custom_config['jupyter_interface'] = 'lab'

    elif template.environment_type == 'rstudio':
        logging.warning('rstudio config not implemented yet')

    full_config['custom_config'] = custom_config

    return full_config


def get_environment_fields_from_config(environment, field_name):
    """Hybrid fields for Environment model which need processing"""
    full_config = get_full_environment_config(environment)

    if field_name == 'cost_multiplier':
        cost_multiplier = 1.0  # Default value
        if 'cost_multiplier' in full_config:
            try:
                cost_multiplier = float(full_config['cost_multiplier'])
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


def load_cluster_config(load_passwords=True):
    """load configuration for clusters where the instances are executed"""
    cluster_config_file = '/run/secrets/pebbles/cluster-config.yaml'

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
    cluster_passwords_file = '/run/secrets/pebbles/cluster-passwords.yaml'
    try:
        cluster_passwords = yaml.safe_load(open(cluster_passwords_file, 'r'))
    except (IOError, ValueError) as e:
        logging.warning("Unable to parse cluster passwords from path %s", cluster_passwords_file)
        raise e

    for cluster in cluster_config.get('clusters'):
        cluster_name = cluster.get('name')
        password = cluster_passwords.get(cluster_name)
        if password:
            logging.debug('setting password for cluster %s' % cluster_name)
            cluster['password'] = password

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
