#!/usr/bin/python
import getpass
import itertools
import json
import os
import sys
import socket
import fcntl
import struct
import tempfile
import time

activate_this = '/webapps/pouta_blueprints/venv/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))
sys.path.append("/webapps/pouta_blueprints/source")

import yaml
from novaclient.v2 import client

config = yaml.load(open('/etc/pouta_blueprints/config.yaml'))
m2m_store = config['M2M_CREDENTIAL_STORE']


def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,
        struct.pack('256s', ifname[:15])
    )[20:24])

try:
    input = raw_input
except NameError:
    pass


def get_from_env_or_stdin(key, default=None, is_password=False):
    value = os.getenv(key)
    if not value:
        if is_password:
            value = getpass.getpass()
        else:
            value = input()
    return value

print("Initializing your Pouta Blueprints instance")
print("Setting OpenStack M2M (machine-to-machine) credentials")
print("Enter OpenStack M2M user")
os_user = get_from_env_or_stdin('OS_USERNAME')

print("Enter OpenStack M2M password")
os_password = get_from_env_or_stdin('OS_PASSWORD')

print("Enter OpenStack M2M tenant")
os_tenant_id = get_from_env_or_stdin('OS_TENANT_ID')

print("Enter OpenStack Keystone endpoint URL")
os_auth_url = get_from_env_or_stdin('OS_AUTH_URL')

m2m_credentials = {
    'OS_USERNAME': os_user,
    'OS_PASSWORD': os_password,
    'OS_TENANT_ID': os_tenant_id,
    'OS_AUTH_URL': os_auth_url
}
_, tmp_abs = tempfile.mkstemp()
json.dump(m2m_credentials, file(tmp_abs, "w"))

os.popen("sudo cp %s %s" % (tmp_abs, m2m_store))
os.popen("sudo chown pouta_blueprints %s" % m2m_store)
os.popen("sudo chmod 700 %s" % m2m_store)

nt = client.Client(os_user, os_password, os_tenant_id, os_auth_url, service_type="compute")
servers = [(x.id, x.addresses) for x in nt.servers.list()]
current_ip = get_ip_address("eth0")
current_server_id = None
for server_id, server_ips in servers:
    ips = [z for z in itertools.chain(*[[y['addr'] for y in x] for x in server_ips.values()])]
    if current_ip in ips:
        current_server_id = server_id

if not current_server_id:
    print("This instance of Pouta Blueprints seems not to run on the OpenStack environment associated with the given credentials")
    sys.exit(1)

print("Creating persistent volume for database")
volume = nt.volumes.create(50, display_name="Pouta Blueprints DB")

print("Attaching volume")
while True:
    try:
        nt.volumes.create_server_volume(current_server_id, volume.id, "/dev/vdc")
    except:
        print("volume not ready, sleeping a while")
        time.sleep(5)
    else:
        break

device = None
while True:
    if os.path.exists('/dev/vdc'):
        device = '/dev/vdc'
        break
    else:
        print("attached device not ready, sleeping a while")
        time.sleep(5)

os.popen("sudo mkdir /mnt/pb_db")
print("Creating filesystem on volume")
os.popen("sudo mkfs.ext4 /dev/vdc")
os.popen("sudo mount /dev/vdc /mnt/pb_db")
os.popen("sudo chown -R pouta_blueprints /mnt/pb_db")
print("Create DB as pouta_blueprints user")
os.popen("sudo -u pouta_blueprints /webapps/pouta_blueprints/venv/bin/python /webapps/pouta_blueprints/source/manage.py")
print("Restart services")
os.popen("sudo supervisorctl restart all")
