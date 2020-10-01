import datetime
import json
import random
import secrets
import string
import uuid

import names
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.orm import backref
from sqlalchemy.schema import MetaData

from pebbles.utils import get_full_environment_config, get_environment_fields_from_config

MAX_USER_PSEUDONYM_LENGTH = 32
MAX_PASSWORD_LENGTH = 100
MAX_EMAIL_LENGTH = 128
MAX_NAME_LENGTH = 128
MAX_VARIABLE_KEY_LENGTH = 512
MAX_VARIABLE_VALUE_LENGTH = 512
MAX_MESSAGE_SUBJECT_LENGTH = 255

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
    # eppn is manadatory and database objects are retrieved based on eppn
    _eppn = db.Column('eppn', db.String(MAX_EMAIL_LENGTH), unique=True)
    # email_id field is used only for sending emails.
    _email_id = db.Column('email_id', db.String(MAX_EMAIL_LENGTH))
    pseudonym = db.Column(db.String(MAX_USER_PSEUDONYM_LENGTH), unique=True, nullable=False)
    password = db.Column(db.String(MAX_PASSWORD_LENGTH))
    joining_date = db.Column(db.DateTime)
    expiry_date = db.Column(db.DateTime)
    is_admin = db.Column(db.Boolean, default=False)
    is_workspace_owner = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    latest_seen_message_ts = db.Column(db.DateTime)
    workspace_quota = db.Column(db.Integer, default=0)
    environment_quota = db.Column(db.Integer, default=0)
    instances = db.relationship('Instance', backref='user', lazy='dynamic')
    activation_tokens = db.relationship('ActivationToken', backref='user', lazy='dynamic')
    workspaces = db.relationship("WorkspaceUserAssociation", back_populates="user", lazy="dynamic")

    def __init__(self, eppn, password=None, is_admin=False, email_id=None, expiry_date=None, pseudonym=None):
        self.id = uuid.uuid4().hex
        self.eppn = eppn
        self.is_admin = is_admin
        self.joining_date = datetime.datetime.utcnow()
        self.expiry_date = expiry_date
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

    def __eq__(self, other):
        return self.id == other.id

    @hybrid_property
    def eppn(self):
        return self._eppn.lower()

    @eppn.setter
    def eppn(self, value):
        self._eppn = value.lower()

    @eppn.comparator
    def eppn(cls):
        return CaseInsensitiveComparator(cls._eppn)

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

    def delete(self):
        if self.is_deleted:
            return
        self.eppn = self.eppn + datetime.datetime.utcnow().strftime("-%s")
        # Email_id is also renamed to allow users
        # to be deleted and invited again with same email_id
        if self.email_id:
            self.email_id = self.email_id + datetime.datetime.utcnow().strftime("-%s")
        self.activation_tokens.delete()
        self.is_deleted = True
        self.is_active = False

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        if self.can_login():
            return bcrypt.check_password_hash(self.password, password)

    def generate_auth_token(self, app_secret, expires_in=43200):
        s = Serializer(app_secret, expires_in=expires_in)
        return s.dumps({'id': self.id}).decode('utf-8')

    def can_login(self):
        return not self.is_deleted and self.is_active and not self.is_blocked

    @hybrid_property
    def managed_workspaces(self):
        workspaces = []
        workspace_user_objs = WorkspaceUserAssociation.query.filter_by(user_id=self.id, manager=True).all()
        for workspace_user_obj in workspace_user_objs:
            workspaces.append(workspace_user_obj.workspace)
        return workspaces

    @staticmethod
    def verify_auth_token(token, app_secret):
        s = Serializer(app_secret)
        try:
            data = s.loads(token)
        except:
            return None
        user = User.query.get(data['id'])
        if user and user.can_login():
            return user

    def __repr__(self):
        return self.eppn

    def __hash__(self):
        return hash(self.eppn)


workspace_banned_user = db.Table(  # Secondary Table for many-to-many mapping
    'workspaces_banned_users',
    db.Column('workspace_id', db.String(32), db.ForeignKey('workspaces.id')),
    db.Column('user_id', db.String(32), db.ForeignKey('users.id')), db.PrimaryKeyConstraint('workspace_id', 'user_id')
)


class WorkspaceUserAssociation(db.Model):  # Association Object for many-to-many mapping
    __tablename__ = 'workspaces_users_association'
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'), primary_key=True)
    manager = db.Column(db.Boolean, default=False)
    owner = db.Column(db.Boolean, default=False)
    user = db.relationship("User", back_populates="workspaces")
    workspace = db.relationship("Workspace", back_populates="users")


class Workspace(db.Model):
    STATE_ACTIVE = 'active'
    STATE_ARCHIVED = 'archived'
    STATE_DELETED = 'deleted'

    VALID_STATES = (
        STATE_ACTIVE,
        STATE_ARCHIVED,
        STATE_DELETED
    )
    __tablename__ = 'workspaces'

    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(32))
    _join_code = db.Column(db.String(64))
    description = db.Column(db.Text)
    # current_status when created is "active". Later there is option to be "archived".
    _current_status = db.Column('current_status', db.String(32), default='active')
    users = db.relationship("WorkspaceUserAssociation", back_populates="workspace", lazy='dynamic',
                            cascade="all, delete-orphan")
    banned_users = db.relationship('User', secondary=workspace_banned_user,
                                   backref=backref('banned_workspaces', lazy="dynamic"), lazy='dynamic')
    environments = db.relationship('Environment', backref='workspace', lazy='dynamic')

    def __init__(self, name):
        self.id = uuid.uuid4().hex
        self.name = name
        self.join_code = name
        self._current_status = Workspace.STATE_ACTIVE

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
    def current_status(self):
        return self._current_status

    @current_status.setter
    def current_status(self, value):
        if value in Workspace.VALID_STATES:
            self._current_status = value
        else:
            raise ValueError("'%s' is not a valid state for Workspaces" % value)


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.String(32), primary_key=True)
    broadcasted = db.Column(db.DateTime)
    subject = db.Column(db.String(MAX_MESSAGE_SUBJECT_LENGTH))
    message = db.Column(db.Text)

    def __init__(self):
        self.id = uuid.uuid4().hex
        self.broadcasted = datetime.datetime.utcnow()


class ActivationToken(db.Model):
    __tablename__ = 'activation_tokens'

    token = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'))

    def __init__(self, user):
        self.token = uuid.uuid4().hex
        self.user_id = user.id


class EnvironmentTemplate(db.Model):
    __tablename__ = 'environment_templates'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    _config = db.Column('config', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    cluster = db.Column(db.String(32))
    environments = db.relationship('Environment', backref='template', lazy='dynamic')
    _environment_schema = db.Column('environment_schema', db.Text)
    _environment_form = db.Column('environment_form', db.Text)
    _environment_model = db.Column('environment_model', db.Text)
    _allowed_attrs = db.Column('allowed_attrs', db.Text)

    def __init__(self):
        self.id = uuid.uuid4().hex

    @hybrid_property
    def config(self):
        return load_column(self._config)

    @config.setter
    def config(self, value):
        self._config = json.dumps(value)

    @hybrid_property
    def environment_schema(self):
        return load_column(self._environment_schema)

    @environment_schema.setter
    def environment_schema(self, value):
        self._environment_schema = json.dumps(value)

    @hybrid_property
    def environment_form(self):
        return load_column(self._environment_form)

    @environment_form.setter
    def environment_form(self, value):
        self._environment_form = json.dumps(value)

    @hybrid_property
    def environment_model(self):
        return load_column(self._environment_model)

    @environment_model.setter
    def environment_model(self, value):
        self._environment_model = json.dumps(value)

    @hybrid_property
    def allowed_attrs(self):
        return load_column(self._allowed_attrs)

    @allowed_attrs.setter
    def allowed_attrs(self, value):
        self._allowed_attrs = json.dumps(value)


class Environment(db.Model):
    STATE_ACTIVE = 'active'
    STATE_ARCHIVED = 'archived'
    STATE_DELETED = 'deleted'

    VALID_STATES = (
        STATE_ACTIVE,
        STATE_ARCHIVED,
        STATE_DELETED,
    )

    __tablename__ = 'environments'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    template_id = db.Column(db.String(32), db.ForeignKey('environment_templates.id'))
    _config = db.Column('config', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    expiry_time = db.Column(db.DateTime)
    instances = db.relationship('Instance', backref='environment', lazy='dynamic')
    workspace_id = db.Column(db.String(32), db.ForeignKey('workspaces.id'))
    # current_status when created is "active". Later there are options to be "archived" or "deleted".
    _current_status = db.Column('current_status', db.String(32), default='active')

    def __init__(self):
        self.id = uuid.uuid4().hex
        self._current_status = Environment.STATE_ACTIVE

    @hybrid_property
    def config(self):
        return load_column(self._config)

    @config.setter
    def config(self, value):
        self._config = json.dumps(value)

    # 'full_config' property of Environment model will take the template attributes into account too
    @hybrid_property
    def full_config(self):
        return get_full_environment_config(self)

    @hybrid_property
    def current_status(self):
        return self._current_status

    @current_status.setter
    def current_status(self, value):
        if value in Environment.VALID_STATES:
            self._current_status = value
        else:
            raise ValueError("'%s' is not a valid status for Environment" % value)

    @hybrid_property
    def maximum_lifetime(self):
        return get_environment_fields_from_config(self, 'maximum_lifetime')

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
    error_msg = db.Column(db.String(256))
    _instance_data = db.Column('instance_data', db.Text)

    def __init__(self, environment, user):
        self.id = uuid.uuid4().hex
        self.environment_id = environment.id
        self.environment = environment
        self.user_id = user.id
        self._state = Instance.STATE_QUEUEING

    @hybrid_property
    def runtime(self):
        if not self.provisioned_at:
            return 0.0

        if not self.deprovisioned_at:
            diff = datetime.datetime.utcnow() - self.provisioned_at
        else:
            diff = self.deprovisioned_at - self.provisioned_at

        return diff.total_seconds()

    @hybrid_property
    def instance_data(self):
        return load_column(self._instance_data)

    @instance_data.setter
    def instance_data(self, value):
        self._instance_data = json.dumps(value)

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

    def __init__(self, instance_id):
        self.id = uuid.uuid4().hex
        self.instance_id = instance_id


class Lock(db.Model):
    __tablename__ = 'locks'

    id = db.Column(db.String(64), primary_key=True, unique=True)
    owner = db.Column(db.String(64))
    acquired_at = db.Column(db.DateTime)

    def __init__(self, id, owner):
        self.id = id
        self.owner = owner
        self.acquired_at = datetime.datetime.utcnow()


class NamespacedKeyValue(db.Model):
    """ Stores key/value pair data, separated by namespaces
        This model should be initialized by providing namespace and key as mandatory arguments.
        It is highly recommended to have a schema for the JSON value field,
        and provide it during model initialization.
    """
    __tablename__ = 'namespaced_keyvalues'

    namespace = db.Column(db.String(32), primary_key=True)
    key = db.Column(db.String(128), primary_key=True)
    _value = db.Column(db.Text)
    _schema = db.Column(db.Text)
    created_ts = db.Column(db.Float)
    updated_ts = db.Column(db.Float)

    def __init__(self, namespace, key, schema=None):
        self.namespace = namespace
        self.key = key
        self.schema = schema

    @classmethod
    def str_to_bool(cls, val):
        """ Convert the string into boolean.
            Useful when value comes from UI and becomes True even if False
            By default, this function shall return False
        """
        if val:
            val = val.lower()
            if val in ('true', u'true', '1'):
                return True
        return False

    @hybrid_property
    def schema(self):
        return load_column(self._schema)

    @schema.setter
    def schema(self, schema):
        self._schema = json.dumps(schema)

    @hybrid_property
    def value(self):
        return load_column(self._value)

    @value.setter
    def value(self, val):
        if self.schema:
            try:
                schema_obj = self.schema['properties']
                required_fields = self.schema['required']
            except:
                raise KeyError('Incorrect Schema')
            for field in schema_obj:
                field_type = schema_obj[field]['type']
                if field not in val:
                    raise KeyError('Field %s does not exist in value object' % field)
                if not val[field] and field in required_fields and val[field] not in (0, False):
                    raise ValueError('Empty value found for required field %s' % field)
                try:
                    if field_type == "integer":
                        val[field] = int(val[field])
                    elif field_type == "boolean":
                        if type(val[field]) in (str,):
                            val[field] = NamespacedKeyValue.str_to_bool(val[field])
                        else:
                            val[field] = bool(val[field])
                    else:
                        val[field] = str(val[field])
                except:
                    raise TypeError('Field %s should be of type %s, found %s ' % (field, field_type, type(val[field])))
        self._value = json.dumps(val)
