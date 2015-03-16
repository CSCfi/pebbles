#!/bin/bash

set -e
set -x

aptitude update
aptitude install -y git build-essential python-dev python-setuptools
easy_install pip
pip install ansible

groupadd docker
usermod -a -G docker cloud-user

cat > /tmp/pb_setup_run_as_cloud_user.bash << "END_RACU"

#!/bin/bash
PB_BRANCH=wip/remote_deployment
PB_REPO=https://github.com/CSC-IT-Center-for-Science/pouta-blueprints

set -e
set -x

pb_temp=$(mktemp -d)

git clone --branch $PB_BRANCH $PB_REPO $pb_temp/git

(
echo "[docker_host]"
echo "localhost ansible_connection=local"
) > $pb_temp/pb_ansible_inventory

export PYTHONUNBUFFERED=1
ansible-playbook -i $pb_temp/pb_ansible_inventory $pb_temp/git/ansible/prepare_vm.yml

cd $pb_temp/git && scripts/deploy_local_docker_containers.bash

rm -rf $pb_temp

END_RACU

su - cloud-user -c "bash /tmp/pb_setup_run_as_cloud_user.bash"
