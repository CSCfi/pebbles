import glob
from string import Template

import os

from pouta_blueprints.tasks.celery_app import logger, get_config

from pouta_blueprints.tasks.celery_app import celery_app

RUNTIME_PATH = '/webapps/pouta_blueprints/run'


@celery_app.task(name="pouta_blueprints.tasks.proxy_add_route")
def proxy_add_route(route_key, target, no_rewrite_rules=False):
    logger.info('proxy_add_route(%s, %s)' % (route_key, target))

    # generate a location snippet for nginx proxy config
    # see https://support.rstudio.com/hc/en-us/articles/200552326-Running-with-a-Proxy
    template = Template(
        """
        location /${route_key}/ {
          ${no_rw}rewrite ^/${route_key}/(.*)$$ /$$1 break;
          proxy_pass ${target};
          ${no_rw}proxy_redirect ${target} $$scheme://$$host:${external_https_port}/${route_key};
          proxy_set_header Upgrade $$http_upgrade;
          proxy_set_header Connection "upgrade";
        }
        """
    )

    if no_rewrite_rules:
        no_rw = '#'
    else:
        no_rw = ''

    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    with open(path, 'w') as f:
        f.write(
            template.substitute(
                route_key=route_key,
                target=target,
                external_https_port=get_config()['EXTERNAL_HTTPS_PORT'],
                no_rw=no_rw
            )
        )

    refresh_nginx_config()


@celery_app.task(name="pouta_blueprints.tasks.proxy_remove_route")
def proxy_remove_route(route_key):
    logger.info('proxy_remove_route(%s)' % route_key)

    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    if os.path.exists(path):
        os.remove(path)
    else:
        logger.info('proxy_remove_route(): no such file')

    refresh_nginx_config()


def refresh_nginx_config():
    config = [
        'server {',
        '   listen %s;' % get_config()['EXTERNAL_HTTPS_PORT'],
        '   ssl on;',
        '   ssl_certificate /etc/nginx/ssl/server.crt;',
        '   ssl_certificate_key /etc/nginx/ssl/server.key;',
        '   client_max_body_size 20M;',
    ]

    nroutes = 0
    pattern = '%s/route_key-*' % RUNTIME_PATH
    for proxy_route in glob.glob(pattern):
        nroutes += 1
        with open(proxy_route, 'r') as f:
            config.extend(x.rstrip() for x in f.readlines())

    config.append('}')
    config.append('')

    logger.debug('refresh_nginx_config(): added %d routes' % nroutes)

    # path = '/etc/nginx/sites-enabled/proxy'
    # path = '/tmp/proxy.conf'
    path = '%s/proxy.conf' % RUNTIME_PATH

    with open(path, 'w') as f:
        f.write('\n'.join(config))
