"""Drivers abstract resource provisioning strategies to the system and user.

A driver object can be instantiated to connect to some end point to CRUD
resources like Docker containers or OpenStack virtual machines.
"""

import abc
import json

from pebbles.client import PBClient
from pebbles.models import EnvironmentSession


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

    @staticmethod
    def get_configuration():
        return {
            'schema': {
                'type': 'object',
                'properties': {
                    'name': {
                        'type': 'string'
                    }
                },
            },
            'form': [
                {'type': 'help', 'helpvalue': 'config is empty'},
                '*',
                {'style': 'btn-info', 'title': 'Create', 'type': 'submit'}
            ], 'model': {}}

    def update(self, token, environment_session_id):
        """ an update call  updates the status of an environment_session.

        If an environment_session is
          * queued it will be provisioned
          * starting it will be checked for readiness
          * tagged to be deleted it is deprovisioned
        """
        self.logger.debug("update('%s')" % environment_session_id)

        pbclient = self.get_pb_client(token)
        environment_session = pbclient.get_environment_session(environment_session_id)

        if not environment_session['to_be_deleted']:
            if environment_session['state'] in [EnvironmentSession.STATE_QUEUEING]:
                self.logger.info('provisioning starting for %s' % environment_session.get('name'))
                self.provision(token, environment_session_id)
                self.logger.info('provisioning done for %s' % environment_session.get('name'))
            if environment_session['state'] in [EnvironmentSession.STATE_STARTING]:
                self.logger.debug('checking readiness of %s' % environment_session.get('name'))
                self.check_readiness(token, environment_session_id)
            if environment_session['state'] in [EnvironmentSession.STATE_RUNNING] and environment_session['log_fetch_pending']:
                self.logger.info('fetching environment_session logs for %s' % environment_session.get('name'))
                self.fetch_running_environment_session_logs(token, environment_session_id)
                pass
            else:
                self.logger.debug("update('%s') - nothing to do for %s" % (environment_session_id, environment_session))
        elif environment_session['state'] not in [EnvironmentSession.STATE_DELETED]:
            self.logger.info('deprovisioning starting for %s' % environment_session.get('name'))
            self.deprovision(token, environment_session_id)
            pbclient.clear_running_environment_session_logs(environment_session_id)
            self.logger.info('deprovisioning done for %s' % environment_session.get('name'))

    def provision(self, token, environment_session_id):
        self.logger.debug('starting provisioning')
        pbclient = self.get_pb_client(token)
        pbclient.add_provisioning_log(environment_session_id, 'starting provisioning')

        try:
            pbclient.do_environment_session_patch(environment_session_id, {'state': EnvironmentSession.STATE_PROVISIONING})
            self.logger.debug('calling subclass do_provision')

            new_state = self.do_provision(token, environment_session_id)
            self.logger.debug('got new state for environment_session: %s' % new_state)
            if not new_state:
                new_state = EnvironmentSession.STATE_RUNNING

            pbclient.do_environment_session_patch(environment_session_id, {'state': new_state})
        except Exception as e:
            self.logger.exception('do_provision raised %s' % e)
            self.logger.warn('environment_session provisioning failed for %s' % environment_session_id)
            pbclient.do_environment_session_patch(environment_session_id, {'state': EnvironmentSession.STATE_FAILED})
            raise e

    def check_readiness(self, token, environment_session_id):
        self.logger.debug('checking provisioning readiness')
        pbclient = self.get_pb_client(token)

        try:
            self.logger.debug('calling subclass do_check_readiness')

            session_data = self.do_check_readiness(token, environment_session_id)
            if session_data:
                environment_session = pbclient.get_environment_session(environment_session_id)
                self.logger.info('environment_session %s ready' % environment_session.get('name'))
                patch_data = dict(
                    state=EnvironmentSession.STATE_RUNNING,
                    session_data=json.dumps(session_data)
                )
                pbclient.do_environment_session_patch(environment_session_id, patch_data)
                pbclient.add_provisioning_log(environment_session_id, 'checking readiness - ready')
            else:
                pbclient.add_provisioning_log(environment_session_id, 'checking readiness - not yet ready')

        except Exception as e:
            self.logger.exception('do_check_readiness raised %s' % e)
            pbclient.do_environment_session_patch(environment_session_id, {'state': EnvironmentSession.STATE_FAILED})
            raise e

    def deprovision(self, token, environment_session_id):
        self.logger.debug('starting deprovisioning')
        pbclient = self.get_pb_client(token)

        try:
            pbclient.do_environment_session_patch(environment_session_id, {'state': EnvironmentSession.STATE_DELETING})
            self.logger.debug('calling subclass do_deprovision')
            state = self.do_deprovision(token, environment_session_id)

            # check if we got STATE_DELETING from subclass, indicating a retry is needed
            if state and state == EnvironmentSession.STATE_DELETING:
                self.logger.info('environment_session deletion will be retried for %s', environment_session_id)
                pbclient.add_provisioning_log(environment_session_id, 'deprovisioning - retrying')
            elif state is None:
                self.logger.debug('finishing deprovisioning')
                pbclient.do_environment_session_patch(environment_session_id, {'state': EnvironmentSession.STATE_DELETED})
                pbclient.add_provisioning_log(environment_session_id, 'deprovisioning - done')
            else:
                raise RuntimeError('Received invalid state %s from do_deprovision()' % state)
        except Exception as e:
            self.logger.exception('do_deprovision raised %s' % e)
            pbclient.do_environment_session_patch(environment_session_id, {'state': EnvironmentSession.STATE_FAILED})
            raise e

    def housekeep(self, token):
        """ called periodically to do housekeeping tasks.
        """
        self.logger.debug('housekeep')
        self.do_housekeep(token)

    def fetch_running_environment_session_logs(self, token, environment_session_id):
        """ get and uploads the logs of an environment_session which is in running state """
        logs = self.do_get_running_logs(token, environment_session_id)
        pbclient = self.get_pb_client(token)
        if logs:
            # take only last 32k characters at maximum (64k char limit in the database, take half of that to
            # make sure we don't overflow it even in the theoretical case of all characters two bytes)
            logs = logs[-32768:]
            pbclient.update_environment_session_running_logs(environment_session_id, logs)
        pbclient.do_environment_session_patch(environment_session_id, json_data={'log_fetch_pending': False})

    @abc.abstractmethod
    def is_expired(self):
        """ called by worker to check if a new environment_session of this driver needs to be created
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
    def do_provision(self, token, environment_session_id):
        """ The steps to take to provision an environment_session.
        Probably doesn't make sense not to implement.
        """
        pass

    @abc.abstractmethod
    def do_check_readiness(self, token, environment_session_id):
        """ Check if an environment_session in 'STATE_PROVISIONING' is ready yet """
        pass

    @abc.abstractmethod
    def do_deprovision(self, token, environment_session_id):
        """ The steps to take to deprovision an environment_session.
        """
        pass

    @abc.abstractmethod
    def do_get_running_logs(self, token, environment_session_id):
        """implement to return running logs for an environment_session as a string"""
        pass
