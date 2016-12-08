Devevelopment environment
*************************

Which development set-up?
=========================

If in doubt choose Vagrant.

If developing things that require database migrations, do a local set-up.

For debugging use whichever suits your needs.

Vagrant set-up
==============
 
Provided Vagrantfile can be used to start a new **Pouta Blueprints** instance 
(requires VirtualBox or Docker)

.. code-block:: sh

        vagrant up

or

.. code-block:: sh

        vagrant up --provider=docker

After the installation the first admin user is created by using the
initialization form at (https://localhost:8888/#/initialize). The development
environment uses a self-signed certificate.

Local set-up
============

To set up a development environment you'll obviously need python 2.7.x, with X
preferably being the latest version. Py3 support pends on Py3 support in
Ansible that parts of the system use internally.

It's a good idea to have a relatively new pip and possibly build essentials
for your platform. Too old versions sometimes handle requirement resolution
poorly.

It's recommended to use virtualenvwrapper.

.. code-block:: sh

         $ cd pouta_blueprints
         $ mkvirtualenv pb
         (pb) $ pip install -r requirements.txt # install requirement packages
         (pb) $ python manage.py db upgrade # create and upgrade db
         (pb) $ python manage.py runserver

Selenium tests
==============

There are some Selenium tests for integration and acceptance tests.

Currently the only used driver is old Firefox native driver, which requires
Firefox 45. To run the tests run.

.. code-block:: sh

        (pb) $ python manage.py selenium

Setting up a more complex setup using the Marionette, Chromedriver etc. is in
the works. This requires that said artefacts be present. OTOH current approach
requires a stale version of FF.
