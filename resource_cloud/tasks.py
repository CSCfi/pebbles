import base64
import time
import httplib
import urllib
from celery import Celery
from resource_cloud.config import BaseConfig as config
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)
app = Celery('tasks', broker=config.MESSAGE_QUEUE_URI, backend=config.MESSAGE_QUEUE_URI)
app.conf.CELERY_TASK_SERIALIZER = 'json'


@app.task(name="resource_cloud.tasks.run_provisioning")
def run_provisioning(token, resource_id):
    logger.info('provisioning triggered for %s' % resource_id)

    time.sleep(5)

    logger.info('provisioning done, notifying server')
    resp = update_resource_state(token, resource_id, 'running')

    if resp.status == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status, resp.reason)


@app.task(name="resource_cloud.tasks.run_deprovisioning")
def run_deprovisioning(token, resource_id):
    logger.info('deprovisioning triggered for %s' % resource_id)

    time.sleep(5)

    logger.info('deprovisioning done, notifying server')
    resp = update_resource_state(token, resource_id, 'deleted')

    if resp.status == 200:
        return 'ok'

    return 'error: %s %s' % (resp.status, resp.reason)

    return 'dummy ok'


def update_resource_state(token, resource_id, state):
    params = urllib.urlencode({'state': state})
    auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
    headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain", \
               'Authorization': 'Basic %s' % auth}
    conn = httplib.HTTPSConnection("localhost")
    conn.request("PATCH", "/api/v1/provisioned_resources/%s" % resource_id, params, headers)
    resp = conn.getresponse()
    logger.info('got response %s %s' % (resp.status, resp.reason))
    return resp