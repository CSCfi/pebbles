# Flask configuration
DEBUG = True
SECRET_KEY = 'change_me'
WTF_CSRF_ENABLED = False
SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/change_me.db'

# Messaging
MESSAGE_QUEUE_URI = 'redis://localhost:6379/0'
