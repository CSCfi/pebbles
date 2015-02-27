CONFIG = {
    'schema': {
        'type': 'object',
        'title': 'Comment',
        'required': [
            'name',
            'number_of_nodes',
        ],
        'properties': {
            'name': {
                'type': 'string'
            },
            'software': {
                'type': 'array',
                'title': 'Select software',
                'items': {
                    'type': 'string',
                    'enum': [
                        'Common',
                        'Cluster',
                        'Hadoop',
                        'Spark',
                        'Ganglia',
                    ]
                }
            },
            'frontend_flavor': {
                'type': 'string',
                'title': 'Frontend flavor',
                'enum': [
                    'mini',
                    'small',
                    'medium',
                    'fullnode',
                ]
            },
            'frontend_image': {
                'type': 'string',
                'title': 'Frontend image',
                'enum': [
                    'Ubuntu-14.04',
                    'CentOS-6.6',
                ]
            },

            'node_flavor': {
                'type': 'string',
                'title': 'Node flavor',
                'enum': [
                    'mini',
                    'small',
                    'medium',
                    'fullnode',
                ]
            },
            'node_image': {
                'type': 'string',
                'title': 'Node image',
                'enum': [
                    'Ubuntu-14.04',
                    'CentOS-6.6',
                ]
            },

            'number_of_nodes': {
                'type': 'integer',
                'title': 'Number of worker nodes',
                'default': 2,
            },
            'maximum_lifetime': {
                'type': 'integer',
                'title': 'Maximum life-time (seconds)',
                'default': 3600,
            },
            'maximum_instances_per_user': {
                'type': 'integer',
                'title': 'Maximum instances per user',
                'default': 1,
            },
            'firewall_rules': {
                'type': 'array',
                'title': 'Frontend firewall rules',
                'items': {
                    'type': 'string',
                    'title': 'Rules',
                }
            },
        }
    },
    'form': [
        {
            'type': 'help',
            'helpvalue': '<h4>Pouta virtualcluster service config</h4>'
        },
        'name',
        'number_of_nodes',
        'frontend_flavor',
        'frontend_image',
        'node_flavor',
        'node_image',
        'software',
        'maximum_lifetime',
        'maximum_instances_per_user',
        'firewall_rules',
        {
            'type': 'submit',
            'style': 'btn-info',
            'title': 'Create'
        }
    ],
    'model': {
        'name': 'pvc',
        # 'capabilities': ['Common', 'Cluster', 'Ganglia', 'Hadoop', 'Spark'],
        'software': ['Common', ],
        'frontend_flavor': 'mini',
        'frontend_image': 'Ubuntu-14.04',
        'node_flavor': 'mini',
        'node_image': 'Ubuntu-14.04',
    }
}
