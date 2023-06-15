import datetime
import logging
import sys

from pebbles.client import PBClient
from pebbles.config import RuntimeConfig
from pebbles.models import Workspace
from pebbles.utils import init_logging

# Grace period to keep workspaces after expiry
WORKSPACE_EXPIRY_GRACE_PERIOD = 3600 * 24 * 180


def run_workspace_expiry_cleanup(pb_client):
    """Deletes expired workspaces that are beyond their grace period"""
    logging.info('workspace expiry cleanup starting')
    current_time = datetime.datetime.utcnow().timestamp()
    res = pb_client.do_get('workspaces')
    if res.status_code != 200:
        msg = 'Got error %d: %s when listing workspaces' % (res.status_code, res.json() if res.json else res.text)
        logging.warning(msg)
        raise RuntimeError(msg)

    workspaces = res.json()
    expired_workspaces_beyond_grace = [
        workspace for workspace in workspaces
        if workspace['expiry_ts']
        if not workspace['name'].startswith('System')
        if workspace['expiry_ts'] + WORKSPACE_EXPIRY_GRACE_PERIOD < current_time]
    for ws in expired_workspaces_beyond_grace:
        pb_client.delete_workspace(ws.get('id'))
        logging.info(
            'workspace deleted: id %s, name "%s", expiry time %s',
            ws.get('id'),
            ws.get('name'),
            datetime.datetime.fromtimestamp(ws.get('expiry_ts')).isoformat('_', timespec='seconds'))

    logging.info('workspace expiry cleanup done')


def run_membership_expiry_cleanup(pb_client):
    """Deletes expired workspace memberships by
        - listing workspaces with matching policy
        - asking API to clean up the mappings
    """
    logging.info('membership expiry cleanup starting')
    # fetch workspaces with activity timeout policy
    workspaces = pb_client.do_get('workspaces?membership_expiry_policy_kind=%s' % Workspace.MEP_ACTIVITY_TIMEOUT).json()
    for ws in workspaces:
        res = pb_client.do_post('workspaces/%s/clear_expired_members' % ws.get('id'))
        if res.status_code == 200:
            if res.json().get('num_deleted'):
                logging.info(
                    '%d members removed from workspace %s "%s"',
                    res.json().get('num_deleted'),
                    ws.get('id'),
                    ws.get('name'))
        else:
            logging.warning(
                'Got error %d: %s from workspaces/%s/clear_expired_members',
                res.status_code,
                res.json().get('error') if res.json else res.text,
                ws.get('id'))

    logging.info('membership expiry cleanup done')


if __name__ == '__main__':
    config = RuntimeConfig()
    init_logging(config, 'maintenance')
    logging.info('maintenance starting')
    if len(sys.argv) <= 1:
        logging.warning('No maintenance tasks defined from command line')

    client = PBClient(None, config['INTERNAL_API_BASE_URL'])
    client.login('worker@pebbles', config['SECRET_KEY'])
    try:
        if 'run_workspace_expiry_cleanup' in sys.argv:
            run_workspace_expiry_cleanup(client)
        if 'run_membership_expiry_cleanup' in sys.argv:
            run_membership_expiry_cleanup(client)
    except Exception as e:
        logging.critical('maintenance job exiting due to an error', exc_info=e)
        sys.exit(1)
    logging.info('maintenance finished')
