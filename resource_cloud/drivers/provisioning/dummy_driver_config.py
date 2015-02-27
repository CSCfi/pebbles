CONFIG = {
    "schema": {
        "type": "object",
        "title": "Comment",
        "required": [
            "name"
        ],
        "properties": {
            "name": {
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
            }
        }
    },
    "form": [
        {
            "type": "help",
            "helpvalue": "<h4>Dummy config</h4>"
        },
        "name",
        "capabilities",
        "maximum_lifetime",
        "maximum_instances_per_user",
        "secgroup-rules",
        {
            "type": "submit",
            "style": "btn-info",
            "title": "Create"
        }
    ],
    "model": {
        "name": "bar",
        "capabilities": ["Capability A"]
    }
}
