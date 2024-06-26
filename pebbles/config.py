"""
Pebbles is configured with a number of **variables**.

These variables come, in the order of precedence from

- environment variables, prefixed with PB_
- a configuration file
- built-in defaults

Naming convention is `UPPERCASE_WORDS_WITH_UNDERSCORES`.

To see the complete list check out pebbles.config that houses the object.
Only some have been documented.

The idea is that you could have a single docker container with multiple
entry points. All containers can (or should) see the same configuration file
and then at start-up time application variables can be set to e.g.
differentiate workers to run a particular driver.

"""
import functools
import os

import yaml

CONFIG_FILE = '/run/configmaps/pebbles/api-configmap/pebbles.yaml'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


# each config can be documented by making the default value into a (value,
# docstring) tuple
class BaseConfig:
    """ Stores the default key, value pairs for the system configuration.

        This is meant to be a base class, use RuntimeConfig or TestConfig
        for instances.
    """

    # Flask config
    # flask debug mode, see https://flask.palletsprojects.com/en/2.0.x/quickstart/#debug-mode
    DEBUG = False
    # secret for encrypting session tokens
    SECRET_KEY = 'change_me'
    WTF_CSRF_ENABLED = False
    # form content limit
    MAX_CONTENT_LENGTH = 1024 * 1024
    # safety for never showing the request content in the exception
    # https://flask.palletsprojects.com/en/2.0.x/config/#PRESERVE_CONTEXT_ON_EXCEPTION
    PRESERVE_CONTEXT_ON_EXCEPTION = False

    # Database connection
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:__PASSWORD__@localhost/pebbles'
    DATABASE_PASSWORD = 'pebbles'

    # Base url for this installation used for creating hyperlinks
    BASE_URL = 'https://localhost:8888'
    # Internal url for contacting the API, defaults to 'api' Service
    INTERNAL_API_BASE_URL = 'http://api:8080/api/v1'
    # prefix all application session names with this
    SESSION_NAME_PREFIX = 'pb-'

    # Info about the system for frontend
    INSTALLATION_NAME = 'Pebbles'
    SHORT_DESCRIPTION = 'Easy-to-use applications for working with data and programming.'
    INSTALLATION_DESCRIPTION = 'Log in to see the catalogue of available applications. ' + \
                               'Applications run in the cloud and are accessed with your browser.'

    BRAND_IMAGE_URL = 'img/Notebooks_neg300px.png'
    COURSE_REQUEST_FORM_URL = 'http://link-to-form'
    TERMS_OF_USE_URL = 'http://link-to-tou'
    COOKIES_POLICY_URL = 'http://link-to-cookiespolicy'
    PRIVACY_POLICY_URL = 'http://link-to-privacypolicy'
    ACCESSIBILITY_STATEMENT_URL = 'http://link-to-accessibility-statement'
    CONTACT_EMAIL = 'support@example.org'
    SERVICE_DOCUMENTATION_URL = 'http://link-to-service-documentation'
    SERVICE_ANNOUNCEMENT = ''

    # Mail settings
    MAIL_SERVER = 'smtp.example.org'
    MAIL_SENDER_EMAIL = 'sender@example.org'
    MAIL_SUPPRESS_SEND = True
    MAIL_USE_TLS = False

    # Oauth2 master switch
    OAUTH2_LOGIN_ENABLED = False

    # Terms and conditions settings
    AGREEMENT_TITLE = 'Title here'
    AGREEMENT_TERMS_PATH = 'http://link-to-terms'
    AGREEMENT_COOKIES_PATH = 'http://link-to-cookies'
    AGREEMENT_PRIVACY_PATH = 'http://link-to-privacy'
    AGREEMENT_LOGO_PATH = 'assets/images/login/csc_front_logo.svg'

    # Logging settings
    LOG_DIRECTORY = '/opt/log'
    ENABLE_FILE_LOGGING = False

    # Clusters configuration
    CLUSTER_CONFIG_FILE = '/run/secrets/pebbles/cluster-config.yaml'
    CLUSTER_PASSWORDS_FILE = '/run/secrets/pebbles/cluster-passwords.yaml'
    CLUSTER_KUBECONFIG_FILE = '/var/run/secrets/pebbles/cluster-kubeconfig'
    DEFAULT_CLUSTER = 'local_kubernetes'

    # API configmap paths
    API_AUTH_CONFIG_FILE = '/run/configmaps/pebbles/api-configmap/auth-config.yaml'
    API_FAQ_FILE = '/run/configmaps/pebbles/api-configmap/faq-content.yaml'
    API_PUBLIC_STRUCTURED_CONFIG_FILE = '/run/configmaps/pebbles/api-configmap/public-structured-config.yaml'

    # enable access by []
    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, key):
        return getattr(self, key)

    def __contains__(self, item):
        try:
            getattr(self, item)
        except AttributeError:
            return False
        return True


def _parse_env_value(val):
    """
    Pars application variables to bool, integer or float or default to string.

    :param val:
    :return: val coerced into a type if it looks to be of one
    """
    if val.lower() == "false":
        return False
    elif val.lower() == "true":
        return True
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def resolve_configuration_value(key, default=None, *args, **kwargs):
    def get_key_from_config(config_file, key):
        return yaml.safe_load(open(config_file)).get(key)

    # check application
    pb_key = 'PB_' + key
    value = os.getenv(pb_key)
    if value is not None:
        return _parse_env_value(value)

    # then finally check system config file and given default
    if os.path.isfile(CONFIG_FILE):
        value = get_key_from_config(CONFIG_FILE, key)
        if value is not None:
            return value

    if default is not None:
        return default


class RuntimeConfig(BaseConfig):
    """Main config object that resolves values dynamically at runtime."""

    def __init__(self):
        for k, default in vars(BaseConfig).items():
            if type(default) is tuple and len(default) == 2:
                default, doc_ = default
            else:
                doc_ = ''
            if not k.startswith('_') and k.isupper():
                resolvef = functools.partial(resolve_configuration_value, k, default)
                prop = property(resolvef, doc=doc_)
                setattr(RuntimeConfig, k, prop)


class TestConfig(BaseConfig):
    """Unit tests config object"""
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    MAIL_SUPPRESS_SEND = True
    BCRYPT_LOG_ROUNDS = 4
    TEST_MODE = True
    INSTALLATION_NAME = 'Pebbles'
