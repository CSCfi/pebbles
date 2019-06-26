import logging
import requests
import time

import pebbles.utils


class PBInstanceLogHandler(logging.Handler):
    """
    Custom log handler which uploads provisioning logs through ReST interface.
    Could be replaced with HTTPHandler from standard library's logging package once it
    supports HTTPS and authentication header.
    """
    def __init__(self, api_base_url, instance_id, token, ssl_verify=True):
        logging.Handler.__init__(self)
        auth = pebbles.utils.b64encode_string('%s:%s' % (token, '')).replace('\n', '')
        self.ssl_verify = ssl_verify
        self.headers = {
            'Accept': 'text/plain',
            'Authorization': 'Basic %s' % auth}
        self.url = '%s/instances/%s/logs' % (api_base_url, instance_id)

    def emit(self, record):
        log_record = self.format(record)
        payload = {'log_record': log_record}
        try:
            requests.patch(
                self.url, json=payload, headers=self.headers, verify=self.ssl_verify)
        except Exception:
            self.handleError(record)


class PBInstanceLogFormatter(logging.Formatter):
    def __init__(self, log_type):
        self.log_type = log_type
        super(PBInstanceLogFormatter, self).__init__()

    def format(self, record):
        log_record = {
            'message': record.msg,
            'timestamp': time.time(),
            'log_type': self.log_type,
            'log_level': record.levelname
        }
        return log_record
