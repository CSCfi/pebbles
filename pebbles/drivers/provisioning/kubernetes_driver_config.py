CONFIG = {
    'schema': {
        'type': 'object',
        'title': 'Comment',
        'description': 'Description',
        'required': [
            'name',
            'cluster',
            'image',
            'port',
            'memory_limit',
        ],
        'properties': {
            'name': {
                'type': 'string'
            },
            'description': {
                'type': 'string'
            },
            'labels': {
                'title': 'Labels, separated with a comma (",")',
                'type': 'string'
            },
            'image': {
                'type': 'string',
            },
            'cluster': {
                'title': 'Name of the cluster resource to use. Match this with cluster credentials',
                'type': 'string',
                'default': 'local_kubernetes',
            },
            'args': {
                'type': 'string',
                'default': "jupyter notebook --NotebookApp.token='' --NotebookApp.base_url='/notebooks/{instance_id}'"
            },
            'port': {
                'type': 'integer',
            },
            'volume_mount_path': {
                'type': 'string',
            },
            'memory_limit': {
                'type': 'string',
                'default': '512M',
            },
            'maximum_instances_per_user': {
                'type': 'integer',
                'title': 'Maximum instances per user',
                'default': 1,
            },
            'maximum_lifetime': {
                'type': 'string',
                'title': 'Maximum life-time (days hours mins)',
                'default': '1h 0m',
                'pattern': '^(\d+d\s?)?(\d{1,2}h\s?)?(\d{1,2}m\s?)?$',
                'validationMessage': 'Value should be in format [days]d [hours]h [minutes]m'
            },
            'cost_multiplier': {
                'type': 'number',
                'title': 'Cost multiplier',
                'default': 0.0,
            },
            'environment_vars': {
                'type': 'string',
                'title': 'environment variables for docker, separated by space',
                'default': '',
            },
            'autodownload_url': {
                'type': 'string',
                'title': 'Autodownload URL',
                'default': '',
            },
            'autodownload_filename': {
                'type': 'string',
                'title': 'Autodownload file name',
                'default': '',
            },
            'show_password': {
                'type': 'boolean',
                'title': 'Show the required password/token (if any), to the user',
                'default': True,
            },
        }
    },
    'form': [
        {
            'type': 'help',
            'helpvalue': '<h4>Kubernetes local driver config</h4>'
        },
        'name',
        'description',
        'labels',
        'cluster',
        'image',
        'args',
        'port',
        'volume_mount_path',
        'environment_vars',
        'autodownload_url',
        'autodownload_filename',
        'show_password',
        'memory_limit',
        'maximum_instances_per_user',
        'maximum_lifetime',
        'cost_multiplier'
    ],
    'model': {
        'name': 'k8s_testing',
        'description': 'k8s testing template',
        'labels': 'Data Analytics, Python, Jupyter',
        'cost_multiplier': 0.0,
        'port': 8888,
        'volume_mount_path': '/data',
        'image': 'jupyter/minimal-notebook',
        'memory_limit': '512M',
    }
}
