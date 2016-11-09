[![TravisCI](https://travis-ci.org/CSC-IT-Center-for-Science/pouta-blueprints.svg)](https://travis-ci.org/CSC-IT-Center-for-Science/pouta-blueprints/) [![Code Climate](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/gpa.svg)](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints) [![Test Coverage](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/coverage.svg)](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints)

# Pouta Blueprints

**Pouta Blueprints** is a frontend to manage cloud resources and lightweight user
accounts.
Currently supported resource types are 
 - [OpenStack driver](pouta_blueprints/drivers/provisioning/openstack_driver.py),
    which can be used to launch instances on OpenStack cloud.
 - [Docker driver] (pouta_blueprints/drivers/provisioning/README_docker_driver.md),
    for running web notebook instances in Docker containers on a pool of virtual machines. 
 - [Pouta Virtualcluster](https://github.com/CSC-IT-Center-for-Science/pouta-virtualcluster),
    which can be used to launch clusters on [cPouta](https://research.csc.fi/pouta-iaas-cloud).
    
Additional resources can be added by implementing the driver interface
[/pouta_blueprints/drivers/provisioning/base_driver.py](pouta_blueprints/drivers/provisioning/base_driver.py)

## Documentation ##

The system comes with Sphinx documentation under doc/. It's a work in progress
to figure out where the documentation will be hosted.

        $ cd doc && make html

Will build the html documentation. There is a requirement of graphviz
for creating system structure graphs.

