CONFIG = {
    "schema": {
        "type": "object",
        "title": "Comment",
        "description": "Description",
        "required": [
            "name"
        ],
        "properties": {
            "name": {
                "type": "string"
            },
            "description": {
                "type": "string"
            },
            "secgroup-rules": {
                "type": "array",
                "title": "Security Groups",
                "items": {
                    "type": "object",
                    "title": "Rules",
                    "properties": {
                        "source": {
                            "type": "string"
                        },
                        "port": {
                            "type": "integer"
                        }
                    }
                }
            },
            "capabilities": {
                "type": "array",
                "title": "Select capabilities",
                "items": {
                    "type": "string",
                    "enum": [
                        "Capability A",
                        "Capability B",
                        "Capability C"
                    ]
                }
            },
            "maximum_lifetime": {
                "type": "integer",
                "title": "Maximum life-time (seconds)",
                "default": 3600
            },
            "maximum_instances_per_user": {
                "type": "integer",
                "title": "Maximum instances per user",
                "default": 1
            },
            "allow_update_client_connectivity": {
                "type": "boolean",
                "title": "Allow user to request instance firewall to allow access to user's IP address",
                "default": False,
            },
        }
    },
    "form": [
        {
            "type": "help",
            "helpvalue": "<h4>Dummy config</h4>"
        },
        "name",
        {
            "key": "description",
            "type": "textarea"
        },
        "capabilities",
        "maximum_lifetime",
        "maximum_instances_per_user",
        "secgroup-rules",
        "allow_update_client_connectivity",
    ],
    "model": {
        "name": "bar",
        "description": "dummy blueprint",
        "capabilities": ["Capability A"]
    }
}
