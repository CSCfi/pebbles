#!/usr/bin/env bash

#
# Script to set up a standalone notebook server based on 'notebook_host' ansible role
#

set -e

install_packages()
{
    sudo yum install -y ansible
}

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

create_ansible_inventory()
{
    cat > ansible_inventory << EOF_INVENTORY
[notebook-host]
localhost ansible_connection=local

EOF_INVENTORY

}

run_ansible()
{
    pushd pouta-blueprints
    ansible-playbook -i ~/ansible_inventory -v ansible/notebook_playbook.yml \
        -e notebook_host_block_dev_path=/dev/vdc \
        -e enable_docker_ssl=False
    popd
}

build_image()
{
    p_image=$1
    pushd pouta-blueprints/deployment/dockerfiles
    docker build -t $p_image $p_image
    popd
}

print_usage()
{
    cat << EOF_USAGE
Script to set up a standalone Jupyter notebook server, based on 'notebook_host' ansible role.
Will set up one container per notebook and one nginx proxy container in front of them, listening to port 80
and forwarding urls like http://your.ip.here/notebook-1-name/ to the notebook containers.

Prerequisites
- CentOS-7.0 host with a volume attached as /dev/vdc
- file called 'config.txt', each line containing <notebook name> <password-hash>

Password hashes can be generated with:
$ docker run --rm -i -t docker.io/jupyter/minimal-notebook /usr/bin/env python -c "from notebook.auth import passwd; print(passwd('mysecret'))"

Usage: $0 [options]

where options are:
  -c : just create containers, skip installation step
  -i : image to run
  -b : build image"

EOF_USAGE

    exit 0
}

create_container()
{
    p_image=$1
    p_name=$2
    p_password=$3

    if docker ps | grep -q "$p_name$"; then
        echo "Container $p_name already exists"
        return 0
    fi

    echo "creating container $p_image $p_name $p_password"

    docker run -d -i \
    --name $p_name \
    -e BOOTSTRAP_URL=https://raw.githubusercontent.com/CSC-IT-Center-for-Science/kajaani-science-days-workshop/master/data-analytics.ipynb \
    $image \
    /usr/local/bin/bootstrap_and_start.bash \
    --NotebookApp.password="$p_password" --NotebookApp.base_url="$p_name" --NotebookApp.allow_origin='*'
}

create_nginx_config_snippet()
{
    p_name=$1

    echo "creating nginx proxy config for $p_name"

    cat > /tmp/nginx_snippet_${p_name} << EOF_CONFIG
    location /$p_name {
      proxy_pass http://$p_name:8888;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Origin "";
    }
EOF_CONFIG
}

generate_nginx_config()
{
    cat > /tmp/proxy.conf.new << EOF_CONFIG
server {
    listen 80;
    client_max_body_size 20M;

EOF_CONFIG
    for snippet in /tmp/nginx_snippet_*; do
        cat $snippet >> /tmp/proxy.conf.new
        rm -f $snippet
    done

    echo "}" >> /tmp/proxy.conf.new

    cp -vf /tmp/proxy.conf.new /tmp/proxy.conf
    sudo chcon -Rt svirt_sandbox_file_t /tmp/proxy.conf
}

run_proxy_container()
{
    p_notebook_names=$@

    if docker ps -a | grep -q "nginx-proxy$"; then
        echo "removing nging-proxy"
        docker rm -f nginx-proxy
    fi

    link_list=""
    for name in $p_notebook_names; do
        link_list+=" --link $name:$name"
    done


    docker run --name nginx-proxy -d \
        -p 80:80 \
        -v /tmp/proxy.conf:/etc/nginx/conf.d/default.conf:ro \
        $link_list \
        nginx
}

## Main stuff

just_create_containers=false
build_image=false
image=jupyter_ds_with_bootstrap

while getopts "h?cbi:" opt; do
    case "$opt" in
    h|\?)
        print_usage
        exit 0
        ;;
    c)  just_create_containers=true
        ;;
    b)  build_image=true
        ;;
    i)  image="$OPTARG"
        ;;
    esac
done


# initialize

if [ $just_create_containers == false ]; then
    add_docker_group
    create_ansible_inventory
    install_packages
    run_ansible
fi

if [ $build_image == true ]; then
    build_image $image
fi

# create containers based on config.txt

names=""
while read line; do
    if [ "xxx$line" == "xxx" ]; then continue; fi
    a_line=(${line// / })
    c_name=${a_line[0]}
    c_password=${a_line[1]}

    create_container $image $c_name $c_password

    create_nginx_config_snippet $c_name

    names+=" $c_name"

done < config.txt

# create nginx proxy

generate_nginx_config

run_proxy_container $names
