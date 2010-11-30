# encoding: utf-8

from __future__ import unicode_literals

import socket

from pprint import pformat

from marrow.server.testing import ServerTestCase
from marrow.server.http.protocol import HTTPProtocol

from marrow.util.compat import unicode


log = __import__('logging').getLogger(__name__)



def echo(request):
    result = unicode(pformat(request)).encode('utf8')
    return b'200 OK', [
            (b'Content-Type', b'text/plain; charset=utf8'),
            (b'Content-Length', unicode(len(result)).encode('ascii'))
        ], [result]


class TestHTTP10Protocol(ServerTestCase):
    protocol = HTTPProtocol
    arguments = dict(application=echo)
    
    def test_headers(self):
        self.client.write(b"GET / HTTP/1.0\r\n\r\n")
        self.client.read_until(b"\r\n\r\n", self.stop)
        
        headers = self.wait()
        
        self.assertEquals(headers, b'HTTP/1.0 200 OK\r\nContent-Type: text/plain; charset=utf8\r\nContent-Length: 605\r\n\r\n')
    
    def test_request(self):
        self.client.write(b"GET / HTTP/1.0\r\n\r\n")
        self.client.read_until(b"\r\n\r\n", self.stop)
        headers = self.wait()
        
        self.client.read_bytes(605, self.stop)
        body = self.wait()
        
        # EVAL the body to produce a dict, remove SERVER_NAME, SERVER_PORT, wsgi.errors, wsgi.input, and compare.
    
    def test_single(self):
        self.client.write(b"GET / HTTP/1.0\r\n\r\n")
        self.client.read_until(b"\r\n\r\n", self.stop)
        headers = self.wait()
        
        self.client.read_bytes(605, self.stop)
        body = self.wait()
        
        def try_again():
            self.client.write(b"GET / HTTP/1.0\r\n\r\n")
            self.client.read_until(b"\r\n\r\n", self.stop)
            headers = self.wait()
        
        self.assertRaises(socket.error, try_again)
    
    def test_keepalive(self):
        self.client.write(b"GET / HTTP/1.0\r\nConnection: keep-alive\r\n\r\n")
        self.client.read_until(b"\r\n\r\n", self.stop)
        headers1 = self.wait()
        
        self.client.read_bytes(640, self.stop)
        body1 = self.wait()
        
        self.client.write(b"GET / HTTP/1.0\r\nConnection: keep-alive\r\n\r\n")
        self.client.read_until(b"\r\n\r\n", self.stop)
        headers2 = self.wait()
        
        self.client.read_bytes(640, self.stop)
        body2 = self.wait()
        
        self.assertEquals(headers1, headers2)

