import mock


class SecurityGroup(object):
    def __init__(self):
        self.id = "secgroup_1"


class Image(object):
    def __init__(self):
        self.id = "image_1"


class Flavor(object):
    def __init__(self):
        self.id = "flavor_1"


class Instance(object):
    def __init__(self):
        self.id = "instance_1"
        self.status = "READY"
        self.networks = {'id': ["network_1"]}

    def add_floating_ip(self, ip):
        self.floating_ip = ip


class FloatingIP(object):
    def __init__(self):
        self.id = "floating_ip_1"
        self.ip = "10.0.0.1"


class Volume(object):
    def __init__(self):
        self.id = "volume_1"
        self.status = 'available'


class Keypair(object):
    def __init__(self):
        self.id = "keypair_1"

    def delete(self):
        pass


class NovaClientMock(object):
    class SecurityGroupManagerMock(object):
        def create(self, *args, **kwargs):
            return SecurityGroup()

        def find(self, *args, **kwargs):
            return SecurityGroup()

        def delete(self, *args, **kwargs):
            pass

    class SecurityGroupRulesManagerMock(object):
        def create(self, *args, **kwargs):
            pass

    class ImageManagerMock(object):
        def find(self, *args, **kwargs):
            return Image()

    class FlavorManagerMock(object):
        def find(self, *args, **kwargs):
            return Flavor()

    class ServerManagerMock(object):
        def create(self, *args, **kwargs):
            return Instance()

        def get(self, *args, **kwargs):
            return Instance()

        def delete(self, *args, **kwargs):
            return

    class FloatingIPManager(object):
        def findall(self, *args, **kwargs):
            return []

        def create(self, *args, **kwargs):
            return FloatingIP()

    class VolumeManager(object):
        def create_server_volume(self, *args, **kwargs):
            return Volume()

        def create(self, *args, **kwargs):
            return Volume()

        def get(self, *args, **kwargs):
            return Volume()

        def delete(self, *args, **kwargs):
            return

    class KeypairManager(object):
        def create(self, *args, **kwargs):
            return Keypair()

        def find(self, *args, **kwargs):
            return Keypair()

    class Glance(object):
        def create(self, *args, **kwargs):
            return Keypair()

        def list(self, *args, **kwargs):
            return [Image()]

        def find_image(self, *args, **kwargs):
            return Image()

    def __init__(self):
        self.security_groups = NovaClientMock.SecurityGroupManagerMock()
        self.security_group_rules = NovaClientMock.SecurityGroupRulesManagerMock()
        self.images = NovaClientMock.ImageManagerMock()
        self.flavors = NovaClientMock.FlavorManagerMock()
        self.servers = NovaClientMock.ServerManagerMock()
        self.floating_ips = NovaClientMock.FloatingIPManager()
        self.volumes = NovaClientMock.VolumeManager()
        self.keypairs = NovaClientMock.KeypairManager()
        self.glance = NovaClientMock.Glance()
        self.delete_security_group = mock.MagicMock()
        self.create_security_group = mock.MagicMock()
        self.create_security_group_rule = mock.MagicMock()
        self.list_floatingips = mock.MagicMock()
        self.create_floatingip = mock.MagicMock()
        self.find_resource = mock.MagicMock()
        self.exceptions = mock.MagicMock()
