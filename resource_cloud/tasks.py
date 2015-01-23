from celery import Celery
from resource_cloud.config import BaseConfig as config

app = Celery('tasks', broker=config.MESSAGE_QUEUE_URI)


@app.task(name="resource_cloud.tasks.run_provisioning")
def run_provisioning():
    return 'ok'
