"""Drivers abstract resource provisioning strategies to the system and user.

A driver object can be instantiated to connect to some end point to CRUD
resources like Docker containers or OpenStack virtual machines.
"""

import abc
import json

from pebbles.client import PBClient
from pebbles.models import ApplicationSession


class ProvisioningDriverBase(object):
    """ This class functions as the base for other classes.
    """
    config = {}

    def __init__(self, logger, config, cluster_config):
        self.logger = logger
        self.config = config
        self.cluster_config = cluster_config
        self.logger.info('driver for cluster %s created' % cluster_config.get('name'))

    def get_pb_client(self, token):
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        return pbclient

    def update(self, token, application_session_id):
        """ an update call  updates the status of an application_session.

        If an application_session is
          * queued it will be provisioned
          * starting it will be checked for readiness
          * tagged to be deleted it is deprovisioned
        """
        self.logger.debug("update('%s')" % application_session_id)

        pbclient = self.get_pb_client(token)
        application_session = pbclient.get_application_session(application_session_id)

        if not application_session['to_be_deleted']:
            if application_session['state'] in [ApplicationSession.STATE_QUEUEING]:
                self.logger.info('provisioning starting for %s' % application_session.get('name'))
                self.provision(token, application_session_id)
                self.logger.info('provisioning done for %s' % application_session.get('name'))
            if application_session['state'] in [ApplicationSession.STATE_STARTING]:
                self.logger.debug('checking readiness of %s' % application_session.get('name'))
                self.check_readiness(token, application_session_id)
            if application_session['state'] in [ApplicationSession.STATE_RUNNING] and application_session['log_fetch_pending']:
                self.logger.info('fetching application_session logs for %s' % application_session.get('name'))
                self.fetch_running_application_session_logs(token, application_session_id)
                pass
            else:
                self.logger.debug("update('%s') - nothing to do for %s" % (application_session_id, application_session))
        elif application_session['state'] not in [ApplicationSession.STATE_DELETED]:
            self.logger.info('deprovisioning starting for %s' % application_session.get('name'))
            self.deprovision(token, application_session_id)
            pbclient.clear_running_application_session_logs(application_session_id)
            self.logger.info('deprovisioning done for %s' % application_session.get('name'))

    def provision(self, token, application_session_id):
        self.logger.debug('starting provisioning')
        pbclient = self.get_pb_client(token)
        pbclient.add_provisioning_log(application_session_id, 'created')

        try:
            pbclient.do_application_session_patch(application_session_id, {'state': ApplicationSession.STATE_PROVISIONING})
            self.logger.debug('calling subclass do_provision')

            new_state = self.do_provision(token, application_session_id)
            self.logger.debug('got new state for application_session: %s' % new_state)
            if not new_state:
                new_state = ApplicationSession.STATE_RUNNING

            pbclient.do_application_session_patch(application_session_id, {'state': new_state})
        except Exception as e:
            self.logger.exception('do_provision raised %s' % e)
            self.logger.warn('application_session provisioning failed for %s' % application_session_id)
            pbclient.do_application_session_patch(application_session_id, {'state': ApplicationSession.STATE_FAILED})
            raise e

    def check_readiness(self, token, application_session_id):
        self.logger.debug('checking provisioning readiness')
        pbclient = self.get_pb_client(token)

        try:
            self.logger.debug('calling subclass do_check_readiness')

            session_data = self.do_check_readiness(token, application_session_id)
            # if we got a result, the session is ready and the returned value is session_data
            if session_data:
                application_session = pbclient.get_application_session(application_session_id)
                self.logger.info('application_session %s ready' % application_session.get('name'))
                patch_data = dict(
                    state=ApplicationSession.STATE_RUNNING,
                    session_data=json.dumps(session_data)
                )
                pbclient.do_application_session_patch(application_session_id, patch_data)
                pbclient.add_provisioning_log(application_session_id, 'ready')

        except Exception as e:
            self.logger.exception('do_check_readiness raised %s' % e)
            pbclient.do_application_session_patch(application_session_id, {'state': ApplicationSession.STATE_FAILED})
            raise e

    def deprovision(self, token, application_session_id):
        self.logger.debug('starting deprovisioning')
        pbclient = self.get_pb_client(token)

        try:
            pbclient.do_application_session_patch(application_session_id, {'state': ApplicationSession.STATE_DELETING})
            self.logger.debug('calling subclass do_deprovision')
            state = self.do_deprovision(token, application_session_id)

            # check if we got STATE_DELETING from subclass, indicating a retry is needed
            if state and state == ApplicationSession.STATE_DELETING:
                self.logger.info('application_session deletion will be retried for %s', application_session_id)
                pbclient.add_provisioning_log(application_session_id, 'deprovisioning - retrying')
            elif state is None:
                self.logger.debug('finishing deprovisioning')
                pbclient.do_application_session_patch(application_session_id, {'state': ApplicationSession.STATE_DELETED})
            else:
                raise RuntimeError('Received invalid state %s from do_deprovision()' % state)
        except Exception as e:
            self.logger.exception('do_deprovision raised %s' % e)
            pbclient.do_application_session_patch(application_session_id, {'state': ApplicationSession.STATE_FAILED})
            raise e

    def housekeep(self, token):
        """ called periodically to do housekeeping tasks.
        """
        self.logger.debug('housekeep')
        self.do_housekeep(token)

    def fetch_running_application_session_logs(self, token, application_session_id):
        """ get and uploads the logs of an application_session which is in running state """
        logs = self.do_get_running_logs(token, application_session_id)
        pbclient = self.get_pb_client(token)
        if logs:
            # take only last 32k characters at maximum (64k char limit in the database, take half of that to
            # make sure we don't overflow it even in the theoretical case of all characters two bytes)
            logs = logs[-32768:]
            pbclient.update_application_session_running_logs(application_session_id, logs)
        pbclient.do_application_session_patch(application_session_id, json_data={'log_fetch_pending': False})

    @abc.abstractmethod
    def is_expired(self):
        """ called by worker to check if a new application_session of this driver needs to be created
        """
        pass

    @abc.abstractmethod
    def do_housekeep(self, token):
        """Each plugin must implement this method but it doesn't have to do
        anything. Can be used to e.g. determine that a system should scale up
        or down.
        """
        pass

    @abc.abstractmethod
    def do_provision(self, token, application_session_id):
        """ The steps to take to provision an application_session.
        Probably doesn't make sense not to implement.
        """
        pass

    @abc.abstractmethod
    def do_check_readiness(self, token, application_session_id):
        """ Check if an application_session in 'STATE_PROVISIONING' is ready yet """
        pass

    @abc.abstractmethod
    def do_deprovision(self, token, application_session_id):
        """ The steps to take to deprovision an application_session.
        """
        pass

    @abc.abstractmethod
    def do_get_running_logs(self, token, application_session_id):
        """implement to return running logs for an application_session as a string"""
        pass
