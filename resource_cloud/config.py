import os


class BaseConfig(object):
    DEBUG = True
    SECRET_KEY = os.urandom(24)
    WTF_CSRF_ENABLED = False
    SSL_VERIFY = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/change_me.db'
    MESSAGE_QUEUE_URI = 'redis://localhost:6379/0'
    PVC_CLUSTER_DATA_DIR = '/var/spool/pvc_clusters'
    BASE_URL = 'https://localhost:8888'
    MAX_CONTENT_LENGTH = 1024 * 1024
    FAKE_PROVISIONING = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SSL_VERIFY = True


class DevConfig(BaseConfig):
    SECRET_KEY = 'change_me'
    MAIL_SUPPRESS_SEND = True
    FAKE_PROVISIONING = True


class TestConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
