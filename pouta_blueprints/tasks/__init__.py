import pouta_blueprints.tasks.celery_app

import pouta_blueprints.tasks.provisioning_tasks
import pouta_blueprints.tasks.proxy_tasks
import pouta_blueprints.tasks.misc_tasks

run_update = pouta_blueprints.tasks.provisioning_tasks.run_update

update_user_connectivity = pouta_blueprints.tasks.provisioning_tasks.update_user_connectivity

proxy_add_route = pouta_blueprints.tasks.proxy_tasks.proxy_add_route

proxy_remove_route = pouta_blueprints.tasks.proxy_tasks.proxy_remove_route

send_mails = pouta_blueprints.tasks.misc_tasks.send_mails

periodic_update = pouta_blueprints.tasks.misc_tasks.periodic_update
