import glob
from string import Template
import os
from pouta_blueprints.tasks.celery_app import logger, get_config
from pouta_blueprints.tasks.celery_app import celery_app

RUNTIME_PATH = '/webapps/pouta_blueprints/run/proxy_conf.d'


@celery_app.task(name="pouta_blueprints.tasks.proxy_add_route")
def proxy_add_route(route_key, target, options):
    logger.info('proxy_add_route(%s, %s)' % (route_key, target))

    # generate a location snippet for nginx proxy config
    # see https://support.rstudio.com/hc/en-us/articles/200552326-Running-with-a-Proxy

    template = Template(
        """
        location /notebooks/${route_key}/ {
        $no_rw
        $set_hh
        proxy_pass ${target};
        $no_rd
        proxy_set_header Upgrade $$$http_upgrade;
        proxy_set_header Connection "upgrade";
        }
        """
    )

    no_rw = no_rd = set_hh = ''
    if 'proxy_rewrite' in options:
        no_rw = 'rewrite ^/notebooks/${route_key}/(.*)$$ /$$1 break;'
    if 'proxy_redirect' in options:
        no_rd = 'proxy_redirect ${target} $$scheme://$$host:${external_https_port}/notebooks/${route_key};'
    if 'set_host_header' in options:
        set_hh = 'proxy_set_header Host $$host;'
    options_template = Template(template.safe_substitute(no_rw=no_rw, no_rd=no_rd, set_hh=set_hh))

    path = '%s/route_key-%s' % (RUNTIME_PATH, route_key)
    with open(path, 'w') as f:
        f.write(
            options_template.substitute(
                route_key=route_key,
                target=target,
                external_https_port=get_config()['EXTERNAL_HTTPS_PORT'],
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
