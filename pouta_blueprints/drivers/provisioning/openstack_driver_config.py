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
            'flavor': {
                'type': 'string',
                'title': 'Flavor',
                'enum': [
                ]
            },
            'image': {
                'type': 'string',
                'title': 'Image',
                'enum': [
                ]
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
            'userdata': {
                'type': 'text',
                'title': 'Customization script for instance after it is launched',
                'default': '',
            },
            'firewall_rules': {
                'type': 'array',
                'title': 'Frontend firewall rules',
                'items': {
                    'type': 'string',
                    'title': 'Rules',
                }
            },
            "allow_update_client_connectivity": {
                "type": "boolean",
                "title": "Allow user to request instance firewall to allow access to user's IP address",
                "default": False,
            },
        }
    },
    'form': [
        {
            'type': 'help',
            'helpvalue': '<h4>OpenStack Instance config</h4>'
        },
        'name',
        'flavor',
        'image',
        'maximum_lifetime',
        'maximum_instances_per_user',
        {
            'key': 'userdata',
            'type': 'textarea',
            'title': 'Customization script for instance after it is launched'
        },
        'firewall_rules',
        'allow_update_client_connectivity',
    ],
    'model': {
        'name': 'os-machine',
        'flavor': 'mini',
        'image': 'Ubuntu-14.04',
        'firewall_rules': ['tcp 22 22 192.168.1.0/24']
    }
}
