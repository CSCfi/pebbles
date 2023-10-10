# Test fixture methods to be called from app context so we can access the db
import datetime
import json

from flask import Flask

import pebbles.utils
from pebbles.maintenance.main import run_workspace_expiry_cleanup, WORKSPACE_EXPIRY_GRACE_PERIOD
from pebbles.models import Workspace
from tests.conftest import PrimaryData


class MockResponseAdapter:
    """Adapt response from flask_testing to requests"""

    def __init__(self, resp):
        self.resp = resp
        self.status_code = resp.status_code

    def json(self):
        return self.resp.json


class PBClientMock:
    """Mock PBClient to test workspace cleanup"""

    def __init__(self, request_api):
        self.request_api = request_api
        self.api_base_url = 'api/v1'
        self.token = None
        self.auth = None

    def login(self, ext_id, password):
        auth_url = '%s/sessions' % self.api_base_url
        auth_credentials = dict(ext_id=ext_id, password=password, agreement_sign='signed')
        r = self.request_api.post(auth_url, json=auth_credentials)
        if r.status_code != 200:
            raise RuntimeError('Login failed, status: %d, ext_id "%s", auth_url "%s"' %
                               (r.status_code, ext_id, auth_url))
        self.token = json.loads(r.text).get('token')
        self.auth = pebbles.utils.b64encode_string('%s:%s' % (self.token, '')).replace('\n', '')

    def do_get(self, url):
        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % self.auth,
            'token': self.token
        }
        resp = self.request_api.get('api/v1/%s' % url, headers=headers)
        return MockResponseAdapter(resp)

    def do_delete(self, url):
        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic %s' % self.auth,
            'token': self.token
        }
        resp = self.request_api.delete('api/v1/%s' % url, headers=headers)
        return MockResponseAdapter(resp)

    def delete_workspace(self, workspace_id):
        return self.do_delete('workspaces/%s' % workspace_id)


def test_workspace_cleanup(app: Flask, pri_data: PrimaryData):
    # check that the test set is valid. There should be workspaces that
    # a) have expired but are within grace period
    # b) need cleaning
    current_time = datetime.datetime.utcnow().timestamp()
    wss = Workspace.query.filter_by(status='active').all()
    expired_workspaces = [
        ws for ws in wss
        if ws.expiry_ts
        if not ws.name.startswith('System')
        if ws.expiry_ts < current_time]
    assert expired_workspaces
    expired_workspaces_within_grace = [
        ws for ws in expired_workspaces
        if ws.expiry_ts + WORKSPACE_EXPIRY_GRACE_PERIOD >= current_time]
    assert expired_workspaces_within_grace
    expired_workspaces_beyond_grace = [
        ws for ws in expired_workspaces
        if ws.expiry_ts + WORKSPACE_EXPIRY_GRACE_PERIOD < current_time]
    assert expired_workspaces_beyond_grace

    pb_client = PBClientMock(app.test_client())
    pb_client.login('admin@example.org', 'admin')
    run_workspace_expiry_cleanup(pb_client)

    # check that the cleanup left workspaces before grace alone but removed the ones beyond grace
    wss_after = Workspace.query.filter_by(status='active').all()
    assert len(wss) - len(expired_workspaces_beyond_grace) == len(wss_after)
    for ws in expired_workspaces_within_grace:
        assert ws.id in [w.id for w in wss_after]
    for ws in expired_workspaces_beyond_grace:
        assert ws.id not in [w.id for w in wss_after]
