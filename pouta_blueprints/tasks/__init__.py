from . import celery_app
from . import provisioning_tasks
from . import proxy_tasks
from . import misc_tasks

celery_app = celery_app

run_update = provisioning_tasks.run_update

update_user_connectivity = provisioning_tasks.update_user_connectivity

proxy_add_route = proxy_tasks.proxy_add_route

proxy_remove_route = proxy_tasks.proxy_remove_route

send_mails = misc_tasks.send_mails

periodic_update = misc_tasks.periodic_update
