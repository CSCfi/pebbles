from setuptools import setup, find_packages

setup(
    name='pouta_blueprints-provisioning_extensions',
    version='1.0',

    description='Provisioning extensions for Pouta Blueprints',

    author='Olli Tourunen',
    author_email='olli.tourunen@csc.fi',

    url='https://github.com/CSC-IT-Center-for-Science/resource-cloud',

    classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Environment :: Console',
        'Operating System :: POSIX :: Linux',
    ],

    scripts=[],

    provides=[
        'pouta_blueprints.provisioning_extensions',
    ],

    packages=find_packages(),
    include_package_data=True,

    entry_points={
        'pouta_blueprints.drivers.provisioning': [
            'DummyDriver = pouta_blueprints.drivers.provisioning.dummy_driver:DummyDriver',
            'PvcCmdLineDriver = pouta_blueprints.drivers.provisioning.pvc_cmdline_driver:PvcCmdLineDriver',
            'OpenStackDriver = pouta_blueprints.drivers.provisioning.openstack_driver:OpenStackDriver',
        ],
    },

    zip_safe=False,
)
