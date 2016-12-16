import json

from pouta_blueprints.client import PBClient
from pouta_blueprints.tasks.celery_app import get_token, get_config, do_post, local_config, logger
from pouta_blueprints.tasks.celery_app import celery_app


def get_provisioning_manager():
    """ Gets a stevedore provisioning manager which controls access to all the
    possible drivers.

    Manager is used to call a method on one or more of the drivers.
    """
    from stevedore import dispatch

    config = get_config()
    if config.get('PLUGIN_WHITELIST', ''):
        plugin_whitelist = config.get('PLUGIN_WHITELIST').split()
        mgr = dispatch.NameDispatchExtensionManager(
            namespace='pouta_blueprints.drivers.provisioning',
            check_func=lambda x: x.name in plugin_whitelist,
            invoke_on_load=True,
            invoke_args=(logger, get_config()),
        )
    else:
        # ahem, load all plugins if string is empty or not available?
        # is this wise? -jyrsa 2016-11-28
        mgr = dispatch.NameDispatchExtensionManager(
            namespace='pouta_blueprints.drivers.provisioning',
            check_func=lambda x: True,
            invoke_on_load=True,
            invoke_args=(logger, get_config()),
        )

    logger.debug('provisioning manager loaded, extensions: %s ' % mgr.names())

    return mgr


def get_provisioning_type(token, instance_id):
    """ gets the name of the plugin (driver) that an instance uses.
    """
    pbclient = PBClient(token, local_config['INTERNAL_API_BASE_URL'], ssl_verify=False)

    blueprint = pbclient.get_instance_parent_data(instance_id)
    plugin_id = blueprint['plugin']
    return pbclient.get_plugin_data(plugin_id)['name']


@celery_app.task(name="pouta_blueprints.tasks.run_update")
def run_update(instance_id):
    """ calls the update method for the manager of a single instance.
    """
    logger.info('update triggered for %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'update', token, instance_id)

    logger.info('update done, notifying server')


@celery_app.task(name="pouta_blueprints.tasks.publish_plugins")
def publish_plugins():
    """ ToDo: document.
    """
    logger.info('provisioning plugins queried from worker')
    token = get_token()
    mgr = get_provisioning_manager()
    for plugin in mgr.names():
        payload = {'plugin': plugin}
        res = mgr.map_method([plugin], 'get_configuration')
        if not len(res):
            logger.warn('plugin returned empty configuration: %s' % plugin)
            continue
        config = res[0]

        if not config:
            logger.warn('No config for %s obtained' % plugin)
            continue

        for key in ('schema', 'form', 'model'):
            payload[key] = json.dumps(config.get(key, {}))

        do_post(token, 'plugins', payload)


@celery_app.task(name="pouta_blueprints.tasks.housekeeping")
def housekeeping():
    """ calls housekeep for each manager. is run periodically.
    """
    token = get_token()
    logger.info('provisioning plugins queried from worker')
    mgr = get_provisioning_manager()
    mgr.map_method(mgr.names(), 'housekeep', token)


@celery_app.task(name="pouta_blueprints.tasks.update_user_connectivity")
def update_user_connectivity(instance_id):
    """ updates the connectivity for a single instance.
    """
    logger.info('updating connectivity for instance %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'update_connectivity', token, instance_id)
    logger.info('update connectivity for instance %s ready' % instance_id)
