import os
import yaml

CONFIG_FILE = '/etc/pouta_blueprints/config.yaml'
CONFIG = {}
if os.path.isfile(CONFIG_FILE):
    CONFIG = yaml.load(open(CONFIG_FILE).read())


def resolve_configuration_value(key, default=None):
    pb_key = 'PB_' + key
    value = os.getenv(pb_key)
    if value:
        return value
    elif key in CONFIG:
        return CONFIG[key]
    elif default:
        return default
    elif not default:
        raise RuntimeError('configuration value for %s missing' % key)


class BaseConfig(object):
    DEBUG = True
    SECRET_KEY = resolve_configuration_value('SECRET_KEY', default='change_me')
    WTF_CSRF_ENABLED = False
    SSL_VERIFY = False
    SQLALCHEMY_DATABASE_URI = resolve_configuration_value(
        'SQLALCHEMY_DATABASE_URI',
        default='sqlite:////tmp/change_me.db')
    M2M_CREDENTIAL_STORE = resolve_configuration_value(
        'M2M_CREDENTIAL_STORE',
        default='/var/run/pouta_blueprints_m2m')
    MESSAGE_QUEUE_URI = 'redis://www:6379/0'
    PVC_CLUSTER_DATA_DIR = '/var/spool/pvc_clusters'
    INTERNAL_API_BASE_URL = 'https://www/api/v1'
    BASE_URL = 'https://localhost:8888'
    MAX_CONTENT_LENGTH = 1024 * 1024
    FAKE_PROVISIONING = False
    SENDER_EMAIL = 'sender@example.org'
    SKIP_TASK_QUEUE = False
    WRITE_PROVISIONING_LOGS = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SSL_VERIFY = True
    MAIL_SERVER = 'smtp.example.org'


class DevConfig(BaseConfig):
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True


class TestConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True
    SKIP_TASK_QUEUE = True
    WRITE_PROVISIONING_LOGS = False
