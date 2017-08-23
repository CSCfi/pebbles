"""Drivers abstract resource provisioning strategies to the system and user.

A driver object can be instantiated to connect to some end point to CRUD
resources like Docker containers or OpenStack virtual machines.
"""

import json
import datetime
import os
import logging

import abc
import six

from pebbles.logger import PBInstanceLogHandler, PBInstanceLogFormatter
from pebbles.client import PBClient
from pebbles.models import Instance


@six.add_metaclass(abc.ABCMeta)
class ProvisioningDriverBase(object):
    """ This class functions as the base for other classes.
    """
    config = {}

    def __init__(self, logger, config):
        self.logger = logger
        self.config = config
        self._m2m_credentials = {}

    def get_m2m_credentials(self):
        """ Helper to read and parse m2m credentials. The file name
          is taken from M2M_CREDENTIAL_STORE config key.

        :return: a dict parsed from creds file
        """
        if getattr(self, '_m2m_credentials', None):
            self.logger.debug('m2m creds: found cached m2m creds')
            return self._m2m_credentials

        m2m_credential_store = self.config['M2M_CREDENTIAL_STORE']
        try:
            self._m2m_credentials = json.load(open(m2m_credential_store))

            debug_str = ['m2m_creds:']
            for key in self._m2m_credentials.keys():
                if key == 'OS_PASSWORD':
                    debug_str.append('OS_PASSWORD is set (not shown)')
                elif key in ('OS_USERNAME', 'OS_TENANT_NAME', 'OS_TENANT_ID', 'OS_AUTH_URL'):
                    debug_str.append('%s: %s' % (key, self._m2m_credentials[key]))
                else:
                    debug_str.append('other key %s' % key)
            self.logger.debug(' '.join(debug_str))
        except (IOError, ValueError) as e:
            self.logger.warn("Unable to parse M2M credentials from path %s %s" % (m2m_credential_store, e))

        return self._m2m_credentials

    def get_configuration(self):
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

    def get_backend_configuration(self):
        """ This method would return the default values of the backend vars
            which are specific to a particular driver.
        """
        return {}

    def update(self, token, instance_id):
        """ an update call  updates the status of an instance.

        If an instance is queued it will be provisioned, if should be deleted,
        it is.
        """
        self.logger.debug("update('%s')" % instance_id)

        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)
        instance = pbclient.get_instance(instance_id)
        if not instance['to_be_deleted'] and instance['state'] in [Instance.STATE_QUEUEING]:
            self.provision(token, instance_id)
        elif instance['to_be_deleted'] and instance['state'] not in [Instance.STATE_DELETED]:
            self.deprovision(token, instance_id)
            pbclient.clear_running_instance_logs(instance_id)
        else:
            self.logger.debug("update('%s') - nothing to do for %s" % (instance_id, instance))

    def update_connectivity(self, token, instance_id):
        self.logger.debug('update connectivity')
        self.do_update_connectivity(token, instance_id)

    def provision(self, token, instance_id):
        self.logger.debug('starting provisioning')
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        try:
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_PROVISIONING})
            self.logger.debug('calling subclass do_provision')

            new_state = self.do_provision(token, instance_id)
            if not new_state:
                new_state = Instance.STATE_RUNNING

            pbclient.do_instance_patch(instance_id, {'state': new_state})
        except Exception as e:
            self.logger.exception('do_provision raised %s' % e)
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_FAILED})
            raise e

    def deprovision(self, token, instance_id):
        self.logger.debug('starting deprovisioning')
        pbclient = PBClient(token, self.config['INTERNAL_API_BASE_URL'], ssl_verify=False)

        try:
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_DELETING})
            self.logger.debug('calling subclass do_deprovision')
            self.do_deprovision(token, instance_id)

            self.logger.debug('finishing deprovisioning')
            pbclient.do_instance_patch(instance_id, {'deprovisioned_at': datetime.datetime.utcnow()})
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_DELETED})
        except Exception as e:
            self.logger.exception('do_deprovision raised %s' % e)
            pbclient.do_instance_patch(instance_id, {'state': Instance.STATE_FAILED})
            raise e

    def housekeep(self, token):
        """ called periodically to do housekeeping tasks.
        """
        self.logger.debug('housekeep')
        self.do_housekeep(token)

    @abc.abstractmethod
    def do_housekeep(self, token):
        """Each plugin must implement this method but it doesn't have to do
        anything. Can be used to e.g. determine that a system should scale up
        or down.
        """
        pass

    @abc.abstractmethod
    def do_update_connectivity(self, token, instance_id):
        """ Each plugin must implement this method but it doesn't have to do
        anything.

        This can be used to e.g. open holes in firewalls or to update a proxy
        to route traffic to an instance.
        """
        pass

    @abc.abstractmethod
    def get_running_instance_logs(self, token, instance_id):
        """ get the logs of an instance which is in running state """
        pass

    @abc.abstractmethod
    def do_provision(self, token, instance_id):
        """ The steps to take to provision an instance.
        Probably doesn't make sense not to implement.
        """

        pass

    @abc.abstractmethod
    def do_deprovision(self, token, instance_id):
        """ The steps to take to deprovision an instance.
        """
        pass

    def create_prov_log_uploader(self, token, instance_id, log_type):
        """ Creates a new logger that will upload the log file via the
        internal API.
        """
        uploader = logging.getLogger('%s-%s' % (instance_id, log_type))
        uploader.setLevel(logging.INFO)
        for handler in uploader.handlers:
            uploader.removeHandler(handler)

        if 'TEST_MODE' not in self.config:
            # check if the custom handler is already there
            if len(uploader.handlers) == 0:
                log_handler = PBInstanceLogHandler(
                    self.config['INTERNAL_API_BASE_URL'],
                    instance_id,
                    token,
                    ssl_verify=self.config['SSL_VERIFY'])
                formatter = PBInstanceLogFormatter(log_type)
                log_handler.setFormatter(formatter)
                uploader.addHandler(log_handler)

        return uploader

    def create_openstack_env(self):
        m2m_creds = self.get_m2m_credentials()
        env = os.environ.copy()
        for key in ('OS_USERNAME', 'OS_PASSWORD', 'OS_TENANT_NAME', 'OS_TENANT_ID', 'OS_AUTH_URL'):
            if key in m2m_creds:
                env[key] = m2m_creds[key]
        env['PYTHONUNBUFFERED'] = '1'
        env['ANSIBLE_HOST_KEY_CHECKING'] = '0'
        return env
