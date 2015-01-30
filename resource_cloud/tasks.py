import base64
import os
import random
import time
import requests
from celery import Celery
from resource_cloud.config import BaseConfig as config
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)
app = Celery('tasks', broker=config.MESSAGE_QUEUE_URI, backend=config.MESSAGE_QUEUE_URI)
app.conf.CELERY_TASK_SERIALIZER = 'json'


@app.task(name="resource_cloud.tasks.run_provisioning")
def run_provisioning(token, resource_id):
    logger.info('provisioning triggered for %s' % resource_id)

    run_pvc_provisioning(token, resource_id)

    logger.info('provisioning done, notifying server')
    resp = update_resource_state(token, resource_id, 'running')

    if resp.status_code == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status_code, resp.reason)


@app.task(name="resource_cloud.tasks.run_deprovisioning")
def run_deprovisioning(token, resource_id):
    logger.info('deprovisioning triggered for %s' % resource_id)

    run_pvc_deprovisioning(token, resource_id)

    logger.info('deprovisioning done, notifying server')
    resp = update_resource_state(token, resource_id, 'deleted')

    if resp.status_code == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status_code, resp.reason)


def update_resource_state(token, resource_id, state):
    payload = {'state': state}
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {'Content-type': 'application/x-www-form-urlencoded',
               'Accept': 'text/plain',
               'Authorization': 'Basic %s' % auth}
    url = 'https://localhost/api/v1/provisioned_resources/%s' % resource_id
    resp = requests.patch(url, data=payload, headers=headers,
                          verify=config.SSL_VERIFY)
    logger.info('got response %s %s' % (resp.status_code, resp.reason))
    return resp


def run_pvc_provisioning(token, resource_id):
    res_dir = '%s/%s' % (config.PVC_CLUSTER_DATA_DIR, resource_id)

    # will fail if there is already a directory for this resource
    os.makedirs(res_dir)

    # sleep for a while to emulate provisioning
    t = random.randint(10, 30)
    logger.info('sleeping for %s secs' % t)
    time.sleep(t)


def run_pvc_deprovisioning(token, resource_id):
    res_dir = '%s/%s' % (config.PVC_CLUSTER_DATA_DIR, resource_id)

    # sleep for a while to emulate deprovisioning
    t = random.randint(10, 30)
    logger.info('sleeping for %s secs' % t)
    time.sleep(t)
    os.rename(res_dir, '%s.deleted' % res_dir)
