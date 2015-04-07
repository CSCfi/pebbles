[![TravisCI](https://travis-ci.org/CSC-IT-Center-for-Science/pouta-blueprints.svg)](https://travis-ci.org/CSC-IT-Center-for-Science/pouta-blueprints/) [![Code Climate](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/gpa.svg)](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints) [![Test Coverage](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/coverage.svg)](https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints)

# Pouta Blueprints

**Pouta Blueprints** is a frontend to manage cloud resources and lightweight user
accounts.
Currently supported resource types are 
 - [Pouta Virtualcluster](https://github.com/CSC-IT-Center-for-Science/pouta-virtualcluster),
which can be used to launch clusters on [Pouta](https://pouta.csc.fi).
 - [OpenStack driver](https://github.com/CSC-IT-Center-for-Science/pouta-blueprints/blob/master/pouta_blueprints/drivers/provisioning/openstack_driver.py), which can be used to launch instances on OpenStack cloud.

Additional resources can be added by implementing the driver interface [/pouta_blueprints/drivers/provisioning/base_driver.py](https://github.com/CSC-IT-Center-for-Science/pouta-blueprints/blob/master/pouta_blueprints/drivers/provisioning/base_driver.py)

## Installation of development environment ##

Provided Vagrantfile can be used to start a new **Pouta Blueprints** instance
(requires VirtualBox or Docker)

    vagrant up

After the installation the first admin user is created by using the
[initialization form](https://localhost:8888/#/initialize)
