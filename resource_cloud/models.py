from flask.ext.bcrypt import generate_password_hash, check_password_hash
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
import uuid
import datetime
from resource_cloud.server import db, app

MAX_PASSWORD_LENGTH = 100


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    visual_id = db.Column(db.String(32))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(MAX_PASSWORD_LENGTH))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)

    def __init__(self, email, password=None, is_admin=False):
        self.visual_id = uuid.uuid4().hex
        self.email = email.lower()
        self.is_admin = is_admin
        if password:
            self.set_password(password)
            self.is_active = True
        else:
            self.set_password(uuid.uuid4().hex)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def generate_auth_token(self, expires_in=3600):
        s = Serializer(app.config['SECRET_KEY'], expires_in=expires_in)
        return s.dumps({'id': self.id}).decode('utf-8')

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return None
        return User.query.get(data['id'])

    def __repr__(self):
        return '<User %r>' % self.email


class Keypair(db.Model):
    __tablename__ = 'keypairs'

    id = db.Column(db.Integer, primary_key=True)
    visual_id = db.Column(db.String(32))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    public_key = db.Column(db.String(450))

    def __init__(self):
        self.visual_id = uuid.uuid4().hex


class ActivationToken(db.Model):
    __tablename__ = 'activation_tokens'

    token = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __init__(self, user):
        self.user_id = user.id
        self.token = uuid.uuid4().hex


class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    visual_id = db.Column(db.String(32))
    name = db.Column(db.String(64))
    config = db.Column(db.Text)

    def __init__(self):
        self.visual_id = uuid.uuid4().hex


class ProvisionedResource(db.Model):
    __tablename__ = 'provisioned_resources'
    id = db.Column(db.Integer, primary_key=True)
    visual_id = db.Column(db.String(32))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'))
    name = db.Column(db.String(64), unique=True)
    provisioned_at = db.Column(db.DateTime)
    state = db.Column(db.String(32))

    def __init__(self, resource_id, user_id):
        self.resource_id = resource_id
        self.user_id = user_id
        self.visual_id = uuid.uuid4().hex
        self.provisioned_at = datetime.datetime.utcnow()
        self.state = 'starting'


class SystemToken(db.Model):
    __tablename__ = 'system_tokens'

    token = db.Column(db.String(32), primary_key=True)
    role = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)

    def __init__(self, role):
        self.role = role
        self.token = uuid.uuid4().hex
        self.created_at = datetime.datetime.utcnow()

    @staticmethod
    def verify(token):
        return SystemToken.query.filter_by(token=token).first()


db.create_all()
