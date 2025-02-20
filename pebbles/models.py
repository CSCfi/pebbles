import hashlib
import importlib
import inspect
import json
import logging
import random
import secrets
import string
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jose import jwt, JWTError, ExpiredSignatureError
from jose.exceptions import JWTClaimsError, JWSError
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.schema import MetaData

import pebbles
from pebbles.app import db, bcrypt
from pebbles.utils import get_application_fields_from_config, read_list_from_text_file

PEBBLES_TAINT_KEY = 'pebbles.csc.fi/taint'

MAX_PSEUDONYM_LENGTH = 32
MAX_PASSWORD_LENGTH = 100
MAX_EMAIL_LENGTH = 128
MAX_NAME_LENGTH = 128
MAX_VARIABLE_KEY_LENGTH = 512
MAX_VARIABLE_VALUE_LENGTH = 512
MAX_MESSAGE_SUBJECT_LENGTH = 255
MAX_SERVICE_ANNOUNCEMENT_SUBJECT_LENGTH = 255

JWS_SIGNING_ALG = 'HS512'

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db.Model.metadata = MetaData(naming_convention=convention)

SESSION_NAME_MODIFIERS = [
    'dark', 'light', 'deep', 'faint', 'bright', 'beautifully', 'faded', 'vivid', 'pale', 'rich',
    'pure', 'gloriously',
]

SESSION_NAME_COLORS = [
    'red', 'green', 'blue', 'purple', 'orange', 'yellow', 'black', 'white', 'pink', 'cyan',
    'magenta', 'fuchsia', 'turquoise', 'coral', 'emerald', 'mauve', 'indigo', 'ruby', 'brown',
    'grey', 'lilac', 'beige', 'crimson', 'teal', 'maroon', 'olive', 'violet', 'silver', 'khaki',
]


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
    _annotations = db.Column('annotations', db.Text)
    application_sessions = db.relationship('ApplicationSession', backref='user', lazy='dynamic')
    workspace_memberships = db.relationship("WorkspaceMembership", back_populates="user", lazy='dynamic')
    deletion_requested_date = db.Column(db.DateTime, nullable=True)

    def __init__(self, ext_id, password=None, is_admin=False, email_id=None, expiry_ts=None, pseudonym=None,
                 workspace_quota=None, annotations=None):
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
        if annotations:
            self._annotations = json.dumps(annotations)

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
        return self.workspace_quota > 0 or len(self.get_owned_workspace_memberships()) > 0

    @hybrid_property
    def is_workspace_manager(self):
        # we are a workspace managerif we are mapped to be one
        return len(self.get_managed_workspace_memberships()) > 0

    @is_workspace_owner.setter
    def is_workspace_owner(self, value):
        raise RuntimeError('Set workspace owner status through workspace quota and membership')

    @hybrid_property
    def joining_ts(self):
        return self._joining_ts.timestamp()

    @joining_ts.setter
    def joining_ts(self, value):
        self._joining_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def expiry_ts(self):
        return self._expiry_ts.timestamp() if self._expiry_ts else None

    @expiry_ts.setter
    def expiry_ts(self, value):
        self._expiry_ts = datetime.fromtimestamp(value) if value else None

    @hybrid_property
    def last_login_ts(self):
        return self._last_login_ts.timestamp() if self._last_login_ts else None

    @last_login_ts.setter
    def last_login_ts(self, value):
        self._last_login_ts = datetime.fromtimestamp(value) if value else None

    @hybrid_property
    def annotations(self):
        if self._annotations:
            return load_column(self._annotations)
        else:
            return []

    @annotations.setter
    def annotations(self, value):
        if not value:
            self._annotations = None
        elif isinstance(value, list):
            self._annotations = json.dumps(value)
        else:
            raise RuntimeWarning('user annotations need to be a list of key value pairs')

    @hybrid_property
    def taints(self):
        return [a.get('value') for a in self.annotations if a.get('key') == PEBBLES_TAINT_KEY]

    def delete(self):
        if self.is_deleted:
            return
        self.ext_id = self.ext_id + datetime.now(timezone.utc).strftime("-%s")
        # Email_id is also renamed to allow users
        # to be deleted and invited again with same email_id
        if self.email_id:
            self.email_id = self.email_id + datetime.now(timezone.utc).strftime("-%s")
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
        return not self.is_deleted and self.is_active and not self.is_blocked and not self.has_expired()

    def get_owned_workspace_memberships(self):
        return [wm for wm in self.workspace_memberships if wm.is_owner and wm.workspace.status == 'active']

    def get_managed_workspace_memberships(self):
        return [wm for wm in self.workspace_memberships if wm.is_manager and wm.workspace.status == 'active']

    @staticmethod
    def verify_auth_token(token, app_secret):
        if not token:
            return None
        try:
            # explicitly pass the single algorithm for signing to avoid token forging by algorithm tampering
            data = jwt.decode(token, app_secret, algorithms=[JWS_SIGNING_ALG])
        except (ExpiredSignatureError):
            logging.debug('Token has expired "%s"', token)
            return None
        except (JWTError, JWSError, JWTClaimsError) as e:
            logging.warning('Possible hacking attempt "%s" with token "%s"', e, token)
            return None

        user = User.query.filter_by(id=data['id']).first()
        if user and user.can_login():
            return user

    def has_expired(self):
        # Only compare if expiry_ts has been set (skip zero/None)
        if self.expiry_ts and self.expiry_ts < time.time():
            return True
        return False

    def __repr__(self):
        return self.ext_id

    def __hash__(self):
        return hash(self.ext_id)


# Membership Object for many-to-many mapping
class WorkspaceMembership(db.Model):
    __tablename__ = 'workspace_memberships'
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'), primary_key=True)
    is_manager = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    user = db.relationship("User", back_populates="workspace_memberships")
    workspace = db.relationship("Workspace", back_populates="memberships")
    created_at = db.Column(db.DateTime, default=func.now())


class Workspace(db.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    STATUS_DELETED = 'deleted'

    VALID_STATUSES = (
        STATUS_ACTIVE,
        STATUS_ARCHIVED,
        STATUS_DELETED
    )

    # Membership Expiry Policies
    MEP_PERSISTENT = 'persistent'
    MEP_ACTIVITY_TIMEOUT = 'activity_timeout'

    VALID_MEMBERSHIP_EXPIRY_POLICIES = (
        MEP_PERSISTENT,
        MEP_ACTIVITY_TIMEOUT,
    )
    __tablename__ = 'workspaces'

    id = db.Column(db.String(32), primary_key=True)
    pseudonym = db.Column(db.String(MAX_PSEUDONYM_LENGTH), unique=True, nullable=False)
    name = db.Column(db.String(64))
    _join_code = db.Column('join_code', db.String(64))
    description = db.Column(db.Text)
    cluster = db.Column(db.String(32))
    # status when created is "active". Later there is option to be "archived".
    _status = db.Column('status', db.String(32), default=STATUS_ACTIVE)
    _create_ts = db.Column('create_ts', db.DateTime, default=func.now())
    _expiry_ts = db.Column(
        'expiry_ts',
        db.DateTime,
        default=lambda: datetime.fromtimestamp(time.time() + 6 * 30 * 24 * 3600)
    )
    memberships = db.relationship("WorkspaceMembership", back_populates="workspace", lazy='dynamic',
                                  cascade="all, delete-orphan")
    _membership_expiry_policy = db.Column('membership_expiry_policy', db.Text)
    _membership_join_policy = db.Column('membership_join_policy', db.Text)
    application_quota = db.Column(db.Integer, default=10)
    memory_limit_gib = db.Column(db.Integer, default=50)
    _config = db.Column('config', db.Text)
    contact = db.Column(db.Text)

    applications = db.relationship('Application', backref='workspace', lazy='dynamic')

    def __init__(self, name, description='', cluster=None, memory_limit_gib=50, config=None):
        self.id = uuid.uuid4().hex
        # Here we opportunistically create a pseudonym without actually checking the existing workspaces,
        # the probability of collision is low enough. There are 400 pseudonyms for all inhabitants on earth
        # with 36**8 alternatives
        self.pseudonym = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        self.name = name
        self.description = description
        self.join_code = name
        self.cluster = cluster
        # invoke the hybrid property accessor to convert provided config dict to json
        if config:
            self.config = config
        self.memory_limit_gib = memory_limit_gib
        self._status = Workspace.STATUS_ACTIVE
        self.membership_expiry_policy = dict(kind=Workspace.MEP_PERSISTENT)

    @hybrid_property
    def join_code(self):
        return self._join_code

    @join_code.setter
    def join_code(self, name):
        # pick a prefix from first characters in name
        prefix = ''.join(filter(
            lambda c: c in string.ascii_lowercase, name.lower().encode('ascii', 'ignore').decode()
        ))[:3]
        if prefix:
            prefix += '-'

        # append random characters
        random_chars = ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(8))
        self._join_code = prefix + random_chars

    @hybrid_property
    def create_ts(self):
        return self._create_ts.timestamp()

    @create_ts.setter
    def create_ts(self, value):
        self._create_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def expiry_ts(self):
        return self._expiry_ts.timestamp() if self._expiry_ts else None

    @expiry_ts.setter
    def expiry_ts(self, value):
        self._expiry_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if value in Workspace.VALID_STATUSES:
            self._status = value
        else:
            raise ValueError("'%s' is not a valid status for Workspace" % value)

    def has_expired(self):
        # Only compare if expiry_ts has been set (skip zero/None)
        return self.expiry_ts and self.expiry_ts < time.time()

    @hybrid_property
    def config(self):
        return load_column(self._config)

    @config.setter
    def config(self, value):
        self._config = json.dumps(value)

    @hybrid_property
    def membership_expiry_policy(self):
        return load_column(self._membership_expiry_policy)

    @membership_expiry_policy.setter
    def membership_expiry_policy(self, value):
        error = Workspace.check_membership_expiry_policy(value)
        if error:
            raise RuntimeWarning('Invalid membership_expiry_policy: "%s"' % error)
        else:
            self._membership_expiry_policy = json.dumps(value)

    @hybrid_property
    def membership_join_policy(self):
        return load_column(self._membership_join_policy)

    @hybrid_property
    def allow_expiry_extension(self):
        return self.config.get('allow_expiry_extension', False)

    @membership_join_policy.setter
    def membership_join_policy(self, value):
        error = Workspace.check_membership_join_policy(value)
        if error:
            raise RuntimeWarning('Invalid membership_expiry_policy: "%s"' % error)
        else:
            self._membership_join_policy = json.dumps(value)

    @staticmethod
    def check_membership_expiry_policy(mep):
        """ Return validation errors for given membership expiry policy or None if successful """
        if not isinstance(mep, dict):
            return 'membership expiry policy must be a dict'
        kind = mep.get('kind')
        if kind not in Workspace.VALID_MEMBERSHIP_EXPIRY_POLICIES:
            return 'Invalid membership expiry policy kind: %s' % kind

        if kind == Workspace.MEP_ACTIVITY_TIMEOUT:
            timeout_days = mep.get('timeout_days')
            if type(timeout_days) not in (int, float):
                return 'Invalid type for "timeout_days": %s, %s' % (timeout_days, type(timeout_days))
            if timeout_days <= 0:
                return 'Invalid "timeout_days": %s' % timeout_days

        return None

    @staticmethod
    def check_membership_join_policy(mjp):
        """ Return validation errors for given membership expiry policy or None if successful """
        if mjp is None:
            return None
        if not isinstance(mjp, dict):
            return 'policy must be a dict'

        if not set(mjp.keys()).issubset({'tolerations', }):
            return 'Extra keys in policy %s' % mjp
        tolerations = mjp.get('tolerations')
        if tolerations and not isinstance(tolerations, list):
            return 'tolerations is not a list'

        return None


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.String(32), primary_key=True)
    broadcasted = db.Column(db.DateTime)
    subject = db.Column(db.String(MAX_MESSAGE_SUBJECT_LENGTH))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=func.now())

    def __init__(self, subject, message):
        self.id = uuid.uuid4().hex
        self.broadcasted = datetime.now(timezone.utc)
        self.subject = subject
        self.message = message


class ServiceAnnouncement(db.Model):
    __tablename__ = 'service_announcements'

    id = db.Column(db.String(32), primary_key=True)
    subject = db.Column(db.String(MAX_SERVICE_ANNOUNCEMENT_SUBJECT_LENGTH))
    content = db.Column(db.Text)
    level = db.Column(db.Integer, default=0)
    targets = db.Column(db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=func.now())

    def __init__(self, subject, content, level, targets, is_enabled, is_public):
        self.id = uuid.uuid4().hex
        self.subject = subject
        self.content = content
        self.level = level
        self.targets = targets
        self.is_enabled = is_enabled
        self.is_public = is_public


class ApplicationTemplate(db.Model):
    ENVIRONMENT_TYPES = ['jupyter', 'rstudio', 'generic']

    __tablename__ = 'application_templates'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    description = db.Column(db.Text)
    application_type = db.Column(db.String(MAX_NAME_LENGTH))
    _base_config = db.Column('base_config', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    _attribute_limits = db.Column('attribute_limits', db.Text)
    created_at = db.Column(db.DateTime, default=func.now())

    def __init__(self, name=None, description=None, application_type='generic', attribute_limits=None,
                 base_config=None, is_enabled=False):
        self.id = uuid.uuid4().hex
        self.name = name
        self.description = description
        if application_type not in ApplicationTemplate.ENVIRONMENT_TYPES:
            raise ValueError('Illegal application type: "%s"' % application_type)
        self.application_type = application_type
        self._attribute_limits = json.dumps(attribute_limits)
        self._base_config = json.dumps(base_config)
        self.is_enabled = is_enabled

    @hybrid_property
    def base_config(self):
        return load_column(self._base_config)

    @base_config.setter
    def base_config(self, value):
        self._base_config = json.dumps(value)

    @hybrid_property
    def attribute_limits(self):
        return load_column(self._attribute_limits)

    @attribute_limits.setter
    def attribute_limits(self, value):
        self._attribute_limits = json.dumps(value)


class Application(db.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    STATUS_DELETED = 'deleted'

    VALID_STATUSES = (
        STATUS_ACTIVE,
        STATUS_ARCHIVED,
        STATUS_DELETED,
    )

    __tablename__ = 'applications'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    description = db.Column(db.Text)
    template_id = db.Column(db.String(32), db.ForeignKey('application_templates.id'))
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'))
    _labels = db.Column('labels', db.Text)
    application_type = db.Column(db.String(MAX_NAME_LENGTH))
    maximum_lifetime = db.Column(db.Integer)
    _base_config = db.Column('base_config', db.Text)
    _config = db.Column('config', db.Text)
    _attribute_limits = db.Column('attribute_limits', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    expiry_time = db.Column(db.DateTime)
    application_sessions = db.relationship('ApplicationSession', backref='application', lazy='dynamic')
    # status when created is "active". Later there are options to be "archived" or "deleted".
    _status = db.Column('status', db.String(32), default='active')
    created_at = db.Column(db.DateTime, default=func.now())

    def __init__(self, name=None, description=None, template_id=None, workspace_id=None, labels=None,
                 maximum_lifetime=3600, is_enabled=False, config=None,
                 base_config=None, attribute_limits=None, application_type=None):
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
        self._status = Application.STATUS_ACTIVE
        if not base_config:
            base_config = dict()
        self._base_config = json.dumps(base_config)
        if not attribute_limits:
            attribute_limits = []
        self._attribute_limits = json.dumps(attribute_limits)
        self.application_type = application_type

    @hybrid_property
    def base_config(self):
        return load_column(self._base_config)

    @base_config.setter
    def base_config(self, value):
        self._base_config = json.dumps(value)

    @hybrid_property
    def config(self):
        return load_column(self._config)

    @config.setter
    def config(self, value):
        self._config = json.dumps(value)

    @hybrid_property
    def attribute_limits(self):
        return load_column(self._attribute_limits)

    @attribute_limits.setter
    def attribute_limits(self, value):
        self._attribute_limits = json.dumps(value)

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
        if value in Application.VALID_STATUSES:
            self._status = value
        else:
            raise ValueError("'%s' is not a valid status for Application" % value)

    @hybrid_property
    def cost_multiplier(self):
        return get_application_fields_from_config(self, 'cost_multiplier')

    def cost(self, duration=None):
        if not duration:
            duration = self.maximum_lifetime
        return self.cost_multiplier * duration / 3600

    def replace_application_image(self, old_image: str, new_image: str) -> bool:
        """ replace image in both base_config and config """
        change = False
        if self.config.get('image_url', '') == old_image:
            # hybrid property needs to be assigned as a new dict
            config = self.config
            config['image_url'] = new_image
            self.config = config
            change = True
        if self.base_config.get('image', '') == old_image:
            # hybrid property needs to be assigned as a new dict
            base_config = self.base_config
            base_config['image'] = new_image
            self.base_config = base_config
            change = True
        return change

    def __repr__(self):
        return self.name or "Unnamed application"


class ApplicationSession(db.Model):
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

    __tablename__ = 'application_sessions'
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'))
    application_id = db.Column(db.String(32), db.ForeignKey('applications.id'))
    name = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=func.now())
    provisioned_at = db.Column(db.DateTime)
    deprovisioned_at = db.Column(db.DateTime)
    errored = db.Column(db.Boolean, default=False)
    _state = db.Column('state', db.String(32))
    to_be_deleted = db.Column(db.Boolean, default=False)
    log_fetch_pending = db.Column(db.Boolean, default=False)
    error_msg = db.Column(db.String(256))
    _provisioning_config = db.Column('provisioning_config', db.Text)
    _session_data = db.Column('session_data', db.Text)

    def __init__(self, application, user):
        self.id = uuid.uuid4().hex
        self.application_id = application.id
        self.user_id = user.id
        self._state = ApplicationSession.STATE_QUEUEING

    @hybrid_property
    def session_data(self):
        return load_column(self._session_data)

    @session_data.setter
    def session_data(self, value):
        self._session_data = json.dumps(value)

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
        if value in ApplicationSession.VALID_STATES:
            self._state = value
        else:
            raise ValueError("'%s' is not a valid state" % value)

    @staticmethod
    def generate_name(prefix):
        plant_names = read_list_from_text_file(f'{Path(__file__).parent}/data/plantnames.txt')
        return '%s%s-%s-%s' % (
            prefix,
            random.choice(SESSION_NAME_MODIFIERS),
            random.choice(SESSION_NAME_COLORS),
            random.choice(plant_names)
        )

    def get_age_secs(self):
        if self.provisioned_at:
            # We still use naive datetime objects in SQLAlchemy due to unit tests running on SQLite, so we have
            # to construct a naive UTC datetime from datetime.now(timezone.utc) to be able to get deltas
            utcnow = datetime.now(timezone.utc).replace(tzinfo=None)
            return (utcnow - self.provisioned_at).total_seconds()
        else:
            return 0


class ApplicationSessionLog(db.Model):
    __tablename__ = 'application_session_logs'
    id = db.Column(db.String(32), primary_key=True)
    application_session_id = db.Column(db.String(32), db.ForeignKey('application_sessions.id'), index=True,
                                       unique=False)
    log_level = db.Column(db.String(8))
    log_type = db.Column(db.String(64))
    timestamp = db.Column(db.Float)
    message = db.Column(db.Text)

    def __init__(self, application_session_id, log_level, log_type, timestamp, message):
        self.id = uuid.uuid4().hex
        self.application_session_id = application_session_id
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
        self.acquired_at = datetime.now(timezone.utc)


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.String(64), primary_key=True)
    target = db.Column(db.String(64), nullable=False)
    source = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(64), nullable=False, index=True)
    _data = db.Column('data', db.Text)
    _first_seen_ts = db.Column('first_seen_ts', db.DateTime, default=func.now())
    _last_seen_ts = db.Column('last_seen_ts', db.DateTime, default=func.now())

    def __init__(self, id, target, source, status, data):
        self.id = id if id else Alert.generate_alert_id(target, source, data)
        self.target = target
        self.source = source
        self.status = status
        self.data = data

    @staticmethod
    def generate_alert_id(target, source, data):
        id_bytes = target.encode() + source.encode() + json.dumps(data).encode()
        return hashlib.sha3_224(id_bytes).hexdigest()

    @hybrid_property
    def last_seen_ts(self):
        return self._last_seen_ts.timestamp()

    @last_seen_ts.setter
    def last_seen_ts(self, value):
        self._last_seen_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def first_seen_ts(self):
        return self._first_seen_ts.timestamp()

    @first_seen_ts.setter
    def first_seen_ts(self, value):
        self._first_seen_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def data(self):
        return load_column(self._data)

    @data.setter
    def data(self, value):
        self._data = json.dumps(value)


class Task(db.Model):
    STATE_NEW = 'new'
    STATE_PROCESSING = 'processing'
    STATE_FINISHED = 'finished'
    STATE_FAILED = 'failed'

    VALID_STATES = (
        STATE_NEW,
        STATE_PROCESSING,
        STATE_FINISHED,
        STATE_FAILED,
    )

    KIND_WORKSPACE_VOLUME_BACKUP = 'workspace_volume_backup'
    KIND_WORKSPACE_VOLUME_RESTORE = 'workspace_volume_restore'

    VALID_KINDS = (
        KIND_WORKSPACE_VOLUME_BACKUP,
        KIND_WORKSPACE_VOLUME_RESTORE,
    )

    __tablename__ = 'tasks'

    id = db.Column(db.String(64), primary_key=True)
    _kind = db.Column('kind', db.String(32), primary_key=True)
    _state = db.Column('state', db.String(32))
    _data = db.Column('data', db.Text)
    _create_ts = db.Column('create_ts', db.DateTime, default=func.now())
    _complete_ts = db.Column('complete_ts', db.DateTime)
    _update_ts = db.Column('update_ts', db.DateTime, default=func.now())
    _results = db.Column('results', db.Text)

    def __init__(self, kind, state, data):
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.state = state
        self.data = data

    @hybrid_property
    def kind(self):
        return self._kind

    @kind.setter
    def kind(self, value):
        if value in Task.VALID_KINDS:
            self._kind = value
        else:
            raise ValueError("'%s' is not a valid kind for Task" % value)

    @hybrid_property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value in Task.VALID_STATES:
            self._state = value
        else:
            raise ValueError("'%s' is not a valid state for Task" % value)

    @hybrid_property
    def results(self):
        if self._results:
            return load_column(self._results)
        return []

    @results.setter
    def results(self, value):
        self._results = json.dumps(value)

    @hybrid_property
    def data(self):
        return load_column(self._data)

    @data.setter
    def data(self, value):
        self._data = json.dumps(value)

    @hybrid_property
    def create_ts(self):
        return self._create_ts.timestamp()

    @create_ts.setter
    def create_ts(self, value):
        self._create_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def complete_ts(self):
        return self._complete_ts.timestamp()

    @complete_ts.setter
    def complete_ts(self, value):
        self._complete_ts = datetime.fromtimestamp(value)

    @hybrid_property
    def update_ts(self):
        return self._update_ts.timestamp()

    @update_ts.setter
    def update_ts(self, value):
        self._update_ts = datetime.fromtimestamp(value)


class CustomImage(db.Model):
    STATE_NEW = 'new'
    STATE_BUILDING = 'building'
    STATE_COMPLETED = 'completed'
    STATE_FAILED = 'failed'
    STATE_DELETED = 'deleted'

    VALID_STATES = (
        STATE_NEW,
        STATE_BUILDING,
        STATE_COMPLETED,
        STATE_FAILED,
        STATE_DELETED,
    )

    __tablename__ = 'custom_images'
    id = db.Column(db.String(32), primary_key=True)
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'))
    name = db.Column(db.String(64))
    tag = db.Column(db.String(64))
    _definition = db.Column('definition', db.Text)
    dockerfile = db.Column(db.Text)
    build_system_id = db.Column(db.String(64))
    build_system_output = db.Column(db.Text)
    url = db.Column(db.String(256))

    started_at = db.Column('started_at', db.DateTime)
    completed_at = db.Column('completed_at', db.DateTime)
    _state = db.Column('state', db.String(32))
    to_be_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column('created_at', db.DateTime, default=func.now())
    updated_at = db.Column('updated_at', db.DateTime, onupdate=func.now())

    def __init__(self, id=None, workspace_id=None, name=None, tag=None, dockerfile=None, ):
        self.id = id if id else uuid.uuid4().hex
        self.workspace_id = workspace_id
        self.name = name
        self.tag = tag
        self.dockerfile = dockerfile
        self.state = self.STATE_NEW

    @hybrid_property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if value in CustomImage.VALID_STATES:
            self._state = value
        else:
            raise ValueError("'%s' is not a valid state" % value)

    @hybrid_property
    def definition(self):
        return load_column(self._definition)

    @definition.setter
    def definition(self, value):
        self._definition = json.dumps(value)


def load_yaml(yaml_data):
    """
    A function to load annotated yaml data into the database.
    Example can be found in devel_dataset.yaml
    """

    # callback function for constructing custom objects from yaml
    def model_object_constructor(loader, node):
        values = loader.construct_mapping(node, deep=True)
        # figure out class and use its constructor
        cls = getattr(
            importlib.import_module('pebbles.models'),
            node.tag[1:],
            None
        )
        # we could not find a matching class, return value dict
        if not cls:
            return values

        if 'id' in values:
            id = values.pop('id')
            obj = cls(**values)
            obj.id = id
        else:
            obj = cls(**values)

        return obj

    # wire custom construction for all pebbles.models classes
    for class_info in inspect.getmembers(pebbles.models, inspect.isclass):
        yaml.add_constructor('!' + class_info[0], model_object_constructor)

    data = yaml.unsafe_load(yaml_data)

    return data


def list_active_applications() -> list[Application]:
    """List applications in active state in valid workspaces"""
    applications = Application.query.filter(Application.status != 'deleted').all()
    return list(filter(lambda a: a.workspace.status == 'active' and not a.workspace.has_expired(), applications))
