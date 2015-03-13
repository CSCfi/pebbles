#!/bin/bash

PB_BRANCH=wip/remote_deployment
PB_REPO=https://github.com/CSC-IT-Center-for-Science/pouta-blueprints

aptitude update
aptitude install -y python-pip git build-essential python-dev
pip install ansible
git clone --branch $PB_BRANCH $PB_REPO /opt/pouta-blueprints

cd /opt/pouta-blueprints
scripts/deploy_local_docker_containers.bash


