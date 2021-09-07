import datetime
import json
import logging
import random
import secrets
import string
import time
import uuid

import names
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from jose import jwt, JWTError, ExpiredSignatureError
from jose.exceptions import JWTClaimsError, JWSError
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.schema import MetaData

from pebbles.utils import get_environment_fields_from_config

MAX_PSEUDONYM_LENGTH = 32
MAX_PASSWORD_LENGTH = 100
MAX_EMAIL_LENGTH = 128
MAX_NAME_LENGTH = 128
MAX_VARIABLE_KEY_LENGTH = 512
MAX_VARIABLE_VALUE_LENGTH = 512
MAX_MESSAGE_SUBJECT_LENGTH = 255

JWS_SIGNING_ALG = 'HS512'

db = SQLAlchemy()

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db.Model.metadata = MetaData(naming_convention=convention)

bcrypt = Bcrypt()

NAME_ADJECTIVES = (
    'happy',
    'sad',
    'bright',
    'dark',
    'blue',
    'yellow',
    'red',
    'green',
    'white',
    'black',
    'clever',
    'witty',
    'smiley',
)


class CaseInsensitiveComparator(Comparator):
    def __eq__(self, other):
        return func.lower(self.__clause_element__()) == func.lower(other)


def load_column(column):
    try:
        value = json.loads(column)
    except:
        value = {}
    return value


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(32), primary_key=True)
    # ext_id is mandatory and unique. ext_id can be used to retrieve database objects
    _ext_id = db.Column('ext_id', db.String(MAX_EMAIL_LENGTH), unique=True)
    # email_id field is used only for sending emails.
    _email_id = db.Column('email_id', db.String(MAX_EMAIL_LENGTH))
    pseudonym = db.Column(db.String(MAX_PSEUDONYM_LENGTH), unique=True, nullable=False)
    password = db.Column(db.String(MAX_PASSWORD_LENGTH))
    _joining_ts = db.Column('joining_ts', db.DateTime)
    _last_login_ts = db.Column('last_login_ts', db.DateTime)
    _expiry_ts = db.Column('expiry_ts', db.DateTime)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    latest_seen_message_ts = db.Column(db.DateTime)
    workspace_quota = db.Column(db.Integer, default=0)
    tc_acceptance_date = db.Column(db.DateTime)
    instances = db.relationship('Instance', backref='user', lazy='dynamic')
    workspace_associations = db.relationship("WorkspaceUserAssociation", back_populates="user", lazy='dynamic')

    def __init__(self, ext_id, password=None, is_admin=False, email_id=None, expiry_ts=None, pseudonym=None,
                 workspace_quota=None):
        self.id = uuid.uuid4().hex
        self.ext_id = ext_id
        self.is_admin = is_admin
        self.joining_ts = time.time()
        if expiry_ts:
            self.expiry_ts = expiry_ts
        if email_id:
            self.email_id = email_id
        if password:
            self.set_password(password)
            self.is_active = True
        else:
            self.set_password(uuid.uuid4().hex)
        if pseudonym:
            self.pseudonym = pseudonym
        else:
            # Here we opportunistically create a pseudonym without actually checking the existing user table
            # the probability of collision is low enough. There are 400 pseudonyms for all inhabitants on earth
            # with 36**8 alternatives
            self.pseudonym = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        if workspace_quota:
            self.workspace_quota = workspace_quota

    def __eq__(self, other):
        return self.id == other.id

    @hybrid_property
    def ext_id(self):
        return self._ext_id.lower()

    @ext_id.setter
    def ext_id(self, value):
        self._ext_id = value.lower()

    @ext_id.comparator
    def ext_id(cls):
        return CaseInsensitiveComparator(cls._ext_id)

    @hybrid_property
    def email_id(self):
        if self._email_id:
            return self._email_id.lower()

    @email_id.setter
    def email_id(self, value):
        if value:
            self._email_id = value.lower()

    @email_id.comparator
    def email_id(cls):
        return CaseInsensitiveComparator(cls._email_id)

    @hybrid_property
    def is_workspace_owner(self):
        # we are a workspace owner if we have existing workspaces or have quota to create one
        return self.workspace_quota > 0 or self.get_owned_workspace_associations()

    @hybrid_property
    def is_workspace_manager(self):
        # we are a workspace managerif we are mapped to be one
        return self.get_managed_workspace_associations()

    @is_workspace_owner.setter
    def is_workspace_owner(self, value):
        raise RuntimeError('Set workspace owner status through workspace quota and membership')

    @hybrid_property
    def joining_ts(self):
        return self._joining_ts.timestamp()

    @joining_ts.setter
    def joining_ts(self, value):
        self._joining_ts = datetime.datetime.fromtimestamp(value)

    @hybrid_property
    def expiry_ts(self):
        return self._expiry_ts.timestamp()

    @expiry_ts.setter
    def expiry_ts(self, value):
        self._expiry_ts = datetime.datetime.fromtimestamp(value)

    @hybrid_property
    def last_login_ts(self):
        return self._last_login_ts.timestamp()

    @last_login_ts.setter
    def last_login_ts(self, value):
        self._last_login_ts = datetime.datetime.fromtimestamp(value)

    def delete(self):
        if self.is_deleted:
            return
        self.ext_id = self.ext_id + datetime.datetime.utcnow().strftime("-%s")
        # Email_id is also renamed to allow users
        # to be deleted and invited again with same email_id
        if self.email_id:
            self.email_id = self.email_id + datetime.datetime.utcnow().strftime("-%s")
        self.is_deleted = True
        self.is_active = False

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        if self.can_login():
            return bcrypt.check_password_hash(self.password, password)

    def generate_auth_token(self, app_secret, expires_in=43200):
        ts = int(time.time())
        # construct a token with user id in the claims and issue + expiration times in the header
        token = jwt.encode(
            claims=dict(
                id=self.id,
                iat=ts,
                exp=ts + expires_in,
            ),
            key=app_secret,
            algorithm=JWS_SIGNING_ALG
        )
        return token

    def can_login(self):
        return not self.is_deleted and self.is_active and not self.is_blocked

    def get_owned_workspace_associations(self):
        return [wua for wua in self.workspace_associations if wua.is_owner]

    def get_managed_workspace_associations(self):
        return [wua for wua in self.workspace_associations if wua.is_manager]

    @staticmethod
    def verify_auth_token(token, app_secret):
        try:
            # explicitly pass the single algorithm for signing to avoid token forging by algorithm tampering
            data = jwt.decode(token, app_secret, algorithms=[JWS_SIGNING_ALG])
        except (ExpiredSignatureError):
            logging.info('Token has expired "%s"', token)
            return None
        except (JWTError, JWSError, JWTClaimsError) as e:
            logging.warning('Possible hacking attempt "%s" with token "%s"', e, token)
            return None

        user = User.query.get(data['id'])
        if user and user.can_login():
            return user

    def __repr__(self):
        return self.ext_id

    def __hash__(self):
        return hash(self.ext_id)


class WorkspaceUserAssociation(db.Model):  # Association Object for many-to-many mapping
    __tablename__ = 'workspace_user_associations'
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'), primary_key=True)
    is_manager = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    user = db.relationship("User", back_populates="workspace_associations")
    workspace = db.relationship("Workspace", back_populates="user_associations")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Workspace(db.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    STATUS_DELETED = 'deleted'

    VALID_STATUSES = (
        STATUS_ACTIVE,
        STATUS_ARCHIVED,
        STATUS_DELETED
    )
    __tablename__ = 'workspaces'

    id = db.Column(db.String(32), primary_key=True)
    pseudonym = db.Column(db.String(MAX_PSEUDONYM_LENGTH), unique=True, nullable=False)
    name = db.Column(db.String(32))
    _join_code = db.Column('join_code', db.String(64))
    description = db.Column(db.Text)
    cluster = db.Column(db.String(32))
    # status when created is "active". Later there is option to be "archived".
    _status = db.Column('status', db.String(32), default=STATUS_ACTIVE)
    _create_ts = db.Column('create_ts', db.DateTime, default=datetime.datetime.utcnow)
    _expiry_ts = db.Column(
        'expiry_ts',
        db.DateTime,
        default=lambda: datetime.datetime.fromtimestamp(time.time() + 6 * 30 * 24 * 3600)
    )
    user_associations = db.relationship("WorkspaceUserAssociation", back_populates="workspace", lazy='dynamic',
                                        cascade="all, delete-orphan")
    environment_quota = db.Column(db.Integer, default=10)
    environments = db.relationship('Environment', backref='workspace', lazy='dynamic')

    def __init__(self, name, description='', cluster=None):
        self.id = uuid.uuid4().hex
        # Here we opportunistically create a pseudonym without actually checking the existing workspaces,
        # the probability of collision is low enough. There are 400 pseudonyms for all inhabitants on earth
        # with 36**8 alternatives
        self.pseudonym = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        self.name = name
        self.description = description
        self.join_code = name
        self.cluster = cluster
        self._status = Workspace.STATUS_ACTIVE

    @hybrid_property
    def join_code(self):
        return self._join_code

    @join_code.setter
    def join_code(self, name):
        name = name.replace(' ', '').lower()
        ascii_name = name.encode('ascii', 'ignore').decode()
        random_chars = ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(5))
        self._join_code = ascii_name + '-' + random_chars

    @hybrid_property
    def create_ts(self):
        return self._create_ts.timestamp()

    @create_ts.setter
    def create_ts(self, value):
        self._create_ts = datetime.datetime.fromtimestamp(value)

    @hybrid_property
    def expiry_ts(self):
        return self._expiry_ts.timestamp()

    @expiry_ts.setter
    def expiry_ts(self, value):
        self._expiry_ts = datetime.datetime.fromtimestamp(value)

    @hybrid_property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value in Workspace.VALID_STATUSES:
            self._status = value
        else:
            raise ValueError("'%s' is not a valid state for Workspaces" % value)


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.String(32), primary_key=True)
    broadcasted = db.Column(db.DateTime)
    subject = db.Column(db.String(MAX_MESSAGE_SUBJECT_LENGTH))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __init__(self, subject, message):
        self.id = uuid.uuid4().hex
        self.broadcasted = datetime.datetime.utcnow()
        self.subject = subject
        self.message = message


class EnvironmentTemplate(db.Model):
    ENVIRONMENT_TYPES = ['jupyter', 'rstudio', 'generic']

    __tablename__ = 'environment_templates'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    description = db.Column(db.Text)
    environment_type = db.Column(db.String(MAX_NAME_LENGTH))
    _base_config = db.Column('base_config', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    environments = db.relationship('Environment', backref='template', lazy='dynamic')
    _allowed_attrs = db.Column('allowed_attrs', db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __init__(self, name=None, description=None, environment_type='generic', allowed_attrs=None,
                 base_config=None, is_enabled=False):
        self.id = uuid.uuid4().hex
        self.name = name
        self.description = description
        if environment_type not in EnvironmentTemplate.ENVIRONMENT_TYPES:
            raise ValueError('Illegal environment type: "%s"' % environment_type)
        self.environment_type = environment_type
        self._allowed_attrs = json.dumps(allowed_attrs)
        self._base_config = json.dumps(base_config)
        self.is_enabled = is_enabled

    @hybrid_property
    def base_config(self):
        return load_column(self._base_config)

    @base_config.setter
    def base_config(self, value):
        self._base_config = json.dumps(value)

    @hybrid_property
    def allowed_attrs(self):
        return load_column(self._allowed_attrs)

    @allowed_attrs.setter
    def allowed_attrs(self, value):
        self._allowed_attrs = json.dumps(value)


class Environment(db.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    STATUS_DELETED = 'deleted'

    VALID_STATUSES = (
        STATUS_ACTIVE,
        STATUS_ARCHIVED,
        STATUS_DELETED,
    )

    __tablename__ = 'environments'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    description = db.Column(db.Text)
    template_id = db.Column(db.String(32), db.ForeignKey('environment_templates.id'))
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'))
    _labels = db.Column('labels', db.Text)
    maximum_lifetime = db.Column(db.Integer)
    _config = db.Column('config', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    expiry_time = db.Column(db.DateTime)
    instances = db.relationship('Instance', backref='environment', lazy='dynamic')
    # status when created is "active". Later there are options to be "archived" or "deleted".
    _status = db.Column('status', db.String(32), default='active')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __init__(self, name=None, description=None, template_id=None, workspace_id=None, labels=None,
                 maximum_lifetime=3600, is_enabled=False, config=None):
        self.id = uuid.uuid4().hex
        self.name = name
        self.description = description
        self.template_id = template_id
        self.workspace_id = workspace_id
        self.labels = labels
        self.maximum_lifetime = maximum_lifetime
        self.is_enabled = is_enabled
        if not config:
            config = dict()
        self._config = json.dumps(config)
        self._status = Environment.STATUS_ACTIVE

    @hybrid_property
    def config(self):
        return load_column(self._config)

    @config.setter
    def config(self, value):
        self._config = json.dumps(value)

    @hybrid_property
    def labels(self):
        return json.loads(self._labels)

    @labels.setter
    def labels(self, value):
        self._labels = json.dumps(value)

    @hybrid_property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value in Environment.VALID_STATUSES:
            self._status = value
        else:
            raise ValueError("'%s' is not a valid status for Environment" % value)

    @hybrid_property
    def cost_multiplier(self):
        return get_environment_fields_from_config(self, 'cost_multiplier')

    def cost(self, duration=None):
        if not duration:
            duration = self.maximum_lifetime
        return self.cost_multiplier * duration / 3600

    def __repr__(self):
        return self.name or "Unnamed environment"


class Instance(db.Model):
    STATE_QUEUEING = 'queueing'
    STATE_PROVISIONING = 'provisioning'
    STATE_STARTING = 'starting'
    STATE_RUNNING = 'running'
    STATE_DELETING = 'deleting'
    STATE_DELETED = 'deleted'
    STATE_FAILED = 'failed'

    VALID_STATES = (
        STATE_QUEUEING,
        STATE_PROVISIONING,
        STATE_STARTING,
        STATE_RUNNING,
        STATE_DELETING,
        STATE_DELETED,
        STATE_FAILED,
    )

    __tablename__ = 'instances'
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'))
    environment_id = db.Column(db.String(32), db.ForeignKey('environments.id'))
    name = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    provisioned_at = db.Column(db.DateTime)
    deprovisioned_at = db.Column(db.DateTime)
    errored = db.Column(db.Boolean, default=False)
    _state = db.Column('state', db.String(32))
    to_be_deleted = db.Column(db.Boolean, default=False)
    log_fetch_pending = db.Column(db.Boolean, default=False)
    error_msg = db.Column(db.String(256))
    _provisioning_config = db.Column('provisioning_config', db.Text)
    _instance_data = db.Column('instance_data', db.Text)

    def __init__(self, environment, user):
        self.id = uuid.uuid4().hex
        self.environment_id = environment.id
        self.environment = environment
        self.user_id = user.id
        self._state = Instance.STATE_QUEUEING

    @hybrid_property
    def instance_data(self):
        return load_column(self._instance_data)

    @instance_data.setter
    def instance_data(self, value):
        self._instance_data = json.dumps(value)

    @hybrid_property
    def provisioning_config(self):
        return load_column(self._provisioning_config)

    @provisioning_config.setter
    def provisioning_config(self, value):
        self._provisioning_config = json.dumps(value)

    @hybrid_property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value in Instance.VALID_STATES:
            self._state = value
        else:
            raise ValueError("'%s' is not a valid state" % value)

    @staticmethod
    def generate_name(prefix):
        return '%s%s-the-%s' % (prefix, names.get_first_name().lower(), random.choice(NAME_ADJECTIVES))


class InstanceLog(db.Model):
    __tablename__ = 'instance_logs'
    id = db.Column(db.String(32), primary_key=True)
    instance_id = db.Column(db.String(32), db.ForeignKey('instances.id'), index=True, unique=False)
    log_level = db.Column(db.String(8))
    log_type = db.Column(db.String(64))
    timestamp = db.Column(db.Float)
    message = db.Column(db.Text)

    def __init__(self, instance_id, log_level, log_type, timestamp, message):
        self.id = uuid.uuid4().hex
        self.instance_id = instance_id
        self.log_level = log_level
        self.log_type = log_type
        self.timestamp = timestamp
        self.message = message


class Lock(db.Model):
    __tablename__ = 'locks'

    id = db.Column(db.String(64), primary_key=True)
    owner = db.Column(db.String(64))
    acquired_at = db.Column(db.DateTime)

    def __init__(self, id, owner):
        self.id = id
        self.owner = owner
        self.acquired_at = datetime.datetime.utcnow()
