from datetime import datetime, timezone
import logging
import re

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import g, abort
from flask_restful import fields, reqparse, marshal_with
from sqlalchemy import select
from sqlalchemy.sql.expression import true

from pebbles import rules
from pebbles.forms import CustomImageForm
from pebbles.models import db, CustomImage, Workspace, ApplicationTemplate
from pebbles.utils import requires_admin
from pebbles.views.commons import auth, is_workspace_manager, requires_workspace_manager_or_admin

custom_images = FlaskBlueprint('custom_images', __name__)

custom_image_fields = {
    'id': fields.String,
    'workspace_id': fields.String,
    'name': fields.String,
    'tag': fields.String,
    'definition': fields.Raw,
    'dockerfile': fields.String,
    'created_at': fields.DateTime(dt_format='iso8601'),
    'started_at': fields.DateTime(dt_format='iso8601'),
    'completed_at': fields.DateTime(dt_format='iso8601'),
    'state': fields.String,
    'to_be_deleted': fields.Boolean,
    'build_system_id': fields.String,
    'build_system_output': fields.String,
    'url': fields.String,
}


class CustomImageView(restful.Resource):

    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(custom_image_fields)
    def get(self, custom_image_id):
        user = g.user
        opts = dict(custom_image_id=custom_image_id)
        custom_image = db.session.scalar(rules.generate_custom_image_query(user, opts))
        if not custom_image:
            abort(404)

        return custom_image

    patch_parser = reqparse.RequestParser()
    patch_parser.add_argument('state', type=str, location='json')
    patch_parser.add_argument('url', type=str, location='json')
    patch_parser.add_argument('tag', type=str, location='json')
    patch_parser.add_argument('build_system_id', type=str, location='json')
    patch_parser.add_argument('build_system_output', type=str, location='json')

    @auth.login_required
    @requires_admin
    def patch(self, custom_image_id):
        user = g.user
        opts = dict(custom_image_id=custom_image_id)
        custom_image = db.session.scalar(rules.generate_custom_image_query(user, opts))
        if not custom_image:
            abort(404)

        args = self.patch_parser.parse_args()
        if args.get('state') is not None:
            state = args.get('state')
            try:
                custom_image.state = state
            except ValueError as e:
                return str(e), 422
            if not custom_image.started_at and state == CustomImage.STATE_BUILDING:
                custom_image.started_at = datetime.now(timezone.utc)
            if not custom_image.completed_at and state in (CustomImage.STATE_FAILED, CustomImage.STATE_COMPLETED):
                custom_image.completed_at = datetime.now(timezone.utc)

        if args.get('build_system_id') is not None:
            custom_image.build_system_id = args['build_system_id']

        if args.get('build_system_output') is not None:
            custom_image.build_system_output = args['build_system_output']

        if args.get('url') is not None:
            custom_image.url = args['url']

        if args.get('tag') is not None:
            custom_image.tag = args['tag']

        db.session.commit()

        return restful.marshal(custom_image, custom_image_fields)

    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(custom_image_fields)
    def delete(self, custom_image_id):
        user = g.user
        opts = dict(custom_image_id=custom_image_id)
        custom_image = db.session.scalar(rules.generate_custom_image_query(user, opts))
        if not custom_image:
            abort(404)
        custom_image.to_be_deleted = True
        db.session.commit()
        return custom_image, 202


class CustomImageList(restful.Resource):
    list_parser = reqparse.RequestParser()
    list_parser.add_argument('limit', type=int, location='args')
    list_parser.add_argument('workspace_id', type=str, location='args')
    list_parser.add_argument('unfinished', type=str, location='args')

    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(custom_image_fields)
    def get(self):
        user = g.user
        args = self.list_parser.parse_args()
        s = rules.generate_custom_image_query(user, args)
        images = db.session.execute(s).scalars().all()
        return images

    @auth.login_required
    @requires_workspace_manager_or_admin
    @marshal_with(custom_image_fields)
    def post(self):
        form = CustomImageForm()
        if not form.validate_on_submit():
            logging.warning('form validation error on creating custom image')
            return form.errors, 422

        user = g.user
        workspace_id = form.workspace_id.data
        workspace = Workspace.query.filter_by(id=workspace_id).first()
        if not workspace:
            abort(422)
        if not user.is_admin and not is_workspace_manager(user, workspace):
            logging.warning("invalid workspace for the user")
            abort(403)

        # check custom image quota
        s = select(CustomImage).where(CustomImage.workspace_id == workspace_id)
        workspace_custom_images = db.session.scalars(s).all()
        num_workspace_custom_images = [
            ci.state != CustomImage.STATE_DELETED for ci in workspace_custom_images].count(True)

        if num_workspace_custom_images >= 10:
            logging.warning('Custom image quota is reached')
            return dict(
                message='You reached maximum number of custom images per workspace'
            ), 422

        custom_image = CustomImage()
        try:
            custom_image.name = form.name.data
            custom_image.workspace_id = workspace_id
            custom_image.definition = form.definition.data
            custom_image.dockerfile = create_dockerfile_from_definition(form.definition.data)
        except ValueError as e:
            abort(422, str(e))

        db.session.add(custom_image)
        db.session.commit()

        return custom_image


def validate_apt_package(package: str):
    """
    Remove trailing whitespace from apt package name and validate.
    Raise ValueError if package name contains invalid characters.
    """
    package = package.strip()
    if not re.match(r'^[a-z][a-z0-9\-+.=~]+$', package):
        raise ValueError(f'invalid apt package: {package}')


def validate_pip_package(package: str):
    """
    Remove trailing whitespace from pip package name and validate.
    Raise ValueError if package name contains invalid characters.
    """
    package = package.strip()
    if not re.match(r'^[a-zA-Z0-9\-_.=]+$', package):
        raise ValueError(f'invalid pip package: {package}')


def validate_base_image(base_image: str):
    """
    Make sure that the base image is from existing application templates.
    Raise ValueError if not.
    """
    if not base_image:
        raise ValueError('base_image cannot be empty')

    s = select(ApplicationTemplate).where(ApplicationTemplate.is_enabled == true())
    enabled_application_templates = db.session.scalars(s).all()
    base_images = [template.base_config.get("image") for template in list(enabled_application_templates)]
    if base_image not in base_images:
        raise ValueError(f'invalid base image: {base_image}')


def create_dockerfile_from_definition(definition: dict):
    validate_base_image(definition.get("base_image"))
    lines = [f'FROM {definition.get("base_image")}']

    user = definition.get('user')
    for ic in definition.get('image_content', []):

        if ic.get('kind') == 'aptPackages':
            if not ic.get('data'):
                raise ValueError('aptPackages definition must have non-empty "data" field')
            for data in ic.get('data').split(" "):
                validate_apt_package(data)

            lines.append('')
            lines.append(f'# {ic.get("kind")}')
            lines.append('USER root')
            lines.append(f'RUN apt-get update && apt-get install -y {ic["data"]} && apt-get clean')
            lines.append(f'USER {user}')

        elif ic.get('kind') == 'pipPackages':
            if not ic.get('data'):
                raise ValueError('pipPackages definition must have non-empty "data" field')
            for data in ic.get('data').split(" "):
                validate_pip_package(data)

            lines.append('')
            lines.append(f'# {ic.get("kind")}')
            lines.append(f'RUN pip --no-cache-dir install --upgrade {ic["data"]}')

        elif ic.get('kind') == 'condaForgePackages':
            if not ic.get('data'):
                raise ValueError('condaForgePackages definition must have non-empty "data" field')
            for data in ic.get('data').split(" "):
                # pip package validation should work for conda-forge packages as well
                validate_pip_package(data)

            lines.append('')
            lines.append(f'# {ic.get("kind")}')
            lines.append(f'RUN conda install -c conda-forge --yes {ic["data"]}')

        else:
            raise ValueError(f'unknown kind in image_content: {ic.get("kind")}')

    return '\n'.join(lines)


if __name__ == '__main__':
    print(create_dockerfile_from_definition(
        dict(
            base_image='example.org/foo/bar:main',
            user='jovyan',
            image_content=[
                dict(kind='aptPackages', data='foo'),
                dict(kind='pipPackages', data='bar'),
                dict(kind='condaForgePackages', data='foobar'),
            ],
        )
    ))
