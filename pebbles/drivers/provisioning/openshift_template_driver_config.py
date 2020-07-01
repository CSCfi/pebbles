CONFIG = {
    'schema': {
        'type': 'object',
        'title': 'Comment',
        'description': 'Description',
        'required': [
            'name',
            'os_template',
            'openshift_cluster_id',
            'memory_limit',
        ],
        'properties': {
            'name': {
                'type': 'string'
            },
            'description': {
                'type': 'string'
            },
            'os_template': {
                'type': 'string',
                'title': 'Openshift template URL',
                'pattern': '^(?:http(s)?:\/\/)?[\w.-]+(?:\.[\w\.-]+)+[\w\-\._~:/?#[\]@!\$&\'\(\)\*\+,;=.]+$',
                'validationMessage': 'Invalid URL'
            },
            'cluster': {
                'title': 'Name of the cluster resource to use. Match this with cluster credentials',
                'type': 'string',
                'default': 'local_kubernetes',
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
            'auto_authentication': {
                'type': 'boolean',
                'title': 'Auto Authenticate',
                'default': False,
            }
        }
    },
    'form': [
        {
            'type': 'help',
            'helpvalue': '<h4>Openshift Template instance config</h4>'
        },
        'name',
        'description',
        'os_template',
        'cluster',
        'environment_vars',
        'maximum_instances_per_user',
        'maximum_lifetime',
        'cost_multiplier',
        'auto_authentication'
    ],
    'model': {
        'name': 'openshift_template_testing',
        'description': 'openshift testing template',
        'cost_multiplier': 0.0,
        'os_template': '',
    }
}
