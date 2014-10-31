# encoding: utf-8
import os
import sys
import platform
import time
import socket

from thrift.protocol.TJSONProtocol import TJSONProtocol
from sds.auth import AuthService
from sds.admin import AdminService
from sds.table import TableService
from sds.client.sdsthttpclient import SdsTHttpClient
from sds.common.constants import DEFAULT_SERVICE_ENDPOINT
from sds.common.constants import DEFAULT_ADMIN_CLIENT_TIMEOUT
from sds.common.constants import DEFAULT_CLIENT_TIMEOUT
from sds.common.constants import AUTH_SERVICE_PATH
from sds.common.constants import ADMIN_SERVICE_PATH
from sds.common.constants import TABLE_SERVICE_PATH
from sds.common.constants import Version
from sds.errors.constants import ERROR_AUTO_BACKOFF
from sds.errors.constants import MAX_RETRY
from sds.client.exceptions import SdsTransportException


class ClientFactory:
    def __init__(self, credential, retryIfTimeout = False):
        self._credential = credential
        self.retryIfTimeout = retryIfTimeout
        ver = Version()
        version = "%s.%s.%s" % (ver.major, ver.minor, ver.patch)
        script = os.path.basename(sys.argv[0])
        if script:
            self._agent = "Python-SDK/%s Python/%s(%s)" % \
                          (version, platform.python_version(), script)
        else:
            self._agent = "Python-SDK/%s Python/%s" % (version, platform.python_version())

    def new_default_auth_client(self):
        return self.new_auth_client(DEFAULT_SERVICE_ENDPOINT + AUTH_SERVICE_PATH,
                                    DEFAULT_CLIENT_TIMEOUT)

    def new_auth_client(self, url, timeout):
        client = self.get_client(AuthService.Client, url, timeout)
        return RetryableClient(client, self.retryIfTimeout)

    def new_default_admin_client(self):
        return self.new_admin_client(DEFAULT_SERVICE_ENDPOINT + ADMIN_SERVICE_PATH,
                                     DEFAULT_ADMIN_CLIENT_TIMEOUT)

    def new_admin_client(self, url, timeout):
        client = self.get_client(AdminService.Client, url, timeout)
        return RetryableClient(client, self.retryIfTimeout)

    def new_default_table_client(self):
        return self.new_table_client(DEFAULT_SERVICE_ENDPOINT + TABLE_SERVICE_PATH,
                                     DEFAULT_CLIENT_TIMEOUT)

    def new_table_client(self, url, timeout):
        client = self.get_client(TableService.Client, url, timeout)
        return RetryableClient(client, self.retryIfTimeout)

    def get_client(self, clazz, url, timeout):
        http_client = SdsTHttpClient(self._credential, url, timeout)
        http_client.setCustomHeaders({'User-Agent': self._agent})
        thrift_protocol = TJSONProtocol(http_client)
        return clazz(thrift_protocol, thrift_protocol)


class RetryableClient:
    def __init__(self, client, retryIfTimeout):
        self.client = client
        self.retryIfTimeout = retryIfTimeout

    def __getattr__(self, item):
        def __call_with_retries(*args):
            retry = 0
            while retry < 3:
                try:
                    return getattr(self.client, item)(*args)
                except SdsTransportException, ex:
                    if ERROR_AUTO_BACKOFF.has_key(ex.errorCode) and retry < MAX_RETRY:
                        sec = ERROR_AUTO_BACKOFF[ex.errorCode] / 1000.0 * (1 << retry)
                        time.sleep(sec)
                        retry += 1
                    else:
                        raise ex
                except socket.timeout, se:
                    if self.retryIfTimeout and retry < MAX_RETRY:
                        retry += 1
                    else:
                        raise se

        return __call_with_retries
