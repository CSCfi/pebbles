import logging
from pylogbeat import PyLogBeatClient


class BeatsHandler(logging.Handler):
    """
    Logging handler used to write logs to logstash with Beats protocol
    """
    def __init__(self, host, port, ssl_enable=True) -> None:
        self.client = PyLogBeatClient(host, port, ssl_enable=ssl_enable)
        logging.Handler.__init__(self=self)

    def write_log(self, msg: logging.LogRecord) -> None:
        self.client.connect()
        # LogRecord object needs to be converted to a list containing a dictionary
        # in order to pass it to the pylogbeat client
        self.client.send([msg.__dict__.copy()])
        self.client.close()

    def emit(self, record) -> None:
        self.write_log(record)
