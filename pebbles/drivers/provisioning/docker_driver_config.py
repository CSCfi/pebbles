CONFIG = {
    'schema': {
        'type': 'object',
        'title': 'Comment',
        'description': 'Description',
        'required': [
            'name',
            'docker_image',
            'internal_port',
        ],
        'properties': {
            'name': {
                'type': 'string'
            },
            'description': {
                'type': 'string'
            },
            'docker_image': {
                'type': 'string',
                'enum': [
                ]
            },
            'internal_port': {
                'type': 'integer'
            },
            'launch_command': {
                'type': 'string',
            },
            'memory_limit': {
                'type': 'string',
                'default': '512m',
            },
            'consumed_slots': {
                'type': 'integer',
                'default': '1',
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
                'title': 'Cost multiplier (default 1.0)',
                'default': 1.0,
            },
            'needs_ssh_keys': {
                'type': 'boolean',
                'title': 'Needs ssh-keys to access',
                'default': False,
            },
            'show_password': {
                'type': 'boolean',
                'title': 'Show the required password/token (if any), to the user',
                'default': True,
            },
            'proxy_options': {
                'type': 'object',
                'title': 'Proxy Options',
                'properties': {
                    'proxy_rewrite': {
                        'type': 'boolean',
                        'title': 'Rewrite the proxy url',
                        'default': False,
                    },
                    'proxy_redirect': {
                        'type': 'boolean',
                        'title': 'Redirect the proxy url',
                        'default': False,
                    },
                    'set_host_header': {
                        'type': 'boolean',
                        'title': 'Set host header',
                        'default': False,
                    },
                    'bypass_token_authentication': {
                        'type': 'boolean',
                        'title': 'Bypass Token Authentication (Jupyter Notebooks)',
                        'default': False,
                    }
                }
            },
            'environment_vars': {
                'type': 'string',
                'title': 'environment variables for docker, separated by space',
                'default': '',
            }
        }
    },
    'form': [
        {
            'type': 'help',
            'helpvalue': '<h4>Docker instance config</h4>'
        },
        'name',
        'description',
        'docker_image',
        'internal_port',
        'launch_command',
        'environment_vars',
        'show_password',
        'memory_limit',
        'consumed_slots',
        'maximum_instances_per_user',
        'maximum_lifetime',
        'cost_multiplier',
        'proxy_options'
    ],
    'model': {
        'name': 'docker-rstudio',
        'description': 'docker blueprint',
        'docker_image': 'rocker.rstudio.img',
        'internal_port': 8787,
        'memory_limit': '512m',
        'cost_multiplier': 0.0,
        'consumed_slots': 1,
        'needs_ssh_keys': False,
        'proxy_options': {
            'proxy_rewrite': True,
            'proxy_redirect': True,
            'set_host_header': False,
            'bypass_token_authentication': False
        }
    }
}

BACKEND_CONFIG = {

    'schema': {
        'type': 'object',
        'properties': {
            'DD_SHUTDOWN_MODE': {'type': 'boolean'},
            'DD_HOST_IMAGE': {'type': 'string'},
            'DD_MAX_HOSTS': {'type': 'integer'},
            'DD_FREE_SLOT_TARGET': {'type': 'integer'},
            'DD_HOST_FLAVOR_NAME_SMALL': {'type': 'string'},
            'DD_HOST_FLAVOR_SLOTS_SMALL': {'type': 'integer'},
            'DD_HOST_FLAVOR_NAME_LARGE': {'type': 'string'},
            'DD_HOST_FLAVOR_SLOTS_LARGE': {'type': 'integer'},
            'DD_HOST_MASTER_SG': {'type': 'string'},
            'DD_HOST_EXTRA_SGS': {'type': 'string'},
            'DD_HOST_ROOT_VOLUME_SIZE': {'type': 'integer'},
            'DD_HOST_DATA_VOLUME_FACTOR': {'type': 'integer'},
            'DD_HOST_DATA_VOLUME_DEVICE': {'type': 'string'},
            'DD_HOST_DATA_VOLUME_TYPE': {'type': 'string'},
            'DD_HOST_NETWORK': {'type': 'string'}

        },
        'required': [
            'DD_SHUTDOWN_MODE',
            'DD_HOST_IMAGE',
            'DD_MAX_HOSTS',
            'DD_FREE_SLOT_TARGET',
            'DD_HOST_FLAVOR_NAME_SMALL',
            'DD_HOST_FLAVOR_SLOTS_SMALL',
            'DD_HOST_FLAVOR_NAME_LARGE',
            'DD_HOST_FLAVOR_SLOTS_LARGE',
            'DD_HOST_MASTER_SG',
            'DD_HOST_ROOT_VOLUME_SIZE',
            'DD_HOST_DATA_VOLUME_FACTOR',
            'DD_HOST_DATA_VOLUME_TYPE',
            'DD_HOST_NETWORK',

        ]
    },
    'model': {
        'DD_SHUTDOWN_MODE': True,
        'DD_HOST_IMAGE': 'CentOS-7',
        'DD_MAX_HOSTS': 4,
        'DD_FREE_SLOT_TARGET': 4,
        'DD_HOST_FLAVOR_NAME_SMALL': 'standard.medium',
        'DD_HOST_FLAVOR_SLOTS_SMALL': 6,
        'DD_HOST_FLAVOR_NAME_LARGE': 'standard.xlarge',
        'DD_HOST_FLAVOR_SLOTS_LARGE': 24,
        'DD_HOST_MASTER_SG': 'pb_server',  # openstack security group attached to instances
        'DD_HOST_EXTRA_SGS': '',
        'DD_HOST_ROOT_VOLUME_SIZE': 0,
        'DD_HOST_DATA_VOLUME_FACTOR': 4,
        'DD_HOST_DATA_VOLUME_DEVICE': '/dev/vdb',  # an optional ephemeral local volume on vm flavor
        'DD_HOST_DATA_VOLUME_TYPE': 'standard',
        'DD_HOST_NETWORK': 'auto'
    }
}
