import json
import uuid
from uuid import uuid4

import pytest

from pebbles.models import CustomImage
from pebbles.views.custom_images import create_dockerfile_from_definition
from tests.conftest import PrimaryData, RequestMaker


def test_get_custom_image(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that getting a custom image works as expected for different users
    """
    # Anonymous
    response = rmaker.make_request(path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id)
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id)
    assert response.status_code == 403

    # Authenticated Workspace Owner for Workspace 1(with 4 apps) and Normal User for Workspace 2
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
    )
    assert response.status_code == 200
    assert response.json.get('id') == pri_data.known_custom_image_id
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id_2
    )
    assert response.status_code == 404

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id)
    assert response.status_code == 200
    assert response.json.get('id') == pri_data.known_custom_image_id

    # non-existing custom_image
    # Anonymous
    response = rmaker.make_request(path='/api/v1/custom_images/%s' % uuid.uuid4().hex)
    assert response.status_code == 401
    # Owner
    response = rmaker.make_authenticated_workspace_owner_request(path='/api/v1/custom_images/%s' % uuid.uuid4().hex)
    assert response.status_code == 404
    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/custom_images/%s' % uuid.uuid4().hex)
    assert response.status_code == 404


def test_delete_custom_image(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that deleting a custom image works as expected for different users
    """
    # Anonymous
    response = rmaker.make_request(
        method='DELETE', path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id)
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(
        method='DELETE', path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id)
    assert response.status_code == 403

    # Authenticated Workspace Owner for Workspace 1 (with 4 apps) and Normal User for Workspace 2
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE', path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
    )
    assert response.status_code == 202
    assert response.json.get('id') == pri_data.known_custom_image_id
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE', path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id_2
    )
    assert response.status_code == 404

    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE', path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id_2)
    assert response.status_code == 202
    assert response.json.get('id') == pri_data.known_custom_image_id_2

    # both known images should be deleted at this point
    response = rmaker.make_authenticated_admin_request(
        method='GET', path='/api/v1/custom_images')
    assert response.status_code == 200
    assert [image["to_be_deleted"] for image in response.json]

    # non-existing custom_image
    # Anonymous
    response = rmaker.make_request(
        method='DELETE', path='/api/v1/custom_images/%s' % uuid.uuid4().hex)
    assert response.status_code == 401
    # Owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE', path='/api/v1/custom_images/%s' % uuid.uuid4().hex)
    assert response.status_code == 404
    # Admin
    response = rmaker.make_authenticated_admin_request(
        method='DELETE', path='/api/v1/custom_images/%s' % uuid.uuid4().hex)
    assert response.status_code == 404


def test_get_custom_images(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test listing custom_images
    """
    # Anonymous
    response = rmaker.make_request(path='/api/v1/custom_images')
    assert response.status_code == 401

    # Authenticated
    response = rmaker.make_authenticated_user_request(path='/api/v1/custom_images')
    assert response.status_code == 403

    # Authenticated Workspace Owner for Workspace 1 (with 4 apps) and Normal User for Workspace 2
    response = rmaker.make_authenticated_workspace_owner_request(
        path='/api/v1/custom_images'
    )
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0].get('id') == 'ci1'

    # Admin
    response = rmaker.make_authenticated_admin_request(path='/api/v1/custom_images')
    assert len(response.json) == 2


def test_anonymous_create_custom_image(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that an anonymous user cannot create custom images
    """
    data = dict(name='custom-image-1', workspace_id='ws1', dockerfile='FROM foo:latest\nRUN echo "hello"')
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(data))
    assert response.status_code == 401


def test_user_create_custom_image(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that a user cannot create custom images
    """
    # User is not a part of the workspace (Workspace2)
    data = dict(name='custom-image-1', workspace_id='ws1', dockerfile='FROM foo:latest\nRUN echo "hello"')
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(data))
    assert response.status_code == 403

    # User is a part of the workspace (Workspace1)
    data = dict(name='custom-image-1', workspace_id='ws1', dockerfile='FROM foo:latest\nRUN echo "hello"')
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(data))
    assert response.status_code == 403


def test_patch_custom_image_no_access(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that an anonymous user or owner cannot patch custom images
    """
    # Anonymous
    response = rmaker.make_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id)
    assert response.status_code == 401

    # Owners cannot patch
    response = rmaker.make_authenticated_workspace_owner_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
    )
    assert response.status_code == 403


def test_patch_custom_image_admin(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that admin patching custom images works as expected
    """
    # valid state change
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
        data=json.dumps(dict(state=CustomImage.STATE_BUILDING))
    )
    assert response.status_code == 200
    assert rmaker.make_authenticated_admin_request(
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
    ).json.get('state') == CustomImage.STATE_BUILDING

    # change setting and resetting other free form attributes
    for attribute in ('url', 'tag', 'build_system_id', 'build_system_output'):
        for value in [uuid4().hex, '']:
            response = rmaker.make_authenticated_admin_request(
                method='PATCH',
                path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
                data=json.dumps({attribute: value})
            )
            assert response.status_code == 200
            assert rmaker.make_authenticated_admin_request(
                path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
            ).json.get(attribute) == value

    # check that invalid changes are properly rejected
    ci1_before = rmaker.make_authenticated_admin_request(
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
    ).json

    # invalid state change
    for state in ('foo', CustomImage.STATE_BUILDING + 'FOO', ''):
        response = rmaker.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
            data=json.dumps(dict(state=state))
        )
        assert response.status_code == 422, f'state {state} should be invalid'
        # check that there is no change
        ci1_after = rmaker.make_authenticated_admin_request(
            path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
        ).json
        assert ci1_after == ci1_before, 'there should be no changes'

    # null/None change should be ignored
    for attribute in ('url', 'state', 'tag', 'build_system_id', 'build_system_output'):
        response = rmaker.make_authenticated_admin_request(
            method='PATCH',
            path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
            data=json.dumps({attribute: None})
        )
        assert response.status_code == 200, 'empty change'
        # check that there is no change
        ci1_after = rmaker.make_authenticated_admin_request(
            path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
        ).json
        assert ci1_after == ci1_before, 'there should be no changes'

    # invalid attributes should be ignored
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
        data=json.dumps(dict(hello='world', url='registry.example.org/foo/bar:main'))
    )
    assert response.status_code == 200, 'invalid attribute should be ignored'
    # check that there is no change
    ci1_after = rmaker.make_authenticated_admin_request(
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id
    ).json
    assert ci1_after['url'] == 'registry.example.org/foo/bar:main'

    # non-existing image
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % 'not-there',
        data=json.dumps(dict(state=CustomImage.STATE_BUILDING))
    )
    assert response.status_code == 404


def test_patch_custom_image_start_and_complete(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that custom image builds start and complete as expected
    """
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name='ci-2',
            workspace_id=pri_data.known_workspace_id,
            definition={'base_image': 'registry.io/image:latest', 'user': 'user', 'image_content': []})
        )
    )
    assert response.status_code == 200
    ci_id = response.json.get('id')
    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % ci_id,
        data=json.dumps(dict(state=CustomImage.STATE_BUILDING))
    )
    assert response.status_code == 200
    ci = rmaker.make_authenticated_admin_request(
        path='/api/v1/custom_images/%s' % ci_id
    ).json
    assert ci.get('started_at')
    assert not ci.get('completed_at')

    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % ci_id,
        data=json.dumps(dict(state=CustomImage.STATE_COMPLETED))
    )
    assert response.status_code == 200
    ci2 = rmaker.make_authenticated_admin_request(
        path='/api/v1/custom_images/%s' % ci_id
    ).json
    assert ci2.get('completed_at')
    assert ci2.get('started_at') == ci.get('started_at')


def test_post_custom_image_no_access(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that users with no access cannot post custom images
    """
    definition = {
        'base_image': 'registry.io/image:latest',
        'user': 'user',
        'image_content': []
    }

    # Anonymous
    response = rmaker.make_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name='ci-2',
            workspace_id=pri_data.known_workspace_id,
            definition=definition)
        )
    )
    assert response.status_code == 401

    # Workspace member
    response = rmaker.make_authenticated_user_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name='ci-2',
            workspace_id=pri_data.known_workspace_id,
            definition=definition)
        )
    )
    assert response.status_code == 403

    # Workspace owner for a different workspace
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name='ci-2',
            workspace_id=pri_data.known_workspace_id_2,
            definition=definition)
        )
    )
    assert response.status_code == 403


def test_post_and_delete_custom_image(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that posting and deleting custom images work as expected
    """
    definition = {
        'base_image': 'registry.io/image:latest',
        'user': 'user',
        'image_content': []
    }

    # Workspace manager
    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name='ci-2',
            workspace_id=pri_data.known_workspace_id,
            definition=definition)
        )
    )
    assert response.status_code == 200
    ci_id = response.json.get('id')
    assert rmaker.make_authenticated_workspace_owner2_request(
        method='GET', path=f'/api/v1/custom_images/{ci_id}'
    ).json.get('name') == 'ci-2'

    response = rmaker.make_authenticated_workspace_owner2_request(
        method='DELETE', path=f'/api/v1/custom_images/{ci_id}'
    )
    assert response.status_code == 202

    response = rmaker.make_authenticated_workspace_owner2_request(
        method='GET', path=f'/api/v1/custom_images/{ci_id}'
    )
    assert response.json.get('to_be_deleted')

    # Workspace owner
    response = rmaker.make_authenticated_workspace_owner_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name='ci-3',
            workspace_id=pri_data.known_workspace_id,
            definition=definition)
        )
    )
    assert response.status_code == 200

    ci_id = response.json.get('id')
    assert rmaker.make_authenticated_workspace_owner_request(
        method='GET', path=f'/api/v1/custom_images/{ci_id}'
    ).json.get('name') == 'ci-3'
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE', path=f'/api/v1/custom_images/{ci_id}'
    )
    assert response.status_code == 202

    response = rmaker.make_authenticated_workspace_owner_request(
        method='GET', path=f'/api/v1/custom_images/{ci_id}'
    )
    assert response.json.get('to_be_deleted')


def test_post_custom_image_invalid_data(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that invalid custom image data raises an error
    """
    definition = {
        'base_image': 'registry.io/image:latest',
        'user': 'user',
        'image_content': []
    }

    invalid_data = [
        dict(name='', workspace_id=pri_data.known_workspace_id, definition=definition),
        dict(name='c2', workspace_id='', definition=definition),
        dict(name='c2', workspace_id=pri_data.known_workspace_id, definition={}),
        dict(name='c2', workspace_id='not-there', definition=definition),
    ]
    for data in invalid_data:
        response = rmaker.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/custom_images',
            data=json.dumps(data),
        )
        assert response.status_code == 422

    invalid_definitions = [
        (dict(
            base_image='registry.io/image:latest',
            user='user',
            image_content=[
                dict(kind='aptPackages', data='pöppö')
            ]
        ), 'invalid apt package'),
        (dict(
            base_image='registry.io/image:latest',
            user='user',
            image_content=[
                dict(kind='nosuchkind', data='foo')
            ]
        ), 'unknown kind'),
    ]
    for invalid_def, resp in invalid_definitions:
        data = dict(name='test', workspace_id=pri_data.known_workspace_id, definition=invalid_def)
        response = rmaker.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/custom_images',
            data=json.dumps(data),
        )
        assert response.status_code == 422
        assert response.json.get('message').startswith(resp)


def test_custom_image_quota(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that only 10 custom images are allowed per workspace
    """
    definition = {
        'base_image': 'registry.io/image:latest',
        'user': 'user',
        'image_content': []
    }

    # owner-2 tries to post 10 new custom images when they already have one,
    # test that the last one fails
    for i in range(10):
        response = rmaker.make_authenticated_workspace_owner2_request(
            method='POST',
            path='/api/v1/custom_images',
            data=json.dumps(dict(
                name=f'new_ci-{i}',
                workspace_id=pri_data.known_workspace_id,
                definition=definition)
            )
        )
        if i != 9:
            assert response.status_code == 200
        else:
            # 10th new custom image is over quota (owner-2 had one to begin with)
            assert response.status_code == 422

    # test that deleting a custom images frees quota
    response = rmaker.make_authenticated_workspace_owner_request(
        method='DELETE', path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
    )
    assert response.status_code == 202

    response = rmaker.make_authenticated_admin_request(
        method='PATCH',
        path='/api/v1/custom_images/%s' % pri_data.known_custom_image_id,
        data=json.dumps(dict(state=CustomImage.STATE_DELETED))
    )
    assert response.status_code == 200

    response = rmaker.make_authenticated_workspace_owner2_request(
        method='POST',
        path='/api/v1/custom_images',
        data=json.dumps(dict(
            name=pri_data.known_custom_image_id,
            workspace_id=pri_data.known_workspace_id,
            definition=definition)
        )
    )
    # Posting should work again now that quota has been freed
    assert response.status_code == 200


def test_create_dockerfile_from_definition(rmaker: RequestMaker, pri_data: PrimaryData):
    """
    Test that valid dockerfile definitions do not raise exceptions and invalid ones raise the
    expected exceptions.
    """
    valid_image_content = [
        [{"kind": "aptPackages", "data": "vim"}, {"kind": "pipPackages", "data": "arrow"}],
        [{"kind": "pipPackages", "data": "arrow==1.0.0 nltk torch"}],
        [{"kind": "pipPackages", "data": "arrow==1.0.0"}],
        [{"kind": "aptPackages", "data": "apache2=2.3.35-4ubuntu1"}],
        [{"kind": "aptPackages", "data": "apache2=2.3.35-4ubuntu1 vim nano"}],
        [],
    ]

    for ic in valid_image_content:
        valid_definition = {
            "base_image": "registry.io/image:latest",
            "user": "user",
            "image_content": ic
        }
        dockerfile = create_dockerfile_from_definition(valid_definition)
        for content in ic:
            assert content["data"] in dockerfile

    invalid_image_content = [
        {"ic": [{"kind": "pipPackages", "data": "arrow;torch"}], "expected_error": "invalid pip package"},
        {"ic": [{"kind": "pipPackages", "data": "arrow, torch"}], "expected_error": "invalid pip package"},
        {"ic": [{"kind": "pipPackages", "data": "torch==${TORCH_VERSION}"}], "expected_error": "invalid pip package"},
        {"ic": [{"kind": "aptPackages", "data": "vim; rm -rf"}], "expected_error": "invalid apt package"},
        {"ic": [{"kind": "aptPackages", "data": "vim&&ls"}], "expected_error": "invalid apt package"},
        {"ic": [{"kind": "pipPackages", "data": "pöppö"}], "expected_error": "invalid pip package"},
        {"ic": [{"kind": "aptPackages", "data": "pöppö"}], "expected_error": "invalid apt package"},
    ]

    for data in invalid_image_content:
        invalid_definition = {
            "base_image": "registry.io/image:latest",
            "user": "user",
            "image_content": data["ic"]
        }
        with pytest.raises(ValueError, match=data["expected_error"]):
            create_dockerfile_from_definition(invalid_definition)

    invalid_base_image_data = [
        {"base_image": "registry.io/image:foo", "expected_error": "invalid base image"},
        {"base_image": "", "expected_error": "base_image cannot be empty"},
        # test that a base image from a disabled application template is not accepted:
        {"base_image": "registry.io/disabled_image:latest", "expected_error": "invalid base image"},
    ]

    for base_image_data in invalid_base_image_data:
        invalid_definition = {
            "base_image": base_image_data["base_image"],
            "user": "user",
            "image_content": []
        }
        with pytest.raises(ValueError, match=base_image_data["expected_error"]):
            create_dockerfile_from_definition(invalid_definition)
