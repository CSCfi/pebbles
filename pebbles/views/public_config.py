from flask_restful import fields, marshal_with
from flask import Blueprint as FlaskBlueprint

import logging

import flask_restful as restful

from pebbles.app import app

variable_fields = {
    'key': fields.String,
    'value': fields.Raw,
}

variables = FlaskBlueprint('variables', __name__)
PUBLIC_CONFIG_VARIABLES = (
    'INSTALLATION_NAME',
    'INSTALLATION_DESCRIPTION',
    'BRAND_IMAGE_URL',
    'AGREEMENT_TITLE',
    'AGREEMENT_LOGO_PATH',
    'COURSE_REQUEST_FORM_URL',
    'TERMS_OF_USE_URL',
    'COOKIES_POLICY_URL',
    'PRIVACY_POLICY_URL',
    'ACCESSIBILITY_STATEMENT_URL',
    'CONTACT_EMAIL',
    'SHORT_DESCRIPTION',
    'OAUTH2_LOGIN_ENABLED',
    'SERVICE_DOCUMENTATION_URL',
    'SERVICE_ANNOUNCEMENT',
)


class PublicConfigList(restful.Resource):
    """The list of variables that are needed for the frontend to construct a branded page.
    Installation name, logo url etc.
    """

    @marshal_with(variable_fields)
    def get(self):
        try:
            public_vars = []
            for public_var in PUBLIC_CONFIG_VARIABLES:
                public_vars.append({'key': public_var, 'value': app.config[public_var]})
            return public_vars

        except Exception as ex:
            logging.error("error in retrieving variables" + str(ex))
            return []
