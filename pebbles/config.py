"""
Pebbles is configured with a number of **variables**.

These variables come, in the order of precedence from

- environment variables
- a configuration file
- built-in defaults

Naming convention is `UPPERCASE_WORDS_WITH_UNDERSCORES`.

To see the complete list check out pebbles.config that houses the object.
Only some have been documented.

The idea is that you could have a single docker container with multiple
entry points. All containers can (or should) see the same configuration file
and then at start-up time environment variables can be set to e.g.
differentiate workers to run a particular driver.

"""
import os
import yaml
import functools

CONFIG_FILE = '/etc/pebbles/config.yaml'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def _parse_env_value(val):
    """
    Pars environment variables to bool, integer or float or default to string.

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
        return yaml.load(open(config_file)).get(key)

    # check environment
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


def fields_to_properties(cls):
    for k, default in vars(cls).items():
        if type(default) == tuple and len(default) == 2:
            default, doc_ = default
        else:
            doc_ = ''
        if not k.startswith('_') and k.isupper():
            resolvef = functools.partial(resolve_configuration_value, k, default)
            prop = property(resolvef, doc=doc_)
            setattr(cls, k, prop)
    return cls


# each config can be documented by making the default value into a (value,
# docstring) tuple
@fields_to_properties
class BaseConfig(object):
    """ Stores the default key, value pairs for the system configuration.
        Rendered with a decorator which considers any environment variables,
        then the system level config file and finally the default values,
        in that order of precedence.
    """
    DEBUG = (
        True,
        'Controls debug mode'
    )
    SECRET_KEY = 'change_me'
    WTF_CSRF_ENABLED = False
    SSL_VERIFY = False
    # SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/change_me.db'
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:pebbles@localhost/pebbles'
    DATABASE_PASSWORD = None

    # Base url for this installation used for creating hyperlinks
    BASE_URL = 'https://localhost:8888'
    # Internal url for contacting the API, defaults to 'api' Service
    INTERNAL_API_BASE_URL = 'http://api:8080/api/v1'

    # form content limit in flask
    MAX_CONTENT_LENGTH = 1024 * 1024

    SENDER_EMAIL = 'sender@example.org'
    MAIL_SERVER = 'smtp.example.org'
    MAIL_SUPPRESS_SEND = True
    MAIL_USE_TLS = False
    SKIP_TASK_QUEUE = False
    INSTANCE_NAME_PREFIX = (
        'pb-',
        'all spawned instance names will have this prefix'
    )
    INSTALLATION_NAME = 'Pebbles'
    INSTALLATION_DESCRIPTION = ('A tool for provisioning '
                                'ephemeral private cloud resources.')
    SHORT_DESCRIPTION = 'Welcome to Notebooks'
    BRAND_IMAGE = (
        'img/Notebooks_neg300px.png',
        'An image URL for branding the installation'
    )
    COURSE_REQUEST_FORM = 'http://link-to-form'
    HAKA_INSTITUTION_LIST = (
        '{"university": [], "polytechnic": [], "institution": []}',
        'Dictionary of institution types and corresponding domains'
    )

    PRESERVE_CONTEXT_ON_EXCEPTION = False

    # Oauth2 settings
    OAUTH2_LOGIN_ENABLED = False
    OAUTH2_LOGO_URL = '/img/CSC_login.png'

    OAUTH2_AUTH_METHODS = ['list of idps allowed to login via sso']
    OAUTH2_OPENID_CONFIGURATION_URL = 'https://openid-configuration'

    # Terms and conditions settings
    AGREEMENT_TITLE = 'Title here'
    AGREEMENT_TERMS_PATH = 'http://link-to-terms'
    AGREEMENT_COOKIES_PATH = 'http://link-to-cookies'
    AGREEMENT_PRIVACY_PATH = 'http://link-to-privacy'
    AGREEMENT_LOGO_PATH = 'assets/images/login/csc_front_logo.svg'

    LOG_DIRECTORY = '/opt/log'

    ENABLE_FILE_LOGGING = False

    CLUSTER_CONFIG_FILE = '/run/secrets/pebbles/cluster-config.yaml'
    CLUSTER_PASSWORDS_FILE = '/run/secrets/pebbles/cluster-passwords.yaml'
    CLUSTER_KUBECONFIG_FILE = '/var/run/secrets/pebbles/cluster-kubeconfig'

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


class TestConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    MAIL_SUPPRESS_SEND = True
    SKIP_TASK_QUEUE = True
    BCRYPT_LOG_ROUNDS = 4
    TEST_MODE = True
    INSTALLATION_NAME = 'Pebbles'


class LiveTestConfig(TestConfig):
    """ Config for testing live. e.g. with Selenium.
    """
    # Live testing setup spawns a subprocess for the live server so in-memory
    # is not easily achievable.
    # ToDo: we could use tempfile to create a temporary named file in __init__
    # and close it in __del__. If we do it's important to log the location so
    # that the tester can access the db manually.
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/change_me.livetest.db'
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    # bit of culture never hurt anybody
    INSTALLATION_NAME = 'Underworld Branding Iron'
    INSTALLATION_DESCRIPTION = 'Abandon all hope, ye who enter here.'
