from pyfakefs.fake_filesystem_unittest import Patcher
from pebbles.utils import env_string_to_dict, read_list_from_text_file, validate_container_image_url


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


def test_read_list_from_text_file():
    file_contents = "\n".join(['# foo', 'test', 'hello ', ' nowhitespace', ' alphabetic ', '', ' ', '123', 'Capital'])
    with Patcher() as patcher:
        patcher.fs.create_file('/foo/test_file.txt', contents=file_contents)
        filtered_contents = read_list_from_text_file('/foo/test_file.txt')
        assert filtered_contents == ['test', 'hello', 'nowhitespace', 'alphabetic', 'Capital']


def test_validate_container_image_url():
    """
    Test that validate_container_image_url returns an error string if image URL is invalid
    """
    valid_container_image_urls = [
        "docker.io/rocker/rstudio:latest",
        "registry.2.app.com/repo/image:01-01-2024",
        "private-registry:5000/repo/image:latest",
        "docker.io/library/tomcat@sha256:c34ce3c1fcc0c7431e1392cc3abd0dfe2192ffea1898d5250f199d3ac8d8720f",
    ]
    for url in valid_container_image_urls:
        assert not validate_container_image_url(url)

    invalid_container_image_urls = [
        "foo/bar:latest",
        "https://docker.io/rocker/rstudio:latest",
        "/home/user/images/rstudio:latest",
        r"C:\Documents\images\image:1235",
    ]
    for url in invalid_container_image_urls:
        assert validate_container_image_url(url)
