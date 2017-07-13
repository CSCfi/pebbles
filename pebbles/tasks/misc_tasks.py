from email.mime.text import MIMEText
import random
import smtplib
import jinja2

from pebbles.client import PBClient
from pebbles.models import Instance
from pebbles.tasks.celery_app import logger, get_token, local_config, get_dynamic_config
from pebbles.tasks.provisioning_tasks import run_update
from pebbles.tasks.celery_app import celery_app


@celery_app.task(name="pebbles.tasks.periodic_update")
def periodic_update():
    """ Runs periodic updates.

    In particular sets old instances up for deprovisioning after they are past
    their maximum_lifetime and sets instances up for up updates.

    Both deletion and update events are not guaranteed to take place
    immediately. If there are more than 10 instances a random sample of 10
    updates and deletions will take place to ensure task is safe to run and
    won't slow down other tasks.
    """
    token = get_token()
    pbclient = PBClient(token, local_config['INTERNAL_API_BASE_URL'], ssl_verify=False)
    instances = pbclient.get_instances()

    deprovision_list = []
    update_list = []
    for instance in instances:
        logger.debug('checking instance for actions %s' % instance['name'])
        deprovision_required = False
        if instance.get('state') in [Instance.STATE_RUNNING]:
            if not instance.get('lifetime_left') and instance.get('maximum_lifetime'):
                deprovision_required = True

            if deprovision_required:
                deprovision_list.append(instance)

        elif instance.get('state') not in [Instance.STATE_FAILED]:
            update_list.append(instance)

    # ToDo: refactor magic number to variable
    if len(deprovision_list) > 10:
        deprovision_list = random.sample(deprovision_list, 10)
    for instance in deprovision_list:
        logger.info('deprovisioning triggered for %s (reason: maximum lifetime exceeded)' % instance.get('id'))
        pbclient.do_instance_patch(instance['id'], {'to_be_deleted': True})
        run_update.delay(instance.get('id'))

    if len(update_list) > 10:
        update_list = random.sample(update_list, 10)
    for instance in update_list:
        run_update.delay(instance.get('id'))


@celery_app.task(name="pebbles.tasks.send_mails")
def send_mails(users):
    """ ToDo: document. apparently sends activation emails.
    """
    dynamic_config = get_dynamic_config()
    j2_env = jinja2.Environment(loader=jinja2.PackageLoader('pebbles', 'templates'))
    base_url = dynamic_config['BASE_URL'].strip('/')
    for email, token in users:
        activation_url = '%s/#/activate/%s' % (base_url, token)
        msg = MIMEText(j2_env.get_template('invitation.txt').render(activation_link=activation_url))
        msg['Subject'] = 'Pebbles account activation'
        msg['To'] = email
        msg['From'] = dynamic_config['SENDER_EMAIL']
        logger.info(msg)

        if not dynamic_config['MAIL_SUPPRESS_SEND']:
            s = smtplib.SMTP(dynamic_config['MAIL_SERVER'])
            if dynamic_config['MAIL_USE_TLS']:
                s.starttls()
            s.sendmail(msg['From'], [msg['To']], msg.as_string())
            s.quit()
        else:
            logger.info('Mail sending suppressed in config')
