.. image:: https://badge.waffle.io/CSC-IT-Center-for-Science/pebbles.png?label=ready&title=Ready 
 :target: https://waffle.io/CSC-IT-Center-for-Science/pebbles
 :alt: 'Stories in Ready'
.. image:: https://travis-ci.org/CSC-IT-Center-for-Science/pebbles.svg
   :target: https://travis-ci.org/CSC-IT-Center-for-Science/pebbles/
   :alt: Build Status
.. image:: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/gpa.svg
   :target: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints
   :alt: Code Climate
.. image:: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints/badges/coverage.svg
   :target: https://codeclimate.com/github/CSC-IT-Center-for-Science/pouta-blueprints
   :alt: Test Coverage

Pebbles
****************

**Pebbles** (formerly Pouta Blueprints) is a frontend to manage cloud
resources and lightweight user accounts. Currently supported resource types
are:

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

The system comes with Sphinx RST documentation under doc/. Convention is to have
as much as possible as docstrings close to the code that implements. Generic
things like system descriptions may also be under doc/source. ::

        $ mkvirtualenv pb-doc
        (pb-doc) $ pip install -r requirements.txt
        (pb-doc) $ cd doc && make html

Will build the html documentation under doc/build. There is a requirement of
graphviz for creating system structure graphs.

The documentation is hosted in GitHub pages and built using `Travis-Sphinx`_.

        $ workon pb-doc
        (pb-doc)$ travis-sphinx --branches=doc/sphinx --source=doc/source build

Can save you a lot of trouble.

.. _OpenStack driver: pebbles/drivers/provisioning/openstack_driver.py
.. _Docker driver: pebbles/drivers/provisioning/README_docker_driver.md
.. _Pouta Virtualcluster: https://github.com/CSC-IT-Center-for-Science/pouta-virtualcluster
.. _Travis Sphinx: https://github.com/Syntaf/travis-sphinx
