import glob
import os
from pebbles.tasks.celery_app import logger, get_dynamic_config
from pebbles.tasks.celery_app import celery_app

RUNTIME_PATH = '/webapps/pebbles/run/proxy_conf.d'


@celery_app.task(name="pebbles.tasks.proxy_add_route")
def proxy_add_route(route_key, target, options):
    """ adds a route to nginx configs for access to e.g. a container
    """
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

    dynamic_config = get_dynamic_config()
    external_https_port = dynamic_config['EXTERNAL_HTTPS_PORT']
    if 'proxy_rewrite' in options:
        config.append('rewrite ^/notebooks/%s/(.*)$ /$1 break;' % (route_key))
    if 'proxy_redirect' in options:
        config.append('proxy_redirect %s $scheme://$host:%d/notebooks/%s;' % (target, external_https_port, route_key))
    if 'set_host_header' in options:
        config.append('proxy_set_header Host $host;')
    if 'bypass_token_authentication' in options:
        instance_id = options['bypass_token_authentication']
        config.append('proxy_set_header Authorization "token %s";' % (instance_id))

    config.append('}')
    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    with open(path, 'w') as f:
        f.write(
            '\n'.join(config)
        )

    refresh_nginx_config()


@celery_app.task(name="pebbles.tasks.proxy_remove_route")
def proxy_remove_route(route_key):
    """ removes a route from nginx config e.g. when removing a resource.
    """
    logger.info('proxy_remove_route(%s)' % route_key)

    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    if os.path.exists(path):
        os.remove(path)
    else:
        logger.info('proxy_remove_route(): no such file')

    refresh_nginx_config()


def refresh_nginx_config():
    """ writes all the individual route-key- -files into one proxy.conf that
    is read by nginx.
    """
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
