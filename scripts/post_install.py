import sys
import getpass

activate_this = '/webapps/pouta_blueprints/venv/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))

sys.path.append("/webapps/pouta_blueprints/source")

try:
    input = raw_input
except NameError:
    pass


from pouta_blueprints import server
from pouta_blueprints.views import create_first_user

print("Creating super user")
print("Enter email for super user:")
su_email = input()
print("Enter password for super user:")
su_password = getpass.getpass()

create_first_user(su_email, su_password)
