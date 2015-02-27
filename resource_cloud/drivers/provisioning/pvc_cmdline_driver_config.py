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
            "Capabilities": {
                "type": "array",
                "title": "Select capabilities",
                "items": {
                    "type": "string",
                    "enum": [
                        "Common",
                        "Cluster",
                        "Hadoop",
                        "Spark",
                        "Ganglia",
                    ]
                }
            },
            "number_of_nodes": {
                "type": "integer",
                "title": "Number of worker nodes",
                "default": 2,
            },
            "maximum_lifetime": {
                "type": "integer",
                "title": "Maximum life-time (seconds)",
                "default": 3600,
            },
            "maximum_instances_per_user": {
                "type": "integer",
                "title": "Maximum instances per user",
                "default": 1,
            }
        }
    },
    "form": [
        {
            "type": "help",
            "helpvalue": "<h4>Pouta virtualcluster service config</h4>"
        },
        "name",
        "number_of_nodes",
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
        "name": "pvc",
        # "capabilities": ['Common', 'Cluster', 'Ganglia', 'Hadoop', 'Spark'],
        "capabilities": ['Common', ],
    }
}
