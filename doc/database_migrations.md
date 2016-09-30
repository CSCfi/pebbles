# Database Migrations #

The tool stack we use for databases is SQLAlchemy, Alembic, Flask-SQLAlchemy
and Flask-Migrate.

## Overview ##

It's always possible to just use the db.create_all() to create all database
tables based on code at that point. This is what unit tests do to save time.
Because production databases have a state in the form of the data in them we
have to have migrations.

Database migration-related code is in migrations/. Migrations/env.py contains
some general settings, e.g. naming conventions for constraints and the use of
so-called batch mode with SQLite (that doesn't support ALTER statements). 

Individual migrations are files in migrations/versions. They are linked by
reference to the previous version inside the file and must always form a
single chain.

All the automated deployment systems assume that the migrations will sync the
system to the state in which models.py is. This includes the dev server
deployment.

## Process ##

After you change the models (add fields, constraints etc), first make sure you
have the correct packages installed etc. (ToDo: document!).

Then to make sure db is up to date with latest version file, run

        (env) pouta-blueprints/ $ python manage.py db upgrade

This reads through all the files, introspects the state of your configured db
(and creates it if it doesn't exist).

Then to create a new file, run 
        
        (env) pouta-blueprints/ $ python manage.py db migrate

inspect that you have a new .py file under migrations/versions and at the very
least change the name. Sometimes something doesn't work or the system isn't
good at divining what you want to happen so checking the actual migration code
is very much recommended.

To apply the migration you have created, run

        (env) pouta-blueprints/ $ python manage.py db upgrade

And the system picks up the new migration, sees that it hasn't been run yet
and applies it.

To downgrade e.g. after something appears broken and you don't want to start
generating the db from scratch you can run

        (env) pouta-blueprints/ $ python manage.py db downgrade [revision
        identifier]

## Notes ##

If you use the default settings the SQLite database location will be
at /tmp/change_me.db. Unit tests use an in-memory SQLite and live tests use a
/tmp/change_me.livetest.db . 

SQLite does not support ALTER at all, which is why we have enabled [batch
mode](http://alembic.zzzcomputing.com/en/latest/batch.html) . The system
promises not to do anything differently on databases that do support ALTER but
YMMV.

SQLite also permits completely unnamed constraints. This is all nice and well
until it's necessary to modify such a constraint, which is difficult because it
can't be referenced unambiguously.  For this reason a custom naming scheme has
been enabled in models.py.

The verbs that flask-migrate uses are unintuitive. The verb "migrate" actually
creates a migration and the verbs "upgrade" and "downgrade" apply migrations
(i.e. migrate).

For deployment security it's possible and perhaps even desired to first commit
and deploy changes to the database and models and only when that didn't break
to deploy (or enable via some mechanism) the code that uses these new
features.
