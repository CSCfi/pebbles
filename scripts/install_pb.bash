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
    if [ -f /etc/apt/sources.list ] && grep -q "nova.clouds" /etc/apt/sources.list; then
        echo "-------------------------------------------------------------------------------"
        echo
        echo "Patching /etc/apt/sources.list to point to a Finnish mirror"
        echo
        sudo sed -i -e 's/nova\.clouds\./fi./g' /etc/apt/sources.list
    fi
}

run_apt_update()
{
    if [ -f /var/lib/apt/periodic/update-success-stamp ]; then
        echo "-------------------------------------------------------------------------------"
        echo
        echo "Updating apt repository metadata"
        echo
        metadata_age=$[$(date +%s) - $(stat -c %Z /var/lib/apt/periodic/update-success-stamp)]
        if [  $metadata_age -gt 3600 ]; then
            sudo aptitude update
        fi
    fi
}

install_packages()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Installing packages"
    echo
    if [ -f /etc/debian_version ]; then
        sudo aptitude install -y git build-essential python-dev python-setuptools python-openstackclient
    fi
    if [ -f /etc/redhat-release ]; then
        sudo yum install -y centos-release-openstack
        sudo yum install -y bind-utils git python-devel python-setuptools python-novaclient
        sudo yum install -y libffi-devel openssl-devel
    fi

    sudo -H easy_install pip
    sudo -H pip install ansible==2.2.1
}

create_creds_file()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Testing OpenStack credentials"
    if nova flavor-list; then
        sudo mkdir -p /run/shm/pebbles
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

        ) | sudo tee /run/shm/pebbles/creds > /dev/null
        echo "done"
        echo

        if [ -f /etc/redhat-release ]; then
            echo "Enabling container access to creds file in SELinux"
            sudo chcon -Rt svirt_sandbox_file_t /run/shm/pebbles/creds
        fi

    else
        echo "Seems like OpenStack credentials do not work. Make sure you have m2m openrc sourced with correct password"
        echo
        exit 1
    fi
}

populate_sso_data()
{
    p_sso_data_dir=$1

    echo "-------------------------------------------------------------------------------"
    echo
    echo "Populating /var/lib/pb/sso"

    if [ ! -e /var/lib/pb/sso ]; then
        echo "Creating /var/lib/pb/sso"
        sudo mkdir -p /var/lib/pb/sso
    fi

    echo "Copying SSO certificates to /var/lib/pb/sso/"
    sudo cp -v $p_sso_data_dir/{sp_key,sp_cert,idp_cert}.pem /var/lib/pb/sso/

    if [ -f /etc/redhat-release ]; then
        echo "Enabling container access to sso_data in SELinux"
        sudo chcon -Rt svirt_sandbox_file_t /var/lib/pb/sso
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
    if [ -e pebbles ]; then
    echo "-------------------------------------------------------------------------------"
        echo
        echo "pebbles directory already exists, skipping git clone"
        echo
    else
        local_name="pebbles"
        if [ "xxx$git_repository" == "xxx" ]; then
          git_repository="https://github.com/CSCfi/pebbles.git"
        fi

        if [ "xxx$git_branch" == "xxx" ]; then
          git_branch="master"
        fi

        echo "-------------------------------------------------------------------------------"
        echo
        echo "Cloning Pebbles git repository, branch: '$git_branch'"
        echo
        git clone $git_repository --branch $git_branch $local_name
    fi
}

create_shared_secret()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Creating shared secret for all containers"
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
       echo "NOT FOUND"
       echo
       echo "Please assign a public IP to the instance and run me again"
       echo

       exit 1
    else
       echo "$public_ipv4"
       echo
    fi
}

get_domain_name()
{
    p_ip=$1
    echo "-------------------------------------------------------------------------------"
    echo
    echo -n "Figuring out domain name for ip $p_ip: "
    # reverse lookup
    domain_name=$(dig -x $p_ip +short | head -1)
    # dig will output the root dot also, we get rid of that with trailing conditional replace
    domain_name=${domain_name/%./}
    if [ "xxx$domain_name" == "xxx" ]; then
       echo "NOT FOUND"
       echo
       echo "There seems to be a problem resolving the public ip to a name"
       echo
       exit 1
    else
       echo "$domain_name"
       echo
    fi
}

run_ansible()
{
    export ANSIBLE_HOST_KEY_CHECKING=0
    export PYTHONUNBUFFERED=1
    extra_args="$extra_env"
    if [ $use_shibboleth == true ]; then
        extra_args="-e enable_shibboleth=True -e @$sso_data_dir/sso_config.yml $extra_args"
    fi

    # figure out the roles to deploy
    [[ $deploy_roles =~ "api,"    ]] && deploy_api=True    || deploy_api=False
    [[ $deploy_roles =~ "worker," ]] && deploy_worker=True || deploy_worker=False
    [[ $deploy_roles =~ "frontend,"  ]] && deploy_frontend=True  || deploy_frontend=False
    [[ $deploy_roles =~ "db,"     ]] && deploy_db=True     || deploy_db=False
    [[ $deploy_roles =~ "redis,"  ]] && deploy_redis=True  || deploy_redis=False
    extra_args="$extra_args -e deploy_api=$deploy_api"
    extra_args="$extra_args -e deploy_worker=$deploy_worker"
    extra_args="$extra_args -e deploy_frontend=$deploy_frontend"
    extra_args="$extra_args -e deploy_db=$deploy_db"
    extra_args="$extra_args -e deploy_redis=$deploy_redis"

    echo "-------------------------------------------------------------------------------"
    echo
    echo "Running ansible to create containers and install software"
    echo "Extra arguments: $extra_args"
    echo
    sleep 2

    cd pebbles
    ansible-playbook -i $HOME/pb_ansible_inventory ansible/playbook.yml\
     -e deploy_mode=docker \
     -e server_type=prod \
     -e application_debug_logging=False \
     -e application_secret_key=$application_secret_key \
     -e public_ipv4=$public_ipv4 \
     -e domain_name=$domain_name \
     -e docker_host_app_root=$PWD \
     $extra_args
}

create_ssh_alias()
{
    p_name=$1
    p_port=$2

    if ! grep -q "Host $p_name" ~/.ssh/config; then
        echo "adding entry for $p_name"
        cat >> ~/.ssh/config << EOF_SSH
Host $p_name
        StrictHostKeyChecking no
        HostName localhost
        Port $p_port
EOF_SSH

    fi
}

create_ssh_aliases()
{
    echo "-------------------------------------------------------------------------------"
    echo
    echo "Creating aliases in ssh config"

    [[ $deploy_roles =~ "api," ]] && create_ssh_alias api 2222
    [[ $deploy_roles =~ "worker," ]] && create_ssh_alias worker 2223
    [[ $deploy_roles =~ "frontend," ]] && create_ssh_alias frontend 2224

    [[ $use_shibboleth == true ]] && create_ssh_alias sso 2225

    echo "making ssh config accessible for user only"
    chmod go-rwx ~/.ssh/config

    echo
}

print_usage()
{
    echo "Usage: $0 [options]"
    echo
    echo " where options are:"
    echo "  -c          : just copy OpenStack credentials and exit"
    echo "  -s sso_data : enable shibboleth installation, copy data from sso_data"
    echo "  -r roles    : comma separated list of roles to deploy on this host"
    echo "                full list of roles: $deploy_roles"
    echo "  -e var=val  : environment var for ansible, can be specified more than once"
    echo
    echo "By default, a full install/configuration run is performed"
    echo
    exit 0
}


# Main starts here. First parse options

deploy_roles="api,worker,frontend,redis,db"
use_shibboleth=false
sso_data_dir=""
extra_env=""

while getopts "h?cs:r:e:" opt; do
    case "$opt" in
    h|\?)
        print_usage
        exit 0
        ;;
    c)  create_creds_file
        exit 0
        ;;
    s)  use_shibboleth=true
        sso_data_dir=$(realpath $OPTARG)
        echo
        echo "Ansible provisioning will enable Shibboleth and Apache"
        echo
        echo "sso_data will be picked from $sso_data_dir"
        echo
        ;;
    r)  deploy_roles="$OPTARG"
        ;;
    e)  extra_env="$extra_env -e $OPTARG"
        ;;
    esac
done

echo
echo "Deploying roles $deploy_roles"
echo

deploy_roles="${deploy_roles},"

# all modules (more granularity added later if necessary)

add_docker_group
patch_sources_list
run_apt_update
install_packages
if [[ $deploy_roles =~ "worker," ]]; then
    create_creds_file
fi
if [ $use_shibboleth == true ]; then
    populate_sso_data $sso_data_dir
fi
create_ansible_inventory
clone_git_repo
create_shared_secret
get_public_ip
get_domain_name $public_ipv4
run_ansible
create_ssh_aliases

echo "-------------------------------------------------------------------------------"
echo "Setup finished, point your browser to "
echo
echo " https://$domain_name/#/initialize"
echo
echo " and create an admin user"
echo "-------------------------------------------------------------------------------"
