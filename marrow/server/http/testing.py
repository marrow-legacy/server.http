# encoding: utf-8

"""Unit testing helpers for asynchronous marrow.io IOLoop and IOStream.

This is a barely-modified version of the unit testing rig from Tornado.
"""

from __future__ import unicode_literals

import os
import sys
import time
import socket

from marrow.util.compat import unicode
from marrow.server.testing import ServerTestCase
from marrow.server.http.protocol import HTTPProtocol


log = __import__('logging').getLogger(__name__)
__all__ = ['CRLF', 'EOH', 'Response', 'HTTPTestCase']


CRLF = b"\r\n"
EOH = CRLF + CRLF



class Response(dict):
    def __init__(self, headers, body):
        self.complete = headers + body
        self.headers = headers
        self.body = body
        
        status, _, headers = headers.partition(CRLF)
        
        self.protocol, _, status = status.partition(b" ")
        self.code, _, self.status = status.partition(b" ")
        
        processed = []
        headers = headers.strip(CRLF).split(CRLF)
        for i in headers:
            name, _, value = i.partition(b": ")
            processed.append((name.lower(), value))
        
        super(Response, self).__init__(processed)


class HTTPTestCase(ServerTestCase):
    protocol = HTTPProtocol
    
    def request(self, method=b"GET", path=b"/", host=b"localhost", protocol=b"HTTP/1.1", headers=None, body=None):
        if headers is None: headers = []
        
        request = method + b" " + (path if protocol == b"HTTP/1.0" else (b"http://" + host + path)) + b" " + protocol + b"\r\nHost: " + host
        log.debug("Sending request: %r", request)
        
        length_found = False
        for name, value in headers:
            if name.lower() == b"content-length": length_found = True
            request += CRLF + name + b": " + value
        
        if method not in [b"GET", b"HEAD"] and body and not length_found:
            request += CRLF + b"Transfer-Encoding: chunked"
        
        log.debug("Writing: %r", request + EOH)
        self.client.write(request + EOH)
        
        if method not in [b"GET", b"HEAD"] and body:
            if length_found:
                for i in body:
                    log.debug("Writing: %r", i)
                    self.client.write(i)
            
            else:
                for i in body:
                    log.debug("Writing chunk header: %r", unicode(hex(len(i))[2:]).encode('ascii') + CRLF)
                    self.client.write(unicode(hex(len(i))[2:]).encode('ascii') + CRLF)
                    log.debug("Writing chunk body: %r", i + CRLF)
                    self.client.write(i + CRLF)
                
                log.debug("Writing chunk trailer: 0\\r\\n\\r\\n")
                self.client.write(b"0" + CRLF + CRLF)
        
        self.client.read_until(EOH, self.stop)
        
        headers = self.wait()
        
        log.debug("Recieved headers: %r", headers)
        
        response = Response(headers, b"")
        
        if response.get(b"transfer-encoding", None) == b"chunked":
            while True:
                self.client.read_until(CRLF, self.stop)
                length = self.wait()[:-2]
                
                log.debug("Recieved chunk header: %r", length)
                
                if length == b"0":
                    log.debug("Reading chunked request trailers.")
                    self.client.read_bytes(2, self.stop)
                    log.debug("Recieved trailers: %r", self.wait())
                    break
                
                self.client.read_bytes(int(length, 16) + 2, self.stop)
                chunk = self.wait()
                log.debug("Recieved chunk: %r", chunk)
                response.body += chunk[:-2]
        
        elif b"content-length" in response:
            self.client.read_bytes(int(response[b'content-length']), self.stop)
            response.body = self.wait()
            log.debug("Recieved body: %r", response.body)
        
        response.complete = response.headers + response.body
        
        return response
