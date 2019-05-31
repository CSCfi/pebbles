from flask import abort, request, Response, Blueprint

import datetime
import logging
import re

from pebbles.models import InstanceToken
from pebbles.server import restful

authorize_instances = Blueprint('authorize_instances', __name__)


class AuthorizeInstancesView(restful.Resource):
    def get(self):
        token = ''
        instance_id = ''
        # The idea here is to check if the original-token and instance-id  headers are already present, sent by the nginx proxy of the openshift app,
        # if the headers are present that means the authentication had taken place previously and a cookie exists for the openshift app,
        # in this case - obtain the info contained in the headers
        if 'ORIGINAL-TOKEN' in request.headers and 'INSTANCE-ID' in request.headers:
            token = request.headers['ORIGINAL-TOKEN']
            instance_id = request.headers['INSTANCE-ID']
        # otherwise, the x-original-uri consists of the query string info (which is sent by the openshift driver to the nginx of the openshift app)

        # The query string has the token info and instance id
        # NOTE: This is only used when the authentication is being done for the first time!
        elif 'X-ORIGINAL-URI' in request.headers:
            h_uri = request.headers['X-ORIGINAL-URI']
            regex_query_capture = re.search('.*\\?(.*)=(.*)&(.*)=(.*)', h_uri)  # parse the query string
            if regex_query_capture and len(regex_query_capture.groups()) == 4:
                if regex_query_capture.group(1) == 'token' and regex_query_capture.group(3) == 'instance_id':
                    token = regex_query_capture.group(2)
                    instance_id = regex_query_capture.group(4)
                elif regex_query_capture.group(1) == 'instance_id' and regex_query_capture.group(3) == 'token':
                    instance_id = regex_query_capture.group(2)
                    token = regex_query_capture.group(4)

        if not token and not instance_id:
            logging.warn('No instance token or id found from the headers')
            return abort(401)

        instance_token_obj = InstanceToken.query.filter_by(token=token).first()
        if not instance_token_obj:
            logging.warn("instance token object %s not found" % token)
            return abort(401)

        curr_time = datetime.datetime.utcnow()
        expires_on = instance_token_obj.expires_on

        if curr_time > expires_on:
            logging.warn("instance token %s has expired" % token)
            return abort(403)

        if instance_token_obj.instance_id != instance_id:
            logging.warn("instance id %s from the token does not match the instance_id %s passed as a parameter" % (instance_token_obj.instance_id, instance_id))
            return abort(403)

        resp = Response("Authorized")
        # send the headers back to nginx proxy running on the openshift based instance,
        # which is going to store it as a cookie for the next time, the authorization takes place
        resp.headers["TOKEN"] = instance_token_obj.token
        resp.headers["INSTANCE-ID"] = instance_id
        return resp
