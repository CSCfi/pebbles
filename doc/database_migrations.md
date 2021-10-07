# Database Migrations

The tool stack we use for databases is SQLAlchemy, Alembic, Flask-SQLAlchemy
and Flask-Migrate.

## Overview

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

## Process

After you change the models (add fields, constraints etc), first make sure you
have the correct packages installed etc, either by using a virtualenv or running
the command in the api container. Set "FLASK_APP" environment variable to "pebbles.server:app"
in your shell before running the commands.

        (env) pebbles/ $ export FLASK_APP=pebbles.server:app

Then to make sure db is up to date with latest version file, run

        (env) pebbles/ $ flask db upgrade

This reads through all the files, introspects the state of your configured db
(and creates it if it doesn't exist).

Then to create a new file, run 
        
        (env) pebbles/ $ flask db revision --autogenerate -m "short message describing the change"

inspect that you have a new .py file under migrations/versions and at the very
least change the name. Sometimes something doesn't work or the system isn't
good at divining what you want to happen so checking the actual migration code
is very much recommended. You can list all migrations with

        (env) pebbles/ $ flask db history

To apply the migration you have created, run

        (env) pebbles/ $ flask db upgrade

And the system picks up the new migration, sees that it hasn't been run yet
and applies it.

To downgrade e.g. after something appears broken and you don't want to start
generating the db from scratch you can run

        (env) pebbles/ $ flask db downgrade [revision identifier]

## Notes

The verbs that flask-migrate uses are unintuitive. The verb "migrate" actually
creates a migration and the verbs "upgrade" and "downgrade" apply migrations
(i.e. migrate).

For deployment security it's possible and perhaps even desired to first commit
and deploy changes to the database and models and only when that didn't break
to deploy (or enable via some mechanism) the code that uses these new
features.

For initial deployment of a persistent system, you should apply the migrations
instead of letting SQLAlchemy create the database. It is also possible to stamp
an existing database with the latest migration revision identifier with "flask db stamp".

