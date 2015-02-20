import shlex
import subprocess

import os

import jinja2
import stat
import yaml

from resource_cloud.drivers.provisioning import base_driver


class PvcCmdLineDriver(base_driver.ProvisioningDriverBase):
    def do_provision(self, token, provisioned_resource_id):
        pr_data = self.get_provisioned_resource_data(token, provisioned_resource_id)
        c_name = pr_data['name']

        res_dir = '%s/%s' % (self.config.PVC_CLUSTER_DATA_DIR, c_name)

        # will fail if there is already a directory for this resource
        os.makedirs(res_dir)

        # generate pvc config for this cluster
        resp = self.get_resource_description(token, pr_data['resource_id'])
        if resp.status_code != 200:
            raise RuntimeError('Cannot fetch data for resource %s, %s' % (pr_data['resource_id'], resp.reason))
        r_data = resp.json()
        tc = jinja2.Template(r_data['config'])
        conf = tc.render(cluster_name='rc-%s' % c_name, security_key='rc-%s' % c_name)
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
        key_data = self.get_user_key_data(token, pr_data['user_id']).json()
        user_key_file = '%s/userkey.pub' % res_dir
        if not key_data:
            self.do_provisioned_resource_patch(token, provisioned_resource_id, {'state': 'failed'})
            raise RuntimeError("User's public key missing")

        with open(user_key_file, 'w') as kf:
            kf.write(key_data[0]['public_key'])

        uploader = self.create_prov_log_uploader(token, provisioned_resource_id, log_type='provisioning')
        # generate keypair for this cluster
        key_file = '%s/key.priv' % res_dir
        if not os.path.isfile(key_file):
            with open(key_file, 'w') as keyfile:
                args = ['nova', 'keypair-add', 'rc-%s' % c_name]
                p = subprocess.Popen(args, cwd=res_dir, stdout=keyfile)
                p.wait()
            os.chmod(key_file, stat.S_IRUSR)

        # run provisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py up %d' % num_nodes
        self.logger.debug('spawning "%s"' % cmd)
        self.run_logged_process(cmd=cmd, cwd=res_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # add user key for ssh access
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py add_key userkey.pub'
        self.logger.debug('spawning "%s"' % cmd)
        self.run_logged_process(cmd=cmd, cwd=res_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # get public IP
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py info'
        p = subprocess.Popen(shlex.split(cmd), cwd=res_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        public_ip = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('public ip:'):
                public_ip = line.split(':')[1]
                break
        if public_ip:
            self.do_provisioned_resource_patch(token, provisioned_resource_id, {'public_ip': public_ip})

    def do_deprovision(self, token, provisioned_resource_id):
        pr_data = self.get_provisioned_resource_data(token, provisioned_resource_id)
        c_name = pr_data['name']

        res_dir = '%s/%s' % (self.config.PVC_CLUSTER_DATA_DIR, c_name)

        uploader = self.create_prov_log_uploader(token, provisioned_resource_id, log_type='deprovisioning')
        # run deprovisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py down'
        self.run_logged_process(cmd=cmd, cwd=res_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # clean generated security and server groups
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py cleanup'
        self.run_logged_process(cmd=cmd, cwd=res_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # destroy volumes
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py destroy_volumes'
        self.run_logged_process(cmd=cmd, cwd=res_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # remove generated key from OpenStack
        args = ['nova', 'keypair-delete', 'rc-%s' % c_name]
        p = subprocess.Popen(args, cwd=res_dir)
        p.wait()

        # use resource id as a part of the name to make tombstones always unique
        os.rename(res_dir, '%s.deleted.%s' % (res_dir, provisioned_resource_id))
