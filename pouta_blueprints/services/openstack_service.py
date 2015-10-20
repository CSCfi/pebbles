import novaclient
from novaclient.exceptions import NotFound
from novaclient.v2 import client

import taskflow.engines
from taskflow.patterns import linear_flow as lf
from taskflow.patterns import graph_flow as gf
from taskflow import task

import logging
import os
import json
import time


def get_openstack_nova_client(config):
    if config:
        if config.get('M2M_CREDENTIAL_STORE'):
            logging.debug("loading credentials from %s" % config.get('M2M_CREDENTIAL_STORE'))
            m2m_config = json.load(open(config.get('M2M_CREDENTIAL_STORE')))
            source_config = m2m_config
        else:
            logging.debug("using config as provided")
            source_config = config
    else:
        logging.debug("no config, trying environment vars")
        source_config = os.environ
    os_username = source_config['OS_USERNAME']
    os_password = source_config['OS_PASSWORD']
    os_tenant_name = source_config['OS_TENANT_NAME']
    os_auth_url = source_config['OS_AUTH_URL']
    return client.Client(os_username, os_password, os_tenant_name, os_auth_url, service_type="compute")


class GetServer(task.Task):
    def execute(self, server_id, config):
        logging.debug("gettin server %s" % server_id)
        nc = get_openstack_nova_client(config)
        return nc.servers.get(server_id)

    def revert(self, *args, **kwargs):
        pass


class GetImage(task.Task):
    def execute(self, image_name, config):
        logging.debug("getting image %s" % image_name)
        nc = get_openstack_nova_client(config)
        return nc.images.find(name=image_name)

    def revert(self, *args, **kwargs):
        pass


class ListImages(task.Task):
    def execute(self, image_name, config):
        logging.debug("getting images")
        nc = get_openstack_nova_client(config)
        return nc.images.list()

    def revert(self, *args, **kwargs):
        pass


class GetFlavor(task.Task):
    def execute(self, flavor_name, config):
        logging.debug("getting flavor %s" % flavor_name)
        nc = get_openstack_nova_client(config)
        return nc.flavors.find(name=flavor_name)

    def revert(self, *args, **kwargs):
        pass


class ListFlavors(task.Task):
    def execute(self, flavor_name, config):
        logging.debug("getting flavors")
        nc = get_openstack_nova_client(config)
        return nc.flavors.list()

    def revert(self, *args, **kwargs):
        pass


class CreateSecurityGroup(task.Task):
    def execute(self, display_name, master_sg_name, config):
        logging.debug("create security group %s" % display_name)
        security_group_name = display_name
        nc = get_openstack_nova_client(config)

        self.secgroup = nc.security_groups.create(
            security_group_name,
            "Security group generated by Pouta Blueprints")

        if master_sg_name:
            master_sg = nc.security_groups.find(name=master_sg_name)
            nc.security_group_rules.create(
                self.secgroup.id,
                ip_protocol='tcp',
                from_port=1,
                to_port=65535,
                group_id=master_sg.id
            )
            nc.security_group_rules.create(
                self.secgroup.id,
                ip_protocol='udp',
                from_port=1,
                to_port=65535,
                group_id=master_sg.id
            )
            nc.security_group_rules.create(
                self.secgroup.id,
                ip_protocol='icmp',
                from_port=-1,
                to_port=-1,
                group_id=master_sg.id
            )

        logging.info("Created security group %s" % self.secgroup.id)

        return self.secgroup.id

    def revert(self, config, **kwargs):
        logging.debug("revert: delete security group")
        nc = get_openstack_nova_client(config)
        nc.security_groups.delete(self.secgroup.id)


class CreateRootVolume(task.Task):
    def execute(self, display_name, image, root_volume_size, config):
        if root_volume_size:
            logging.debug("creating a root volume for instance %s from image %s" % (display_name, image))
            nc = get_openstack_nova_client(config)
            volume_name = '%s-root' % display_name

            volume = nc.volumes.create(
                size=root_volume_size,
                imageRef=image.id,
                display_name=volume_name
            )
            self.volume_id = volume.id
            retries = 0
            while nc.volumes.get(volume.id).status not in ('available', ):
                logging.debug("...waiting for volume to be ready")
                time.sleep(5)
                retries += 1
                if retries > 30:
                    raise RuntimeError('Volume creation %s is stuck')

            return volume.id
        else:
            logging.debug("no root volume defined")
            return ""

    def revert(self, config, **kwargs):
        logging.debug("revert: delete root volume")

        try:
            if getattr(self, 'volume_id', None):
                nc = get_openstack_nova_client(config)
                nc.volumes.delete(self.volume_id)
            else:
                logging.debug("revert: no volume_id stored, unable to revert")
        except Exception as e:
            logging.error('revert: deleting volume failed: %s' % e)


class CreateDataVolume(task.Task):
    def execute(self, display_name, data_volume_size, config):
        if data_volume_size:
            logging.debug("creating a data volume for instance %s, %d" % (display_name, data_volume_size))
            nc = get_openstack_nova_client(config)
            volume_name = '%s-data' % display_name

            volume = nc.volumes.create(
                size=data_volume_size,
                display_name=volume_name
            )
            self.volume_id = volume.id
            retries = 0
            while nc.volumes.get(volume.id).status not in ('available', ):
                logging.debug("...waiting for volume to be ready")
                time.sleep(5)
                retries += 1
                if retries > 30:
                    raise RuntimeError('Volume creation %s is stuck')

            return volume.id
        else:
            logging.debug("no root volume defined")
            return ""

    def revert(self, config, **kwargs):
        logging.debug("revert: delete root volume")

        try:
            if getattr(self, 'volume_id', None):
                nc = get_openstack_nova_client(config)
                nc.volumes.delete(self.volume_id)
            else:
                logging.debug("revert: no volume_id stored, unable to revert")
        except Exception as e:
            logging.error('revert: deleting volume failed: %s' % e)


class ProvisionInstance(task.Task):
    def execute(self, display_name, image, flavor, security_group, extra_sec_groups,
                root_volume_id, userdata, config):
        logging.debug("provisioning instance %s" % display_name)
        nc = get_openstack_nova_client(config)
        sgs = [security_group]
        if extra_sec_groups:
            sgs.extend(extra_sec_groups)
        try:
            if len(root_volume_id):
                bdm = {'vda': '%s:::1' % (root_volume_id)}
            else:
                bdm = None
            logging.warn("using key %s " % display_name)
            nc.keypairs.find(name=display_name)
            instance = nc.servers.create(
                display_name,
                image.id,
                flavor.id,
                key_name=display_name,
                security_groups=sgs,
                block_device_mapping=bdm,
                userdata=userdata)

        except Exception as e:
            logging.error("error provisioning instance: %s" % e)
            raise e

        self.instance_id = instance.id
        logging.debug("instance provisioning successful")
        return instance.id

    def revert(self, config, **kwargs):
        logging.debug("revert: deleting instance %s", kwargs)
        try:
            if getattr(self, 'instance_id', None):
                nc = get_openstack_nova_client(config)
                nc.servers.delete(self.instance_id)
            else:
                logging.debug("revert: no instance_id stored, unable to revert")
        except Exception as e:
            logging.error('revert: deleting instance failed: %s' % e)


class DeprovisionInstance(task.Task):
    def execute(self, server_id, config):
        nc = get_openstack_nova_client(config)
        logging.warn("DeprovisionInstance")
        try:
            server = nc.servers.get(server_id)
            server.delete()
            return server.name

        except NotFound:
            logging.warn("Server %s not found" % server_id)
        except Exception as e:
            logging.warn("Unable to deprovision server %s" % e)

    def revert(self, *args, **kwargs):
        logging.warn("revert DeprovisionInstance")


class AllocateIPForInstance(task.Task):
    def execute(self, server_id, allocate_public_ip, config):
        logging.debug("Allocate IP for server %s" % server_id)

        nc = get_openstack_nova_client(config)
        retries = 0
        while nc.servers.get(server_id).status is "BUILDING" or not nc.servers.get(server_id).networks:
            logging.debug("...waiting for server to be ready")
            time.sleep(5)
            retries += 1
            if retries > 30:
                raise RuntimeError('Server %s is stuck in building' % server_id)

        server = nc.servers.get(server_id)
        if allocate_public_ip:

            ips = nc.floating_ips.findall(instance_id=None)
            allocated_from_pool = False
            if not ips:
                logging.debug("No allocated free IPs left, trying to allocate one")
                try:
                    ip = nc.floating_ips.create(pool="public")
                    allocated_from_pool = True
                except novaclient.exceptions.ClientException as e:
                    logging.warning("Cannot allocate IP, quota exceeded?")
                    raise e
            else:
                ip = ips[0]
            try:
                server.add_floating_ip(ip)
            except Exception as e:
                logging.error(e)

            address_data = {
                'public_ip': ip.ip,
                'allocated_from_pool': allocated_from_pool,
                'private_ip': list(server.networks.values())[0][0],
            }
        else:
            address_data = {
                'public_ip': None,
                'allocated_from_pool': False,
                'private_ip': list(server.networks.values())[0][0],
            }

        return address_data

    def revert(self, *args, **kwargs):
        pass


class ListInstanceVolumes(task.Task):
    def execute(self, server_id, config):
        nc = get_openstack_nova_client(config)
        return nc.volumes.get_server_volumes(server_id)

    def revert(self):
        pass


class AttachDataVolume(task.Task):
    def execute(self, server_id, data_volume_id, config):
        logging.debug("Attach data volume for server %s" % server_id)

        if data_volume_id:
            nc = get_openstack_nova_client(config)
            retries = 0

            while nc.servers.get(server_id).status is "BUILDING" or not nc.servers.get(server_id).networks:
                logging.debug("...waiting for server to be ready")
                time.sleep(5)
                retries += 1
                if retries > 30:
                    raise RuntimeError('Server %s is stuck in building' % server_id)

            nc.volumes.create_server_volume(server_id, data_volume_id, '/dev/vdc')

    def revert(self, *args, **kwargs):
        pass


class AddUserPublicKey(task.Task):
    def execute(self, display_name, public_key, config):
        nc = get_openstack_nova_client(config)
        key_data = public_key[0]['public_key']
        nc.keypairs.create(display_name, key_data)

    def revert(self, display_name, public_key, config, **kwargs):
        nc = get_openstack_nova_client(config)
        nc.keypairs.find(display_name).delete()


class RemoveUserPublicKey(task.Task):
    def execute(self, display_name, config):
        nc = get_openstack_nova_client(config)
        try:
            nc.keypairs.find(name=display_name).delete()
        except:
            pass

    def revert(self, *args, **kwargs):
        pass


class DeleteSecurityGroup(task.Task):
    def execute(self, server, config):
        nc = get_openstack_nova_client(config)
        logging.info('DeleteSecurityGroup')
        security_groups = nc.security_groups.findall(name="oss_test_harri")
        for security_group in security_groups:
            try:
                security_group.delete()
            except NotFound:
                logging.info('Security group already deleted')
            except Exception as e:
                logging.warn("Could not delete security group: %s" % e)

    def revert(self, *args, **kwargs):
        pass


class DeleteVolumes(task.Task):
    def execute(self, server, config):
        nc = get_openstack_nova_client(config)
        for volume in nc.volumes.get_server_volumes(server.id):
            retries = 0
            while nc.volumes.get(volume.id).status not in ('available', 'error'):
                logging.debug("...waiting for volume to be ready")
                time.sleep(5)
                retries += 1
                if retries > 30:
                    raise RuntimeError('Volume %s is stuck' % volume.id)

            try:
                volume.delete()
            except NotFound:
                pass

    def revert(self, *args, **kwargs):
        pass


def getProvisionFlow():
    """
    Provisioning flow consisting of three graph flows, each consisting of set of
    tasks that can execute in parallel.

    Returns tuple consisting of the whole flow and a dictionary including
    references to three graph flows for pre-execution customisations.
    """
    preFlow = gf.Flow('PreBootInstance').add(
        AddUserPublicKey('add_user_public_key'),
        GetImage('get_image', provides='image'),
        GetFlavor('get_flavor', provides='flavor'),
        CreateRootVolume('create_root_volume', provides='root_volume_id')
    )
    mainFlow = gf.Flow('BootInstance').add(
        CreateSecurityGroup('create_security_group', provides='security_group'),
        CreateDataVolume('create_data_volume', provides='data_volume_id'),
        ProvisionInstance('provision_instance', provides='server_id')
    )
    postFlow = gf.Flow('PostBootInstance').add(
        AllocateIPForInstance('allocate_ip_for_instance', provides='address_data'),
        AttachDataVolume('attach_data_volume'),
        RemoveUserPublicKey('remove_user_public_key')
    )
    return (lf.Flow('ProvisionInstance').add(preFlow, mainFlow, postFlow),
            {'pre': preFlow, 'main': mainFlow, 'post': postFlow})


def getDeprovisionFlow():
    preFlow = gf.Flow('PreDestroyInstance').add(
        GetServer('get_server', provides="server")
    )
    mainFlow = gf.Flow('DestroyInstance').add(
        DeprovisionInstance('deprovision_instance')
    )
    postFlow = gf.Flow('PostDestroyInstance').add(
        DeleteSecurityGroup('delete_security_group')
    )

    return (lf.Flow('DeprovisionInstance').add(preFlow, mainFlow, postFlow),
            {'pre': preFlow, 'main': mainFlow, 'post': postFlow})


def getListImagesFlow():
    return lf.Flow('ListImages').add(
        ListImages('list_images', provides="images")
    )


def getListFlavorsFlow():
    return lf.Flow('ListFlavors').add(
        ListFlavors('list_flavors', provides="flavors")
    )


def uploadKeyFlow():
    return lf.Flow('UploadKey').add(
        AddUserPublicKey('upload_key')
    )


class OpenStackService(object):
    def __init__(self, config=None):
        self._config = config

    def provision_instance(self, display_name, image_name, flavor_name, public_key, extra_sec_groups=None,
                           master_sg_name=None, allocate_public_ip=True, root_volume_size=0,
                           data_volume_size=0, userdata=None):
        try:
            flow, _ = getProvisionFlow()
            return taskflow.engines.run(flow, engine='parallel', store=dict(
                image_name=image_name,
                flavor_name=flavor_name,
                display_name=display_name,
                master_sg_name=master_sg_name,
                public_key=public_key,
                extra_sec_groups=extra_sec_groups,
                allocate_public_ip=allocate_public_ip,
                root_volume_size=root_volume_size,
                data_volume_size=data_volume_size,
                userdata=userdata,
                config=self._config))
        except Exception as e:
            logging.error(e)
            return {'error': 'flow failed'}

    def deprovision_instance(self, server_id, delete_attached_volumes=False):
        flow, subflows = getDeprovisionFlow()
        if delete_attached_volumes:
            subflows['main'].add(DeleteVolumes())

        try:
            return taskflow.engines.run(flow, engine='parallel', store=dict(
                server_id=server_id,
                config=self._config))
        except Exception as e:
            logging.error(e)
            return {'error': 'flow failed'}

    def get_instance_state(self, instance_id):
        nc = get_openstack_nova_client(self._config)
        return nc.servers.get(instance_id).status

    def get_instance_networks(self, instance_id):
        nc = get_openstack_nova_client(self._config)
        return nc.servers.get(instance_id).networks

    def list_images(self):
        nc = get_openstack_nova_client(self._config)
        return nc.images.list()

    def list_flavors(self):
        nc = get_openstack_nova_client(self._config)
        return nc.flavors.list()

    def upload_key(self, key_name, key_file):
        try:
            return taskflow.engines.rnu(uploadKeyFlow, engine='parallel', store=dict(
                config=self._config))
        except Exception as e:
            logging.error(e)
            return {'error': 'flow failed'}

    def delete_key(self, key_name):
        logging.debug('Deleting key: %s' % key_name)
        nc = get_openstack_nova_client(self._config)
        try:
            key = nc.keypairs.find(name=key_name)
            key.delete()
        except:
            logging.warning('Key not found: %s' % key_name)

    def clear_security_group_rules(self, group_id):
        nc = get_openstack_nova_client(self._config)
        sg = nc.security_groups.get(group_id)
        for rule in sg.rules:
            nc.security_group_rules.delete(rule["id"])

    def create_security_group(self, security_group_name, security_group_description):
        nc = get_openstack_nova_client(self._config)
        nc.security_groups.create(
            security_group_name,
            "Security group generated by Pouta Blueprints")

    def create_security_group_rule(self, security_group_id, from_port, to_port, cidr, ip_protocol='tcp'):
        nc = get_openstack_nova_client(self._config)
        nc.security_group_rules.create(
            security_group_id,
            ip_protocol=ip_protocol,
            from_port=from_port,
            to_port=to_port,
            cidr=cidr,
            group_id=None
        )
