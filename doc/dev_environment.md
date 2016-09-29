# Dev environment #

For most things you can just deploy stuff using Vagrant and the changes will
be neatly visible inside the virtual machine. However, the Vagrant machine
automatically runs any migrations and assumes that the model file and db are
in sync. Also sometimes it's just easier to debug without the extra layer.

To set up a development environment you'll obviously need python 2.7.x, with X
preferably being the latest version. We haven't really tested PB on Py3 yet. 

It's a good idea to have a relatively new pip and possibly build essentials
for your platform.

It's recommended to use virtualenvwrapper.

         $ cd pouta_blueprints
         $ mkvirtualenv pb
         (pb) $ pip install -r requirements.txt # install requirement packages
         (pb) $ python manage.py db upgrade # create and upgrade db
         (pb) $ python manage.py runserver

## Selenium tests ##

There are some Selenium tests for integration and acceptance tests.

Currently the only used driver is old Firefox native driver, which requires
Firefox 45. To run the tests run.

        (pb) $ python manage.py selenium

Setting up a more complex setup using the Marionette, Chromedriver etc. is in
the works. This requires that said artefacts be present. OTOH current approach
requires a stale version of FF.
