import glob
import os
from pouta_blueprints.tasks.celery_app import logger, get_config
from pouta_blueprints.tasks.celery_app import celery_app

RUNTIME_PATH = '/webapps/pouta_blueprints/run/proxy_conf.d'


@celery_app.task(name="pouta_blueprints.tasks.proxy_add_route")
def proxy_add_route(route_key, target, options):
    logger.info('proxy_add_route(%s, %s)' % (route_key, target))

    # generate a location snippet for nginx proxy config
    # see https://support.rstudio.com/hc/en-us/articles/200552326-Running-with-a-Proxy

    config = [
        'location /notebooks/%s/ {' % (route_key),
        'proxy_pass %s;' % (target),
        'proxy_set_header Upgrade $http_upgrade;',
        'proxy_set_header Connection "upgrade";',
        'proxy_read_timeout 86400;'
    ]

    external_https_port = get_config()['EXTERNAL_HTTPS_PORT']
    if 'proxy_rewrite' in options:
        config.append('rewrite ^/notebooks/%s/(.*)$ /$1 break;' % (route_key))
    if 'proxy_redirect' in options:
        config.append('proxy_redirect %s $scheme://$host:%d/notebooks/%s;' % (target, external_https_port, route_key))
    if 'set_host_header' in options:
        config.append('proxy_set_header Host $host;')

    config.append('}')
    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    with open(path, 'w') as f:
        f.write(
            '\n'.join(config)
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
    config = []
    nroutes = 0
    pattern = '%s/route_key-*' % RUNTIME_PATH
    for proxy_route in glob.glob(pattern):
        nroutes += 1
        with open(proxy_route, 'r') as f:
            config.extend(x.rstrip() for x in f.readlines())

    logger.debug('refresh_nginx_config(): added %d routes' % nroutes)
    path = '%s/proxy.conf' % RUNTIME_PATH
    with open(path, 'w') as f:
        f.write('\n'.join(config))
