#!/bin/bash

cat > $HOME/pb_ansible_inventory << END_AI
[docker_host]
localhost ansible_connection=local

[docker_host:vars]
shared_folder_source=$PWD

END_AI

export ANSIBLE_HOST_KEY_CHECKING=0
ansible-playbook -i $HOME/pb_ansible_inventory ansible/playbook.yml
