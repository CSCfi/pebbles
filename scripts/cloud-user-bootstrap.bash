#!/bin/bash

set -e
set -x

if ! id | grep "(docker)" > /dev/null; then
  if ! getent group docker > /dev/null; then
    sudo groupadd -r docker
  fi
  sudo usermod -a -G docker $USER
  echo ""
  echo "Log out and log in again to make docker group effective for $USER, then run me again"
  echo ""
  exit 0
fi

sudo aptitude update
sudo aptitude install -y git build-essential python-dev python-setuptools
sudo easy_install pip
sudo pip install ansible==1.8.4

PB_BRANCH=wip/remote_deployment_v2
PB_REPO=https://github.com/CSC-IT-Center-for-Science/pouta-blueprints

pb_temp=$(mktemp -d)

git clone --branch $PB_BRANCH $PB_REPO $pb_temp/git

cat > $HOME/pb_ansible_inventory << END_AI
[docker_host]
localhost ansible_connection=local
END_AI

# create a shared secret for both containers
application_secret_key=$(openssl rand -base64 32)

# figure out the public ip
public_ipv4=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

export ANSIBLE_HOST_KEY_CHECKING=0
export PYTHONUNBUFFERED=1
ansible-playbook -i $HOME/pb_ansible_inventory ansible/playbook.yml\
 -e deploy_mode=docker \
 -e application_secret_key=$application_secret_key \
 -e public_ipv4=$public_ipv4

rm -rf $pb_temp

