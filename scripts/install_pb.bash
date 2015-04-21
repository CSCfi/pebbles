#!/bin/bash

set -e

add_docker_group()
{
    if ! id | grep -q "(docker)"; then
        echo ""
        echo "Adding $USER to docker group"
        if ! getent group docker > /dev/null; then
        sudo groupadd -r docker
        fi
        sudo usermod -a -G docker $USER
        echo ""
        echo "Log out and log in again to make docker group effective for $USER, then run me again"
        echo ""
        exit 0
    else
        echo ""
        echo "$USER is in docker group, continuing installation"
        echo ""
    fi
}

patch_sources_list()
{
    if grep -q "nova.clouds" /etc/apt/sources.list; then
        echo "-------------------------------------------------------------------------------"
        echo
        echo "Patching /etc/apt/sources.list to point to a Finnish mirror"
        echo
        sudo sed -i -e 's/nova\.clouds\./fi./g' /etc/apt/sources.list
    fi
}

run_apt_update()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Updating apt repository metadata"
    echo
    metadata_age=$[$(date +%s) - $(stat -c %Z /var/lib/apt/periodic/update-success-stamp)]
    if [  $metadata_age -gt 3600 ]; then
        sudo aptitude update
    fi
}

install_packages()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Installing packages"
    echo
    sudo aptitude install -y git build-essential python-dev python-setuptools python-openstackclient
    sudo -H easy_install pip
    sudo -H pip install ansible==1.9.0.1
}

create_creds_file()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Testing OpenStack credentials"
    if nova flavor-list; then
        sudo mkdir -p /run/shm/pouta_blueprints
        echo "Updating m2m credentials"
        (

        cat << END_M2M
{
  "OS_USERNAME": "$OS_USERNAME",
  "OS_PASSWORD": "$OS_PASSWORD",
  "OS_TENANT_NAME": "$OS_TENANT_NAME",
  "OS_TENANT_ID": "$OS_TENANT_ID",
  "OS_AUTH_URL": "$OS_AUTH_URL"
}
END_M2M

        ) | sudo tee /run/shm/pouta_blueprints/creds > /dev/null
        echo "done"
        echo
    else
        echo "Seems like OpenStack credentials do not work. Make sure you have m2m openrc sourced with correct password"
        echo
        exit 1
    fi
}

create_ansible_inventory()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Creating ansible inventory"
    echo
    cat > $HOME/pb_ansible_inventory << END_AI
[docker_host]
localhost ansible_connection=local
END_AI
}

clone_git_repo()
{
    if [ -e pouta-blueprints ]; then
    echo "-------------------------------------------------------------------------------"
        echo
        echo "pouta-blueprints directory already exists, skipping git clone"
        echo
    else
        if [ "xxx$git_repository" == "xxx" ]; then
          git_repository="https://github.com/CSC-IT-Center-for-Science/pouta-blueprints.git"
        fi

        if [ "xxx$git_branch" == "xxx" ]; then
          git_branch="master"
        fi

        echo "-------------------------------------------------------------------------------"
        echo
        echo "Cloning Pouta Blueprints git repository, branch: '$git_branch'"
        echo
        git clone $git_repository --branch $git_branch
    fi
}

create_shared_secret()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Creating shared secret for both containers"
    if [ ! -e .pb_application_secret_key ]; then
        echo "no existing key found, creating a new one"
        openssl rand -base64 32 > .pb_application_secret_key
    fi
    echo

    application_secret_key=$(cat .pb_application_secret_key)
}

get_public_ip()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo -n "Figuring out the public ip: "

    public_ipv4=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
    if [ "xxx$public_ipv4" == "xxx" ]; then
       echo " NOT FOUND"
       echo
       echo "Please assign a public IP to the instance and run me again"
       echo

       exit 1
    else
       echo " $public_ipv4"
       echo
    fi
}

run_ansible()
{
    export ANSIBLE_HOST_KEY_CHECKING=0
    export PYTHONUNBUFFERED=1

    echo "-------------------------------------------------------------------------------"
    echo
    echo "Running ansible to create containers and install software"
    echo
    cd pouta-blueprints
    ansible-playbook -i $HOME/pb_ansible_inventory ansible/playbook.yml\
     -e deploy_mode=docker \
     -e server_type=prod \
     -e application_secret_key=$application_secret_key \
     -e public_ipv4=$public_ipv4 \
     -e docker_host_app_root=$PWD
}

create_ssh_aliases()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Creating aliases for www and worker in ssh config"
    if ! grep -q "Host www" ~/.ssh/config; then
        echo "adding entry for www"
        cat >> ~/.ssh/config << EOF_SSH
Host www
        StrictHostKeyChecking no
        HostName localhost
        Port 2222
EOF_SSH

    fi

    if ! grep -q "Host worker" ~/.ssh/config; then
        echo "adding entry for worker"
        cat >> ~/.ssh/config << EOF_SSH
Host worker
        StrictHostKeyChecking no
        HostName localhost
        Port 2223
EOF_SSH

    fi
    echo
}

if [ "xxx$1" != "xxx" ]; then

    # parameters given
    case $1 in
    creds)
        create_creds_file
        exit 0
    ;;

    help|-h|--help)
        echo
        echo "Usage: $0 [creds]"
        echo
        echo "By default, a full install/configuration run is performed"
        echo
        exit 0
    ;;

    *)
        echo "Unknown parameter $1"
        exit 1
    ;;
    esac
fi


# all modules (more granularity added later if necessary)

add_docker_group
patch_sources_list
run_apt_update
install_packages
create_creds_file
create_ansible_inventory
clone_git_repo
create_shared_secret
get_public_ip
run_ansible
create_ssh_aliases

echo "-------------------------------------------------------------------------------"
echo "Setup finished, point your browser to "
echo
echo " https://$public_ipv4/#/initialize"
echo
echo " and create an admin user"
echo "-------------------------------------------------------------------------------"
