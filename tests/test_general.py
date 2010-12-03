# encoding: utf-8

from __future__ import unicode_literals

import socket

from pprint import pformat

from marrow.server.http.testing import HTTPTestCase, CRLF, EOH

from marrow.util.compat import unicode


log = __import__('logging').getLogger(__name__)



def die(request):
    1/0


class TestHTTPProtocolGeneral(HTTPTestCase):
    arguments = dict(application=die)
    
    def test_internal_error(self):
        response = self.request()
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"500")
        self.assertEquals(response.status, b"Internal Server Error")
