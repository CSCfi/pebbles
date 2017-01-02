from setuptools import setup, find_packages

setup(
    name='pebbles-provisioning_extensions',
    version='1.0',

    description='Provisioning extensions for Pebbles',

    author='Olli Tourunen',
    author_email='olli.tourunen@csc.fi',

    url='https://github.com/CSC-IT-Center-for-Science/pebbles',

    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Environment :: Console',
        'Operating System :: POSIX :: Linux',
    ],

    scripts=[],

    provides=[
        'pebbles.provisioning_extensions',
    ],

    packages=find_packages(),
    include_package_data=True,

    entry_points={
        'pebbles.drivers.provisioning': [
            'DummyDriver = pebbles.drivers.provisioning.dummy_driver:DummyDriver',
            'PvcCmdLineDriver = pebbles.drivers.provisioning.pvc_cmdline_driver:PvcCmdLineDriver',
            'OpenStackDriver = pebbles.drivers.provisioning.openstack_driver:OpenStackDriver',
            'DockerDriver = pebbles.drivers.provisioning.docker_driver:DockerDriver',
        ],
    },

    zip_safe=False,
)
