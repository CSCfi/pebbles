from flask_restful import fields, marshal_with
from flask import Blueprint as FlaskBlueprint

import logging

import flask_restful as restful
from pebbles.config import BaseConfig

# Point to be noted, there will be driver specific configs later on
# how about the readonly vars now?
variable_fields = {
    'key': fields.String,
    'value': fields.Raw,
}


variables = FlaskBlueprint('variables', __name__)
PUBLIC_CONFIG_VARIABLES = (
    'INSTALLATION_NAME',
    'INSTALLATION_DESCRIPTION',
    'BRAND_IMAGE',
    'COURSE_REQUEST_FORM',
    'SHORT_DESCRIPTION',
    'HAKA_INSTITUTION_LIST',
    'OAUTH2_LOGIN_ENABLED',
    'OAUTH2_LOGO_URL',
)


class PublicVariableList(restful.Resource):
    """The list of variables that are needed for the frontend to construct a branded page.
    Installation name, logo url etc.

    Additionally this is the only API call that does not require authentication and therefore it is a good place to
    monitor that the back-end (and database connection) are healthy.
    """

    @marshal_with(variable_fields)
    def get(self):
        try:
            dynamic_config = BaseConfig()
            public_vars = []
            for public_var in PUBLIC_CONFIG_VARIABLES:
                public_vars.append({'key': public_var, 'value': dynamic_config[public_var]})
            return public_vars

        except Exception as ex:
            logging.error("error in retrieving variables" + str(ex))
            return []
