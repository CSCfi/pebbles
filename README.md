<img src="https://travis-ci.org/CSC-IT-Center-for-Science/resource-cloud.svg">

# Pouta Blueprints

**Pouta Blueprints** is a frontend to manage cloud resources and lightweight user
accounts.
Currently the only resource supported resource type is [Pouta
Virtualcluster](https://github.com/CSC-IT-Center-for-Science/pouta-virtualcluster),
which can be used to launch clusters on [Pouta](https://pouta.csc.fi).

## Installation of development environment ##

Provided Vagrantfile can be used to start a new **Pouta Blueprints** instance
(requires VirtualBox or Docker)

    vagrant up

After the installation the first admin user is created by using the
[initialization form](https://localhost:8888/#/initialize)
