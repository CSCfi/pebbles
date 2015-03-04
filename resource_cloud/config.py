import os
from base64 import b64encode


class BaseConfig(object):
    DEBUG = True
    SECRET_KEY = b64encode(os.urandom(24)).decode('utf-8')
    WTF_CSRF_ENABLED = False
    SSL_VERIFY = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/change_me.db'
    MESSAGE_QUEUE_URI = 'redis://localhost:6379/0'
    PVC_CLUSTER_DATA_DIR = '/var/spool/pvc_clusters'
    BASE_URL = 'https://localhost:8888'
    MAX_CONTENT_LENGTH = 1024 * 1024
    FAKE_PROVISIONING = False
    SENDER_EMAIL = 'resource_cloud@csc.fi'
    SKIP_TASK_QUEUE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SSL_VERIFY = True


class DevConfig(BaseConfig):
    SECRET_KEY = 'change_me'
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True


class TestConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True
    SKIP_TASK_QUEUE = True
