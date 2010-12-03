# encoding: utf-8

from __future__ import unicode_literals

import socket

from pprint import pformat

from marrow.server.http.testing import HTTPTestCase, CRLF, EOH

from marrow.util.compat import unicode


log = __import__('logging').getLogger(__name__)


def clean(request):
    del request['SERVER_NAME']
    del request['SERVER_PORT']
    del request['wsgi.errors']
    
    request['wsgi.input'] = request['wsgi.input'].read()
    
    if not request['wsgi.input']:
        del request['wsgi.input']


def echo(request):
    clean(request)
    result = unicode(pformat(request)).encode('utf8')
    log.info("Result: %r", result)
    return b'200 OK', [
            (b'Content-Type', b'text/plain; charset=utf8'),
            (b'Content-Length', unicode(len(result)).encode('ascii'))
        ], [result]


def chunked(request):
    clean(request)
    result = unicode(pformat(request)).encode('utf8')
    return b'200 OK', [
            (b'Content-Type', b'text/plain; charset=utf8'),
        ], result.split(b"\n")


def body_echo(request):
    clean(request)
    
    headers = [(b'Content-Type', b'text/plain; charset=utf8')]
    
    if 'HTTP_CONTENT_LENGTH' in request:
        headers.append((b'Content-Length', unicode(len(request['wsgi.input'])).encode('ascii')))
    
    return b'200 OK', headers, [request['wsgi.input']]


class TestHTTP11Protocol(HTTPTestCase):
    arguments = dict(application=echo)
    
    def test_headers(self):
        response = self.request(headers=[(b'Connection', b'close')])
        
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-type'], b"text/plain; charset=utf8")
        # self.assertEquals(response[b'content-length'], b"468")
    
    def test_request(self):
        response = self.request(headers=[(b'Connection', b'close')])
        
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-type'], b"text/plain; charset=utf8")
        # self.assertEquals(response[b'content-length'], b"468")
        
        log.info("Recieved: %r", response.body)
        raise Exception
        # request = eval(response.body)
        
        # expect = {
        #         'CONTENT_LENGTH': None,
        #         'CONTENT_TYPE': None,
        #         'FRAGMENT': b'',
        #         'HTTP_CONNECTION': b'close',
        #         'HTTP_HOST': b'localhost',
        #         'PARAMETERS': b'',
        #         'PATH_INFO': b'/',
        #         'QUERY_STRING': b'',
        #         'REMOTE_ADDR': b'127.0.0.1',
        #         'REQUEST_METHOD': b'GET',
        #         'SCRIPT_NAME': b'',
        #         'SERVER_ADDR': b'127.0.0.1',
        #         'SERVER_PROTOCOL': b'HTTP/1.1',
        #         'wsgi.multiprocess': False,
        #         'wsgi.multithread': False,
        #         'wsgi.run_once': False,
        #         'wsgi.url_scheme': b'http',
        #         'wsgi.version': (2, 0)
        #     }
        # 
        # self.assertEquals(request, expect)
    
    def test_single(self):
        self.request(headers=[(b'Connection', b'close')])
        
        def try_again():
            self.request(headers=[(b'Connection', b'close')])
        
        self.assertRaises((socket.error, IOError), try_again)
    
    def test_keepalive(self):
        one = self.request()
        two = self.request()
        
        self.assertEquals(one, two)


class TestChunkedHTTP11Protocol(HTTPTestCase):
    arguments = dict(application=chunked)
    
    def test_chunked(self):
        response = self.request()
        
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-type'], b"text/plain; charset=utf8")
        self.assertEquals(response[b'transfer-encoding'], b"chunked")
        
        request = eval(response.body)
        
        expect = {
                'CONTENT_LENGTH': None,
                'CONTENT_TYPE': None,
                'FRAGMENT': b'',
                'HTTP_HOST': b'localhost',
                'PARAMETERS': b'',
                'PATH_INFO': b'/',
                'QUERY_STRING': b'',
                'REMOTE_ADDR': b'127.0.0.1',
                'REQUEST_METHOD': b'GET',
                'SCRIPT_NAME': b'',
                'SERVER_ADDR': b'127.0.0.1',
                'SERVER_PROTOCOL': b'HTTP/1.1',
                'wsgi.multiprocess': False,
                'wsgi.multithread': False,
                'wsgi.run_once': False,
                'wsgi.url_scheme': b'http',
                'wsgi.version': (2, 0)
            }
        
        self.assertEquals(request, expect)


class TestHTTP11BodyProtocol(HTTPTestCase):
    arguments = dict(application=chunked)
    
    def test_normal(self):
        body = b"Hello world!"
        response = self.request(b"PUT", headers=[(b'Content-Length', unicode(len(body)).encode('ascii'))], body=[body])
        
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-type'], b"text/plain; charset=utf8")
        #self.assertEquals(response[b'transfer-encoding'], b"chunked")
        
        request = eval(response.body)
        
        expect = {
                'CONTENT_LENGTH': b"12",
                'CONTENT_TYPE': None,
                'FRAGMENT': b'',
                'HTTP_HOST': b'localhost',
                'PARAMETERS': b'',
                'PATH_INFO': b'/',
                'QUERY_STRING': b'',
                'REMOTE_ADDR': b'127.0.0.1',
                'REQUEST_METHOD': b'PUT',
                'SCRIPT_NAME': b'',
                'SERVER_ADDR': b'127.0.0.1',
                'SERVER_PROTOCOL': b'HTTP/1.1',
                'wsgi.multiprocess': False,
                'wsgi.multithread': False,
                'wsgi.run_once': False,
                'wsgi.url_scheme': b'http',
                'wsgi.version': (2, 0),
                'wsgi.input': b"Hello world!"
            }
        
        self.assertEquals(request, expect)
    
    def test_chunked(self):
        body = b"Hello world!"
        response = self.request(b"PUT", body=[body])
        
        self.assertEquals(response.protocol, b"HTTP/1.1")
        self.assertEquals(response.code, b"200")
        self.assertEquals(response.status, b"OK")
        self.assertEquals(response[b'content-type'], b"text/plain; charset=utf8")
        self.assertEquals(response[b'transfer-encoding'], b"chunked")
        
        request = eval(response.body)
        
        expect = {
                'CONTENT_LENGTH': None,
                'CONTENT_TYPE': None,
                'FRAGMENT': '',
                'HTTP_HOST': b'localhost',
                'HTTP_TRANSFER_ENCODING': b'chunked',
                'PARAMETERS': b'',
                'PATH_INFO': b'/',
                'QUERY_STRING': b'',
                'REMOTE_ADDR': b'127.0.0.1',
                'REQUEST_METHOD': b'PUT',
                'SCRIPT_NAME': b'',
                'SERVER_ADDR': b'127.0.0.1',
                'SERVER_PROTOCOL': b'HTTP/1.1',
                'wsgi.input': b"Hello world!",
                'wsgi.multiprocess': False,
                'wsgi.multithread': False,
                'wsgi.run_once': False,
                'wsgi.url_scheme': b'http',
                'wsgi.version': (2, 0),
            }
        
        self.assertEquals(request, expect)
