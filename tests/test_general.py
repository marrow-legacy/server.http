# encoding: utf-8

from __future__ import unicode_literals

import socket

from pprint import pformat

from marrow.server.http.testing import HTTPTestCase, CRLF, EOH

from marrow.util.compat import unicode

from applications import die, hello_unicode, generator


log = __import__('logging').getLogger(__name__)



class TestHTTPProtocolGeneral(HTTPTestCase):
    arguments = dict(application=die)
    
    def test_internal_error(self):
        response = self.request()
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"500")
        self.assertEquals(response.status, b"Internal Server Error")


class TestHTTPProtocolUnicode(HTTPTestCase):
    arguments = dict(application=hello_unicode)
    
    def test_unicode_response(self):
        response = self.request()
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        
        
class TestHTTPProtocolGenerator(HTTPTestCase):
    arguments = dict(application=generator, pedantic=False)
    
    def test_unicode_response(self):
        response = self.request()
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-length'], b"10")
        self.assertEquals(response.body, b"0123456789")
        
