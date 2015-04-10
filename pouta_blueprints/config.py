import os
import yaml
import functools

CONFIG_FILE = '/etc/pouta_blueprints/config.yaml'


def resolve_configuration_value(key, default=None, *args, **kwargs):
    pb_key = 'PB_' + key
    value = os.getenv(pb_key)
    if value:
        return value

    CONFIG = {}
    if os.path.isfile(CONFIG_FILE):
        CONFIG = yaml.load(open(CONFIG_FILE).read())
    if key in CONFIG:
        return CONFIG[key]
    elif default is not None:
        return default
    else:
        raise RuntimeError('configuration value for %s missing' % key)


def fields_to_properties(cls):
    for k, default in vars(cls).items():
        if not k.startswith('_'):
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

    def __getitem__(self, item):
        return getattr(self, item)


class TestConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True
    SKIP_TASK_QUEUE = True
    WRITE_PROVISIONING_LOGS = False
