from unittest import TestCase


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
