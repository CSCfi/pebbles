from flask.ext.testing import TestCase
from flask_testing import LiveServerTestCase

import logging


from selenium import webdriver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

from pebbles.server import app
from pebbles.models import db
from pebbles.config import TestConfig
from pebbles.config import LiveTestConfig


class BaseTestCase(TestCase):
    def create_app(self):
        app.dynamic_config = TestConfig()
        app.config.from_object(app.dynamic_config)
        app.config['TESTING'] = True
        return app

    def setUp(self):
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()


class SeleniumBaseTestCase(LiveServerTestCase):
    """Base test case for selenium-based browser tests.

    Idea is that this class provides common functionality for e.g. logging
    users in and out via _functions and testcases can focus on being
    relatively short and readable.

    If you intend to use something more than a couple of times, add it here
    and document.
    """
    # FixturesMixin and LiveServerTestCase don't seem to play together well.
    # Something to do with somebody popping an extra context.
    # Must manually create fixtures in setUp or classSetUp

    def create_app(self):
        app.dynamic_config = LiveTestConfig()
        app.config.from_object(app.dynamic_config)
        app.config['TESTING'] = True
        app.config['LIVESERVER_PORT'] = 8943
        self.config = app.config
        # failing tests may leave the db in an odd state so purge
        with app.app_context():
            db.drop_all()
        self.db = db
        self.app = app
        return app

    def setUp(self):
        from pebbles.tests.fixtures import primary_test_setup
        with self.app.app_context():
            self.db.drop_all()
            self.db.create_all()
        primary_test_setup(self)
        self.drivers = [webdriver.Firefox()]

    def tearDown(self):
        for driver in self.drivers:
            driver.close()

    def _do_login(self, username, password, driver,
                  wait_for_element_id="user-dashboard", wait_for=10):
        """ Load frontpage and enter credentials.
            Params:
                credentials to enter to fields
                driver to use
                wait_for_element_id (differs for admin and regular user)
                timeout (so we can timeout sooner e.g. for failed logins)
        """
        driver.get(self.get_server_url() + "/")
        elem = driver.find_element_by_name("click-show-login")
        # make the form visible if we have SSO enabled
        if elem.is_displayed():
            elem.click()
        elem = driver.find_element_by_name("eppn")
        elem.send_keys(username)
        elem = driver.find_element_by_name("password")
        # all logged in users are directed to either dashboard or admin dash.
        # we wait until it is visible and located or up to 10s
        elem.send_keys(password)
        elem.send_keys(Keys.RETURN)

        try:
            wait = WebDriverWait(driver, wait_for)
            wait.until(EC.visibility_of_element_located((By.ID,
                                                        wait_for_element_id)))
        except Exception as ex:
            logging.info("caught exception trying to log in:" + str(ex))
        finally:
            return

    def _do_logout(self, driver):
        """ Click on the logout button and wait for it to become invisible.
        """
        element = driver.find_element_by_id("logout")
        element.click()
        try:
            wait = WebDriverWait(driver, 10)
            wait.until(EC.invisibility_of_of_element_located((By.ID,
                                                             "logout")))
        except Exception as ex:
            logging.info("caught exception trying to log out:" + str(ex))
        finally:
            return
