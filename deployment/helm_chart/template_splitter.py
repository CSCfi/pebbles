#!/usr/bin/env python
import sys

import yaml


def split_file(file_name):
    doc = yaml.load(open(file_name, 'r'))
    res = {}
    for obj in doc['objects']:

        if not 'metadata' in obj.keys():
            if not 'name' in obj['metadata'].keys():
                print('skipping object ' + obj)
                continue

        # transform the object

        # get rid of template vars in names
        name = obj.get('metadata').get('name')
        name = name.replace('${NAME}', 'pebbles')
        name = name.replace('${DATABASE_SERVICE_NAME}', 'db')

        # deploymentconfig to deployment
        if obj['kind'] == 'DeploymentConfig':
            obj['kind'] = 'Deployment'
            obj['spec'].pop('triggers')

        key = name + '-' + obj.get('kind')
        key = key.lower()
        res[key] = obj

    return res


def write_object(key, data):
    with open(key + '.yaml', 'w') as f:
        yaml.safe_dump(data, f, default_flow_style=False)


if __name__ == '__main__':
    objects = split_file(sys.argv[1])
    for key in objects.keys():
        print(key, objects[key])
        write_object(key, objects[key])
