from flask.ext.script import Manager
from flask.ext.migrate import Migrate, MigrateCommand

from resource_cloud.server import app, db


migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command('db', MigrateCommand)


@manager.command
def test():
    """Runs the unit tests without coverage."""
    import unittest
    tests = unittest.TestLoader().discover('resource_cloud.tests')
    unittest.TextTestRunner(verbosity=2).run(tests)


@manager.command
def cov():
    """Runs the unit tests with coverage."""
    import coverage
    import unittest
    import os
    cov = coverage.coverage(
        branch=True,
        include='project/*'
    )
    cov.start()
    tests = unittest.TestLoader().discover('resource_cloud.tests')
    unittest.TextTestRunner(verbosity=2).run(tests)
    cov.stop()
    cov.save()
    print('Coverage Summary:')
    cov.report()
    basedir = os.path.abspath(os.path.dirname(__file__))
    covdir = os.path.join(basedir, 'coverage')
    cov.html_report(directory=covdir)
    cov.erase()

if __name__ == '__main__':
        manager.run()
