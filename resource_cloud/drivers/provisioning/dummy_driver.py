from random import randint

import os
import jinja2
import yaml

from resource_cloud.drivers.provisioning import base_driver


class DummyDriver(base_driver.ProvisioningDriverBase):
    def do_provision(self, token, provisioned_resource_id):
        provisioned_resource = self.get_provisioned_resource_data(token, provisioned_resource_id)
        cluster_name = provisioned_resource['name']

        res_dir = '%s/%s' % (self.config.PVC_CLUSTER_DATA_DIR, cluster_name)

        # will fail if there is already a directory for this resource
        os.makedirs(res_dir)

        # generate pvc config for this cluster
        resp = self.get_resource_description(token, provisioned_resource['resource_id'])
        if resp.status_code != 200:
            raise RuntimeError(
                'Cannot fetch data for resource %s, %s' % (provisioned_resource['resource_id'], resp.reason))
        r_data = resp.json()
        tc = jinja2.Template(r_data['config'])
        conf = tc.render(cluster_name='rc-%s' % cluster_name, security_key='rc-%s' % cluster_name)
        with open('%s/cluster.yml' % res_dir, 'w') as cf:
            cf.write(conf)
            cf.write('\n')

        # figure out the number of nodes from config provisioning-data
        cluster_config = yaml.load(conf)
        if 'provisioning_data' in cluster_config.keys() and 'num_nodes' in cluster_config['provisioning_data'].keys():
            num_nodes = int(cluster_config['provisioning_data']['num_nodes'])
        else:
            self.logger.warn('number of nodes in cluster not defined, using default: 2')
            num_nodes = 2

        # fetch user public key and save it
        key_data = self.get_user_key_data(token, provisioned_resource['user_id']).json()
        user_key_file = '%s/userkey.pub' % res_dir
        if not key_data:
            self.do_provisioned_resource_patch(token, provisioned_resource_id, {'state': 'failed'})
            raise RuntimeError("User's public key missing")

        with open(user_key_file, 'w') as kf:
            kf.write(key_data[0]['public_key'])

        uploader = self.create_prov_log_uploader(token, provisioned_resource_id, log_type='provisioning')

        self.logger.info('faking provisioning')
        cmd = 'time ping -c 10 localhost'
        self.run_logged_process(cmd=cmd, cwd=res_dir, shell=True, log_uploader=uploader)
        self.do_provisioned_resource_patch(token, provisioned_resource_id, {'public_ip': '%s.%s.%s.%s' % (
            randint(1, 254), randint(1, 254), randint(1, 254), randint(1, 254))})

    def do_deprovision(self, token, provisioned_resource_id):
        provisioned_resource = self.get_provisioned_resource_data(token, provisioned_resource_id)
        cluster_name = provisioned_resource['name']

        res_dir = '%s/%s' % (self.config.PVC_CLUSTER_DATA_DIR, cluster_name)

        uploader = self.create_prov_log_uploader(token, provisioned_resource_id, log_type='deprovisioning')

        self.logger.info('faking deprovisioning')
        cmd = 'time ping -c 5 localhost'
        self.run_logged_process(cmd=cmd, cwd=res_dir, shell=True, log_uploader=uploader)

        # use resource id as a part of the name to make tombstones always unique
        os.rename(res_dir, '%s.deleted.%s' % (res_dir, provisioned_resource_id))
