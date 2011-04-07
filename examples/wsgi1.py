#!/usr/bin/env python
# encoding: utf-8

from marrow.server.http import HTTPServer
from marrow.server.http.adapt import wsgi1


@wsgi1
def hello(environ, start_response):
    # request['wsgi.errors'].write("Oh noes!") # Example error, output through the logging module.  \o/
    
    start_response(b'200 OK', [(b'Content-Type', b'text/plain'), (b'Content-Length', b'12')])
    
    return [b'Hello world!']


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    HTTPServer(None, 8080, fork=1, application=hello).start()
