import json

from pebbles.client import PBClient
from pebbles.tasks.celery_app import celery_app, get_token, do_get, do_post_or_put, logger
from pebbles.tasks.celery_app import local_config, get_dynamic_config


def get_provisioning_manager():
    """ Gets a stevedore provisioning manager which controls access to all the
    possible drivers.

    Manager is used to call a method on one or more of the drivers.
    """
    from stevedore import dispatch

    dynamic_config = get_dynamic_config()
    if dynamic_config.get('PLUGIN_WHITELIST'):
        plugin_whitelist = dynamic_config.get('PLUGIN_WHITELIST').split()
        mgr = dispatch.NameDispatchExtensionManager(
            namespace='pebbles.drivers.provisioning',
            check_func=lambda x: x.name in plugin_whitelist,
            invoke_on_load=True,
            invoke_args=(logger, dynamic_config),
        )
    else:
        # ahem, load all plugins if string is empty or not available?
        # is this wise? -jyrsa 2016-11-28
        mgr = dispatch.NameDispatchExtensionManager(
            namespace='pebbles.drivers.provisioning',
            check_func=lambda x: True,
            invoke_on_load=True,
            invoke_args=(logger, dynamic_config),
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


def update_driver_backend_config(token, plugin, backend_config):
    default_config = backend_config['model']
    schema = backend_config['schema']
    payload = {'namespace': plugin, 'key': 'backend_config', 'schema': schema}
    try:
        resp = do_get(token, 'namespaced_keyvalues/%s/%s' % (plugin, 'backend_config')).json()
        user_config = resp['value']
        diff_set = set(default_config.keys()) - set(user_config.keys())
        # compare user_config with default_config
        if diff_set:
            for elem in diff_set:
                user_config[elem] = default_config[elem]
        payload['value'] = user_config
        payload['updated_version_ts'] = resp['updated_ts']
        do_post_or_put(token, 'namespaced_keyvalues/%s/%s' % (plugin, 'backend_config'), payload, 'PUT')
    except:
        payload['value'] = default_config
        do_post_or_put(token, 'namespaced_keyvalues', payload, 'POST')


# update tasks are spawned every 60 seconds, expiry is set to avoid task pile up
@celery_app.task(name="pebbles.tasks.run_update", expires=60)
def run_update(instance_id):
    """ calls the update method for the manager of a single instance.
    """
    logger.info('update triggered for %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'update', token, instance_id)

    logger.info('update done, notifying server')


@celery_app.task(name="pebbles.tasks.publish_plugins_and_configs")
def publish_plugins_and_configs():
    """ Tries to check the PLUGIN_WHITELIST variable for the list of enabled drivers
        and then creates a plugin object for each of them with a default UI config.
        Also, a default backend config is created, if needed by the driver on the backend.
    """
    logger.info('provisioning plugins queried from worker')
    token = get_token()
    mgr = get_provisioning_manager()
    for plugin in mgr.names():
        payload = {'plugin': plugin}
        res_config = mgr.map_method([plugin], 'get_configuration')

        if not len(res_config):
            logger.warn('plugin returned empty configuration: %s' % plugin)
            continue
        config = res_config[0]
        if not config:
            logger.warn('No config for %s obtained' % plugin)
            continue
        for key in ('schema', 'form', 'model'):
            payload[key] = json.dumps(config.get(key, {}))
        do_post_or_put(token, 'plugins', payload)

        res_backend_config = mgr.map_method([plugin], 'get_backend_configuration')
        if not len(res_backend_config):
            logger.warn('plugin returned empty backend configuration: %s' % plugin)
            continue
        if plugin == "DockerDriver":
            backend_config_cpu = res_backend_config[0][0]
            backend_config_gpu = res_backend_config[0][1]
            if not backend_config_cpu:
                logger.warn('No backend cpu config for %s obtained' % plugin)
            else:
                update_driver_backend_config(token, plugin, backend_config_cpu)
            if not backend_config_gpu:
                logger.warn('No backend gpu config for %s obtained' % plugin)
            else:
                update_driver_backend_config(token, "DockerDriverGpu", backend_config_gpu)
        else:
            backend_config = res_backend_config[0]
            if not backend_config:
                logger.warn('No backend config for %s obtained' % plugin)
                continue
                update_driver_backend_config(token, plugin, backend_config)


@celery_app.task(name="pebbles.tasks.housekeeping")
def housekeeping():
    """ calls housekeep for each manager. is run periodically.
    """
    token = get_token()
    logger.info('provisioning plugins queried from worker')
    mgr = get_provisioning_manager()
    mgr.map_method(mgr.names(), 'housekeep', token)


@celery_app.task(name="pebbles.tasks.update_user_connectivity")
def update_user_connectivity(instance_id):
    """ updates the connectivity for a single instance.
    """
    logger.info('updating connectivity for instance %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'update_connectivity', token, instance_id)
    logger.info('update connectivity for instance %s ready' % instance_id)


@celery_app.task(name="pebbles.tasks.fetch_running_instance_logs")
def fetch_running_instance_logs(instance_id):
    """ updates the connectivity for a single instance.
    """
    logger.info('fetching logs for instance %s' % instance_id)
    token = get_token()
    mgr = get_provisioning_manager()
    plugin = get_provisioning_type(token, instance_id)
    mgr.map_method([plugin], 'get_running_instance_logs', token, instance_id)
    logger.info('fetched logs for %s' % instance_id)
