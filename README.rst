.. image:: https://travis-ci.org/CSC-IT-Center-for-Science/pouta-blueprints.svg
   :target: https://travis-ci.org/CSC-IT-Center-for-Science/pouta-blueprints/
   :alt: Build Status
.. image:: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/gpa.svg
   :target: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints
   :alt: Code Climate
.. image:: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/coverage.svg
   :target: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints
   :alt: Test Coverage
[![TravisCI]()]() [![Code Climate](]( [![Test Coverage]()]()

Pouta Blueprints
****************

**Pouta Blueprints** is a frontend to manage cloud resources and lightweight user
accounts.
Currently supported resource types are 
 - `OpenStack driver`_,
    which can be used to launch instances on OpenStack cloud.
 - `Docker driver`_,
    for running web notebook instances in Docker containers on a pool of virtual machines. 
 - `Pouta Virtualcluster`_ ,
    which can be used to launch clusters on `cPouta <https://research.csc.fi/pouta-iaas-cloud>`_.

    
Additional resources can be added by implementing the driver interface. ToDo:
hyperlink to new docs.

Documentation
=============

The system comes with Sphinx documentation under doc/. It's a work in progress
to figure out where the documentation will be hosted.::

        $ cd doc && make html

Will build the html documentation. There is a requirement of graphviz
for creating system structure graphs.

.. _OpenStack driver: pouta_blueprints/drivers/provisioning/openstack_driver.py
.. _Docker driver: pouta_blueprints/drivers/provisioning/README_docker_driver.md 
.. _Pouta Virtualcluster: https://github.com/CSC-IT-Center-for-Science/pouta-virtualcluster
