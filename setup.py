from setuptools import setup

setup(
    entry_points={
        'pebbles.drivers.provisioning': [
            'DummyDriver = pebbles.drivers.provisioning.dummy_driver:DummyDriver',
            'OpenStackDriver = pebbles.drivers.provisioning.openstack_driver:OpenStackDriver',
            'DockerDriver = pebbles.drivers.provisioning.docker_driver:DockerDriver',
            'OpenShiftDriver = pebbles.drivers.provisioning.openshift_driver:OpenShiftDriver',
            'OpenShiftTemplateDriver = pebbles.drivers.provisioning.openshift_template_driver:OpenShiftTemplateDriver',
        ],
    },
)
