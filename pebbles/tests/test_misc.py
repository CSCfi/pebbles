from unittest import TestCase
from mock import patch, Mock, MagicMock


class TestAppCreation(TestCase):
    """ A class to test things to do with creating the Flask app.
    """
    def setUp(self):
        pass

    @patch("pebbles.app.flask_upgrade_db_to_head")
    def test_no_automigrate_by_default(self, automigrate):
        """Should you for some reason have DB_AUTOMIGRATE set when running
        tests this will fail.
        """
        from pebbles.app import run_things_in_context
        run_things_in_context(False)
        assert not automigrate.called

    @patch("pebbles.app.flask_upgrade_db_to_head")
    @patch("pebbles.app.os")
    def test_automigrate_called(self, mock_os, automigrate):
        mock_os.environ = MagicMock
        mock_os.environ.get = Mock()
        mock_os.os_environ.get.return_value = "1"
        from pebbles.app import run_things_in_context
        run_things_in_context(False)
        assert automigrate.called


class TestMisc(TestCase):
    """ A class to test simple helper functions
    """
    def setUp(self):
        pass

    def test_parse_env_string(self):
        from pebbles.config import _parse_env_value
        assert _parse_env_value("true")
        assert _parse_env_value("trUe")
        assert _parse_env_value("TRUE")
        assert not _parse_env_value("False")
        assert not _parse_env_value("FALSE")
        assert _parse_env_value("5") == 5
        assert _parse_env_value("-15") == -15
        assert _parse_env_value("5.0") == 5.0
        assert _parse_env_value("-5.0") == -5.0
        assert _parse_env_value("5.0f") == "5.0f"
