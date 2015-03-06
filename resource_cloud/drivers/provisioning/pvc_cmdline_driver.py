import shlex
import subprocess

import os

import jinja2
import stat

from resource_cloud.drivers.provisioning import base_driver


class PvcCmdLineDriver(base_driver.ProvisioningDriverBase):
    def run_nova_list(self, object_type):
        cmd = 'nova %s-list' % object_type
        try:
            p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as e:
            self.logger.warn('Could not run %s list ("nova" missing from path?): """%s""" ' % (object_type, e))
            return {}

        out, err = p.communicate()
        if p.returncode:
            self.logger.warn('Could not run %s list: """%s""" ' % (object_type, err))
            return {}

        res = []
        lines = [x for x in out.splitlines() if not x.startswith('+')]
        field_names = [x.strip() for x in lines[0].split('|')[1:-1]]
        for line in lines[1:]:
            object_data = {}
            fields = [x.strip() for x in line.split('|')[1:-1]]
            for i in range(0, len(field_names)):
                object_data[field_names[i]] = fields[i]
            res.append(object_data)

        return res

    def get_configuration(self):
        from resource_cloud.drivers.provisioning.pvc_cmdline_driver_config import CONFIG

        images = self.run_nova_list('image')
        self.logger.debug('images: %s' % images)

        flavors = self.run_nova_list('flavor')
        self.logger.debug('flavors: %s' % flavors)

        config = CONFIG.copy()
        image_names = [x['Name'] for x in images]
        config['schema']['properties']['frontend_image']['enum'] = image_names
        config['schema']['properties']['node_image']['enum'] = image_names

        flavor_names = [x['Name'] for x in flavors]
        config['schema']['properties']['frontend_flavor']['enum'] = flavor_names
        config['schema']['properties']['node_flavor']['enum'] = flavor_names

        return config

    def do_provision(self, token, instance_id):
        instance = self.get_instance_data(token, instance_id)
        cluster_name = instance['name']

        instance_dir = '%s/%s' % (self.config.PVC_CLUSTER_DATA_DIR, cluster_name)

        # will fail if there is already a directory for this instance
        os.makedirs(instance_dir)

        # generate pvc config for this cluster
        blueprint_config = self.get_blueprint_description(token, instance['blueprint_id'])['config']

        self.logger.debug('Blueprint config: %s' % blueprint_config)

        cluster_config = self.create_cluster_config(blueprint_config, cluster_name)
        with open('%s/cluster.yml' % instance_dir, 'w') as cf:
            cf.write(cluster_config)
            cf.write('\n')

        # figure out the number of nodes from config provisioning-data
        if 'number_of_nodes' in blueprint_config:
            num_nodes = int(blueprint_config['number_of_nodes'])
        else:
            self.logger.warn('number of nodes in cluster not defined, using default: 2')
            num_nodes = 2

        # fetch user public key and save it
        key_data = self.get_user_key_data(token, instance['user_id']).json()
        user_key_file = '%s/userkey.pub' % instance_dir
        if not key_data:
            self.do_instance_patch(token, instance_id, {'state': 'failed'})
            raise RuntimeError("User's public key missing")

        with open(user_key_file, 'w') as kf:
            kf.write(key_data[0]['public_key'])

        uploader = self.create_prov_log_uploader(token, instance_id, log_type='provisioning')
        # generate keypair for this cluster
        key_file = '%s/key.priv' % instance_dir
        if not os.path.isfile(key_file):
            with open(key_file, 'w') as keyfile:
                args = ['nova', 'keypair-add', 'rc-%s' % cluster_name]
                p = subprocess.Popen(args, cwd=instance_dir, stdout=keyfile)
                p.wait()
            os.chmod(key_file, stat.S_IRUSR)

        # run provisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py up %d' % num_nodes
        self.logger.debug('spawning "%s"' % cmd)
        self.run_logged_process(cmd=cmd, cwd=instance_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # add user key for ssh access
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py add_key userkey.pub'
        self.logger.debug('spawning "%s"' % cmd)
        self.run_logged_process(cmd=cmd, cwd=instance_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # get public IP
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py info'
        p = subprocess.Popen(shlex.split(cmd), cwd=instance_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        public_ip = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('public ip:'):
                public_ip = line.split(':')[1]
                break
        if public_ip:
            self.do_instance_patch(token, instance_id, {'public_ip': public_ip})

    def do_deprovision(self, token, instance_id):
        instance = self.get_instance_data(token, instance_id)
        cluster_name = instance['name']

        instance_dir = '%s/%s' % (self.config.PVC_CLUSTER_DATA_DIR, cluster_name)

        uploader = self.create_prov_log_uploader(token, instance_id, log_type='deprovisioning')
        # run deprovisioning
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py down'
        self.run_logged_process(cmd=cmd, cwd=instance_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # clean generated security and server groups
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py cleanup'
        self.run_logged_process(cmd=cmd, cwd=instance_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # destroy volumes
        cmd = '/webapps/resource_cloud/venv/bin/python /opt/pvc/python/poutacluster.py destroy_volumes'
        self.run_logged_process(cmd=cmd, cwd=instance_dir, env=self.create_pvc_env(), log_uploader=uploader)

        # remove generated key from OpenStack
        args = ['nova', 'keypair-delete', 'rc-%s' % cluster_name]
        p = subprocess.Popen(args, cwd=instance_dir)
        p.wait()

        # use instance id as a part of the name to make tombstones always unique
        os.rename(instance_dir, '%s.deleted.%s' % (instance_dir, instance_id))

    @staticmethod
    def create_cluster_config(user_config, cluster_name):

        software_to_groups = {
            'Common': {
                'frontend': ['common'],
                'node': ['common']
            },
            'Cluster': {
                'frontend': ['cluster_master'],
                'node': ['cluster_slave']
            },
            'GridEngine': {
                'frontend': ['ge_master'],
                'node': ['ge_slave']
            },
            'Ganglia': {
                'frontend': ['ganglia_master'],
                'node': ['ganglia_monitor']
            },
            'Spark': {
                'frontend': ['spark_master'],
                'node': ['spark_slave']
            },
            'Hadoop': {
                'frontend': ['hadoop_jobtracker', 'hadoop_namenode'],
                'node': ['hadoop_tasktracker', 'hadoop_datanode']
            },
        }

        frontend_groups = []
        node_groups = []
        for soft in user_config['software']:
            frontend_groups.extend(software_to_groups[soft]['frontend'])
            node_groups.extend(software_to_groups[soft]['node'])

        frontend_volumes = []
        if 'frontend_volumes' in user_config:
            frontend_volumes = [x for x in user_config['frontend_volumes'] if x['size']]
            user_config.pop('frontend_volumes')
        node_volumes = []
        if 'node_volumes' in user_config:
            node_volumes = [x for x in user_config['node_volumes'] if x['size']]
            user_config.pop('node_volumes')

        # generate pvc config for this cluster
        this_dir = os.path.dirname(os.path.abspath(__file__))

        j2env = jinja2.Environment(loader=jinja2.FileSystemLoader(this_dir), trim_blocks=True)
        tc = j2env.get_template('pvc-cluster.yml.jinja2')
        cluster_config = tc.render(
            cluster_name='rc-%s' % cluster_name,
            security_key='rc-%s' % cluster_name,
            frontend_groups=frontend_groups,
            node_groups=node_groups,
            frontend_volumes=frontend_volumes,
            node_volumes=node_volumes,
            **user_config
        )
        return cluster_config

# testing templating
if __name__ == '__main__':
    blueprint_config = {
        "name": "pvc",
        "software": ['Common', 'Cluster', 'Ganglia', 'Hadoop', 'Spark'],
        'firewall_rules': ["tcp 22 22 193.166.85.0/24"],
        'frontend_flavor': 'mini',
        'frontend_image': 'Ubuntu-14.04',
        'frontend_volumes': [
            {'name': 'local_data', 'device': 'vdc', 'size': 5},
            {'name': 'shared_data', 'device': 'vdd', 'size': 0},
        ],
        'node_flavor': 'mini',
        'node_image': 'Ubuntu-14.04',
        'node_volumes': [
            {'name': 'local_data', 'size': 5},
        ],
    }
    cluster_config = PvcCmdLineDriver.create_cluster_config(blueprint_config, 'test_name')
    print cluster_config
