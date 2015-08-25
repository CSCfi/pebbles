CONFIG = {
    'schema': {
        'type': 'object',
        'title': 'Comment',
        'required': [
            'name',
        ],
        'properties': {
            'name': {
                'type': 'string'
            },
            'docker_image': {
                'type': 'string'
            },
            'internal_port': {
                'type': 'integer'
            },
            'memory_limit': {
                'type': 'string',
                'default': '256m',
            },
            'maximum_instances_per_user': {
                'type': 'integer',
                'title': 'Maximum instances per user',
                'default': 1,
            },
            'maximum_lifetime': {
                'type': 'integer',
                'title': 'Maximum life-time (seconds)',
                'default': 3600,
            },
            'allow_update_client_connectivity': {
                'type': 'boolean',
                'title': "Allow user to request instance firewall to allow access to user's IP address",
                'default': False,
            },
            'cost_multiplier': {
                'type': 'number',
                'title': 'Cost multiplier (default 1.0)',
                'default': 1.0,
            },
        }
    },
    'form': [
        {
            'type': 'help',
            'helpvalue': '<h4>Docker instance config</h4>'
        },
        'name',
        'docker_image',
        'internal_port',
        'memory_limit',
        'maximum_instances_per_user',
        'maximum_lifetime',
        'cost_multiplier',
        'allow_update_client_connectivity',
    ],
    'model': {
        'name': 'docker-machine',
        'docker_image': 'jupyter/minimal',
        'internal_port': 8888,
        'memory_limit': '256m',
    }
}
