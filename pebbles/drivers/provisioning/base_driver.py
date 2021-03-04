"""Drivers abstract resource provisioning strategies to the system and user.

A driver object can be instantiated to connect to some end point to CRUD
resources like Docker containers or OpenStack virtual machines.
"""

import abc
import json

from pebbles.client import PBClient
from pebbles.models import Instance


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

    def update(self, token, instance_id):
        """ an update call  updates the status of an instance.

        If an instance is
          * queued it will be provisioned
          * starting it will be checked for readiness
          * tagged to be deleted it is deprovisioned
        """
        self.logger.debug("update('%s')" % instance_id)

        pbclient = self.get_pb_client(token)
        instance = pbclient.get_instance(instance_id)

        if not instance['to_be_deleted']:
            if instance['state'] in [Instance.STATE_QUEUEING]:
                self.logger.info('provisioning starting for %s' % instance.get('name'))
                self.provision(token, instance_id)
                self.logger.info('provisioning done for %s' % instance.get('name'))
            if instance['state'] in [Instance.STATE_STARTING]:
                self.logger.debug('checking readiness of %s' % instance.get('name'))
                self.check_readiness(token, instance_id)
            if instance['state'] in [Instance.STATE_RUNNING] and instance['log_fetch_pending']:
                self.logger.info('fetching instance logs for %s' % instance.get('name'))
                self.fetch_running_instance_logs(token, instance_id)
                pass
            else:
                self.logger.debug("update('%s') - nothing to do for %s" % (instance_id, instance))
        elif instance['state'] not in [Instance.STATE_DELETED]:
            self.logger.info('deprovisioning starting for %s' % instance.get('name'))
            self.deprovision(token, instance_id)
            pbclient.clear_running_instance_logs(instance_id)
            self.logger.info('deprovisioning done for %s' % instance.get('name'))

    def update_connectivity(self, token, instance_id):
        self.logger.debug('update connectivity')
        self.do_update_connectivity(token, instance_id)

    def provision(self, token, instance_id):
        self.logger.debug('starting provisioning')
        pbclient = self.get_pb_client(token)

        try:
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_PROVISIONING})
            self.logger.debug('calling subclass do_provision')

            new_state = self.do_provision(token, instance_id)
            self.logger.debug('got new state for instance: %s' % new_state)
            if not new_state:
                new_state = Instance.STATE_RUNNING

            pbclient.do_instance_patch(instance_id, {'state': new_state})
        except Exception as e:
            self.logger.exception('do_provision raised %s' % e)
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_FAILED})
            raise e

    def check_readiness(self, token, instance_id):
        self.logger.debug('checking provisioning readiness')
        pbclient = self.get_pb_client(token)

        try:
            self.logger.debug('calling subclass do_check_readiness')

            instance_data = self.do_check_readiness(token, instance_id)
            if instance_data:
                instance = pbclient.get_instance(instance_id)
                self.logger.info('instance %s ready' % instance.get('name'))
                patch_data = dict(
                    state=Instance.STATE_RUNNING,
                    instance_data=json.dumps(instance_data)
                )
                pbclient.do_instance_patch(instance_id, patch_data)

        except Exception as e:
            self.logger.exception('do_check_readiness raised %s' % e)
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_FAILED})
            raise e

    def deprovision(self, token, instance_id):
        self.logger.debug('starting deprovisioning')
        pbclient = self.get_pb_client(token)

        try:
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_DELETING})
            self.logger.debug('calling subclass do_deprovision')
            state = self.do_deprovision(token, instance_id)

            # check if we got STATE_DELETING from subclass, indicating a retry is needed
            if state and state == Instance.STATE_DELETING:
                self.logger.info('instance deletion will be retried for %s', instance_id)
            elif state is None:
                self.logger.debug('finishing deprovisioning')
                pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_DELETED})
            else:
                raise RuntimeError('Received invalid state %s from do_deprovision()' % state)
        except Exception as e:
            self.logger.exception('do_deprovision raised %s' % e)
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_FAILED})
            raise e

    def housekeep(self, token):
        """ called periodically to do housekeeping tasks.
        """
        self.logger.debug('housekeep')
        self.do_housekeep(token)

    def fetch_running_instance_logs(self, token, instance_id):
        """ get and uploads the logs of an instance which is in running state """
        logs = self.do_get_running_logs(token, instance_id)
        pbclient = self.get_pb_client(token)
        if logs:
            # take only last 32k characters at maximum (64k char limit in the database, take half of that to
            # make sure we don't overflow it even in the theoretical case of all characters two bytes)
            logs = logs[-32768:]
            pbclient.update_instance_running_logs(instance_id, logs)
        pbclient.do_instance_patch(instance_id, json_data={'log_fetch_pending': False})

    @abc.abstractmethod
    def is_expired(self):
        """ called by worker to check if a new instance of this driver needs to be created
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
    def do_update_connectivity(self, token, instance_id):
        """ Each driver must implement this method but it doesn't have to do
        anything.

        This can be used to e.g. open holes in firewalls or to update a proxy
        to route traffic to an instance.
        """
        pass

    @abc.abstractmethod
    def do_provision(self, token, instance_id):
        """ The steps to take to provision an instance.
        Probably doesn't make sense not to implement.
        """
        pass

    @abc.abstractmethod
    def do_check_readiness(self, token, instance_id):
        """ Check if an instance in 'STATE_PROVISIONING' is ready yet """
        pass

    @abc.abstractmethod
    def do_deprovision(self, token, instance_id):
        """ The steps to take to deprovision an instance.
        """
        pass

    @abc.abstractmethod
    def do_get_running_logs(self, token, instance_id):
        """implement to return running logs for an instance as a string"""
        pass
