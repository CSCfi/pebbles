from flask.ext.script import Manager, Shell
from flask.ext.migrate import Migrate, MigrateCommand

from pouta_blueprints.server import app, db
from pouta_blueprints import models


migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command('migrate', MigrateCommand)


def _make_context():
    return dict(app=app, db=db, models=models)

manager.add_command("shell", Shell(make_context=_make_context))


@manager.command
def test():
    """Runs the unit tests without coverage."""
    import unittest
    tests = unittest.TestLoader().discover('pouta_blueprints.tests')
    unittest.TextTestRunner(verbosity=2).run(tests)


@manager.command
def cov():
    """Runs the unit tests with coverage."""
    import coverage
    import unittest
    cov = coverage.coverage(
        branch=True,
        include='pouta_blueprints/*'
    )
    cov.start()
    tests = unittest.TestLoader().discover('pouta_blueprints.tests')
    unittest.TextTestRunner(verbosity=2).run(tests)
    cov.stop()
    cov.save()
    print('Coverage Summary:')
    cov.report()

if __name__ == '__main__':
        manager.run()
