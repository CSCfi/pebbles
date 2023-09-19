def test_parse_env_value():
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


def test_env_string_to_dict():
    from pebbles.utils import env_string_to_dict

    test_data = (
        ('', dict()),
        ('FOO=bar', dict(FOO='bar')),
        ('FOO=bar E1=hello', dict(FOO='bar', E1='hello')),
        ('    FOO=bar    E1=hello    ', dict(FOO='bar', E1='hello')),
        ('=    FOO=bar    E1=hello  === ', dict(FOO='bar', E1='hello')),
        ('FOO=bar E1=hello  E2=only first gets assigned', dict(FOO='bar', E1='hello', E2='only')),
        ('FOO=bar E1=hello  E1=override', dict(FOO='bar', E1='override')),
        ('FOO=bar E1=', dict(FOO='bar', E1='')),
    )

    for t in test_data:
        assert env_string_to_dict(t[0]) == t[1]
