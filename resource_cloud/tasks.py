from celery import Celery

app = Celery('tasks', broker='amqp://guest@localhost//')


@app.task(name="resource_cloud.tasks.run_provisioning")
def run_provisioning():
    return 'ok'
