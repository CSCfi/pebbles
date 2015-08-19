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
            'helpvalue': '<h4>OpenStack Instance config</h4>'
        },
        'name',
        'docker_image',
        'maximum_instances_per_user',
        'maximum_lifetime',
        'cost_multiplier',
        'allow_update_client_connectivity',
    ],
    'model': {
        'name': 'docker-machine',
        'docker_image': 'jupyter/minimal',
    }
}
