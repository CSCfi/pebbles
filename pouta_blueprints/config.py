import os
import yaml
import functools

CONFIG_FILE = '/etc/pouta_blueprints/config.yaml'
LOCAL_CONFIG_FILE = '/etc/pouta_blueprints/config.yaml.local'


def resolve_configuration_value(key, default=None, *args, **kwargs):
    # first check environment
    pb_key = 'PB_' + key
    value = os.getenv(pb_key)
    if value:
        return value

    # then check local config file
    if os.path.isfile(LOCAL_CONFIG_FILE):
        config = yaml.load(open(LOCAL_CONFIG_FILE).read())
        if key in config:
            return config[key]

    # finally check system config file and given default
    if os.path.isfile(CONFIG_FILE):
        config = yaml.load(open(CONFIG_FILE).read())
        if key in config:
            return config[key]

    if default is not None:
        return default

    raise RuntimeError('configuration value for %s missing' % key)


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
    SKIP_TASK_QUEUE = False
    WRITE_PROVISIONING_LOGS = True

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
