import os
import yaml
import functools
from pouta_blueprints.models import Variable

CONFIG_FILE = '/etc/pouta_blueprints/config.yaml'
LOCAL_CONFIG_FILE = '/etc/pouta_blueprints/config.yaml.local'


def resolve_configuration_value(key, default=None, *args, **kwargs):
    def get_key_from_config(config_file, key):
        return yaml.load(open(config_file)).get(key)

    # Querying DB will fail during the program initialization as SQLAlchemy is
    # not yet properly initialized
    try:
        variable = Variable.query.filter_by(key=key).first()
        if variable:
            return variable.value
    except:
        pass

    # check environment
    pb_key = 'PB_' + key
    value = os.getenv(pb_key)
    if value is not None:
        return value

    # then check local config file and finally check system
    # config file and given default
    for config_file in (LOCAL_CONFIG_FILE, CONFIG_FILE):
        if os.path.isfile(config_file):
            value = get_key_from_config(config_file, key)
            if value is not None:
                return value

    if default is not None:
        return default


def fields_to_properties(cls):
    for k, default in vars(cls).items():
        if not k.startswith('_') and k.isupper():
            resolvef = functools.partial(resolve_configuration_value, k, default)
            setattr(cls, k, property(resolvef))
    return cls


@fields_to_properties
class BaseConfig(object):
    DEBUG = True
    SECRET_KEY = "change_me"
    WTF_CSRF_ENABLED = False
    SSL_VERIFY = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/change_me.db'
    M2M_CREDENTIAL_STORE = '/var/run/pouta_blueprints_m2m'
    MESSAGE_QUEUE_URI = 'redis://www:6379/0'
    INSTANCE_DATA_DIR = '/var/spool/pb_instances'
    INTERNAL_API_BASE_URL = 'https://www/api/v1'
    BASE_URL = 'https://localhost:8888'
    MAX_CONTENT_LENGTH = 1024 * 1024
    FAKE_PROVISIONING = False
    SENDER_EMAIL = 'sender@example.org'
    MAIL_SERVER = 'smtp.example.org'
    MAIL_SUPPRESS_SEND = True
    MAIL_USE_TLS = False
    SKIP_TASK_QUEUE = False
    WRITE_PROVISIONING_LOGS = True
    INSTANCE_NAME_PREFIX = 'pb-'
    DEFAULT_QUOTA = 1.0
    ENABLE_SHIBBOLETH_LOGIN = False
    INSTALLATION_NAME = 'Pouta Blueprints'
    PLUGIN_WHITELIST = ''

    DD_SHUTDOWN_MODE = True
    DD_HOST_IMAGE = 'CentOS-7.0'
    DD_MAX_HOSTS = 4
    DD_FREE_SLOT_TARGET = 4
    DD_HOST_FLAVOR_NAME_SMALL = 'mini'
    DD_HOST_FLAVOR_SLOTS_SMALL = 6
    DD_HOST_FLAVOR_NAME_LARGE = 'small'
    DD_HOST_FLAVOR_SLOTS_LARGE = 24
    DD_HOST_MASTER_SG = 'pb_server'
    DD_HOST_EXTRA_SGS = ''

    # enable access by []
    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, key):
        return getattr(self, key)


class TestConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True
    SKIP_TASK_QUEUE = True
    WRITE_PROVISIONING_LOGS = False
