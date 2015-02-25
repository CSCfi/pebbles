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
            "apps": {
                "type": "array",
                "title": "Installed apps",
                "items": {
                    "type": "string",
                    "enum": [
                        "vim",
                        "emacs",
                        "cowsay"
                    ]
                }
            }
        }
    },
    "form": [
        {
            "type": "help",
            "helpvalue": "<h4>Dummy config</h4>"
        },
        "*",
        {
            "type": "submit",
            "style": "btn-info",
            "title": "OK"
        }
    ],
    "model": {
        "name": "bar",
        "apps": ["vim", "cowsay"]
    }
}
