import base64
import logging
import requests


class PBInstanceLogHandler(logging.Handler):
    """
    Custom log handler which uploads provisioning logs through ReST interface.
    Could be replaced with HTTPHandler from standard library's logging package once it
    supports HTTPS and authentication header.
    """
    def __init__(self, api_base_url, instance_id, token, log_type, ssl_verify=True):
        logging.Handler.__init__(self)
        auth = base64.encodestring('%s:%s' % (token, '')).replace('\n', '')
        self.log_type = log_type
        self.ssl_verify = ssl_verify
        self.headers = {
            'Content-type': 'application/x-www-form-urlencoded',
            'Accept': 'text/plain',
            'Authorization': 'Basic %s' % auth}
        self.url = '%s/instances/%s/logs' % (api_base_url, instance_id)

    def emit(self, record):
        payload = {'text': record.msg, 'type': self.log_type}
        try:
            requests.patch(
                self.url, data=payload, headers=self.headers, verify=self.ssl_verify)
        except Exception:
            self.handleError(record)
