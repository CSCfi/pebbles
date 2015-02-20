from setuptools import setup, find_packages

setup(
    name='resource_cloud-provisioning_extensions',
    version='1.0',

    description='Provisioning extensions for Resource Cloud',

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
        'resource_cloud.provisioning_extensions',
    ],

    packages=find_packages(),
    include_package_data=True,

    entry_points={
        'resource_cloud.drivers.provisioning': [
            'DummyDriver = resource_cloud.drivers.provisioning.dummy_driver:DummyDriver',
            'PvcCmdLineDriver = resource_cloud.drivers.provisioning.pvc_cmdline_driver:PvcCmdLineDriver',
        ],
    },

    zip_safe=False,
)
