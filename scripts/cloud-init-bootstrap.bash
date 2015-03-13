#!/bin/bash

PB_BRANCH=wip/remote_deployment
PB_REPO=https://github.com/CSC-IT-Center-for-Science/pouta-blueprints

aptitude update
aptitude install -y git build-essential python-dev python-setuptools
easy_install pip
pip install ansible
git clone --branch $PB_BRANCH $PB_REPO /opt/pouta-blueprints

cat > /root/pb_ansible_inventory << END_AI
[docker_host]
localhost ansible_connection=local
END_AI

ansible-playbook -i /root/pb_ansible_inventory /opt/pouta-blueprints/ansible/prepare_vm.yml

su - cloud-user -c 'cd /opt/pouta-blueprints && scripts/deploy_local_docker_containers.bash'


