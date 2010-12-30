# encoding: utf-8

import socket

from functools import partial
from pprint import pformat

from marrow.server.http.testing import HTTPTestCase, CRLF, EOH

from marrow.util.compat import unicode


log = __import__('logging').getLogger(__name__)


from applications import echo


class TestHTTP10Protocol(HTTPTestCase):
    arguments = dict(application=partial(echo, False))
    maxDiff = None
    
    def test_headers(self):
        response = self.request(protocol=b"HTTP/1.0")
        self.assertEquals(response.protocol, b"HTTP/1.0")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-type'], b"text/plain; charset=utf8")
        # self.assertEquals(response[b'content-length'], b"438")
    
    def test_request(self):
        response = self.request(protocol=b"HTTP/1.0")
        request = eval(response.body)
        
        expect = {
                'CONTENT_LENGTH': None,
                'CONTENT_TYPE': None,
                'FRAGMENT': '',
                'HTTP_HOST': 'localhost',
                'PARAMETERS': unicode(),
                'PATH_INFO': b'/'.decode('iso-8859-1'),
                'QUERY_STRING': unicode(),
                'REMOTE_ADDR': '127.0.0.1',
                'REQUEST_METHOD': 'GET',
                'SCRIPT_NAME': unicode(),
                'SERVER_ADDR': '127.0.0.1',
                'SERVER_PROTOCOL': 'HTTP/1.0',
                'wsgi.multiprocess': False,
                'wsgi.multithread': False,
                'wsgi.run_once': False,
                'wsgi.url_scheme': 'http',
                'wsgi.version': (2, 0),
                'REQUEST_URI': b'/',
                'wsgi.async': False,
                'wsgi.uri_encoding': 'utf8'
            }
        
        self.assertEquals(request, expect)
    
    def test_single(self):
        self.request(protocol=b"HTTP/1.0")
        
        def try_again():
            self.request(protocol=b"HTTP/1.0")
        
        self.assertRaises((socket.error, IOError), try_again)
    
    def test_keepalive(self):
        one = self.request(protocol=b"HTTP/1.0", headers=[(b'Connection', b'keep-alive')])
        two = self.request(protocol=b"HTTP/1.0", headers=[(b'Connection', b'keep-alive')])
        
        self.assertEquals(one, two)
