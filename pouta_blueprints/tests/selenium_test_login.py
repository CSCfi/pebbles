import unittest

from pouta_blueprints.tests.base import SeleniumBaseTestCase
from pouta_blueprints.models import Variable

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class LoginTestCase(SeleniumBaseTestCase):
    """ Tests basic login and logout functionality.
    """

    def test_login_as_admin(self):
        for driver in self.drivers:
            self._do_login(
                self.known_admin_email,
                self.known_admin_password,
                driver,
                wait_for_element_id="admin-dashboard"
            )
            elements = driver.find_elements_by_id("admin-dashboard")
            self.assertIsNotNone(elements)
            assert len(elements) >= 1

    def test_login_as_user(self):
        for driver in self.drivers:
            self._do_login(
                self.known_user_email,
                self.known_user_password,
                driver,
            )
            elements = driver.find_elements_by_id("user-dashboard")
            self.assertIsNotNone(elements)
            assert len(elements) >= 1

    def test_login_fail_as_user(self):
        for driver in self.drivers:
            driver.get(self.get_server_url() + "/")
            element = driver.find_element_by_id("invalid-login")
            assert not element.is_displayed()
            self._do_login(
                self.known_user_email,
                "open sesame",
                driver,
                wait_for=2
            )
            element = driver.find_element_by_id("invalid-login")
            assert element.is_displayed()
            i_should_be_empty = driver.find_elements_by_id("user-dashboard")
            assert len(i_should_be_empty) == 0

    def test_login_logout_as_user(self):
        for driver in self.drivers:
            self._do_login(
                self.known_user_email,
                self.known_user_password,
                driver
            )
            self._do_logout(driver)
            elements = driver.find_elements_by_id("user-dashboard")
            assert len(elements) == 0

    def test_frontpage(self):
        """ test more for the set-up of the system than any actual
        functionality. asserts that the front page can be loaded and the
        notification tag is present.

        It was added so that a developer doesn't get depressed when all the
        other tests fail.
        """
        driver = self.drivers[0]
        driver.get(self.get_server_url() + "/")
        wait = WebDriverWait(driver, 10)
        wait.until(EC.visibility_of_element_located((By.TAG_NAME,
                                                    "pb-notifications")))
        element = driver.find_element_by_tag_name("pb-notifications")
        self.assertIsNotNone(element)

    def test_frontpage_name_description(self):
        """ Tests that the configurable installation name and description are
        present on the login page.
        """
        driver = self.drivers[0]
        driver.get(self.get_server_url() + "/")
        wait = WebDriverWait(driver, 10)
        wait.until(EC.visibility_of_element_located((By.NAME,
                                                    "installation-name")))
        element = driver.find_element_by_name("installation-name")
        config = self.config
        assert config["INSTALLATION_NAME"] == element.text
        element = driver.find_element_by_name("installation-description")
        assert config["INSTALLATION_DESCRIPTION"] == element.text

    def test_frontpage_login_visibility(self):
        """
            If shibboleth login is enabled, it should be the only visible way
            to log in and form should be hidden. Also vice versa.
        """
        shibboleth_enabled = \
            Variable.query.filter_by(key="ENABLE_SHIBBOLETH_LOGIN").first()
        saved = shibboleth_enabled.value
        # Set Value to True
        # Show shibboleth, don't show login by default
        shibboleth_enabled.value = True
        self.db.session.commit()
        driver = self.drivers[0]
        driver.get(self.get_server_url() + "/")
        wait = WebDriverWait(driver, 10)
        wait.until(EC.visibility_of_element_located((By.NAME,
                                                    "shibboleth-login")))
        element = driver.find_element_by_name("shibboleth-login")
        assert element.is_displayed()
        other_element = driver.find_element_by_name("password-login")
        assert not other_element.is_displayed()
        # Set Value to True
        # Don't show shibboleth, do show login by default
        shibboleth_enabled.value = False
        self.db.session.commit()
        driver.get(self.get_server_url() + "/")
        wait = WebDriverWait(driver, 10)
        wait.until(EC.visibility_of_element_located((By.NAME,
                                                    "password-login")))
        element = driver.find_element_by_name("shibboleth-login")
        assert not element.is_displayed()
        other_element = driver.find_element_by_name("password-login")
        assert other_element.is_displayed()

        # Don't remember if live tests are run in isolation so revert original
        # value just in case
        shibboleth_enabled.value = saved
        self.db.session.commit()

if __name__ == "__main__":
    unittest.main()
