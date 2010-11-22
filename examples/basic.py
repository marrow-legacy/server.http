#!/usr/bin/env python
# encoding: utf-8

from marrow.server.http import HTTPServer



def hello(request):
    # request['wsgi.errors'].write("Oh noes!") # Example error, output through the logging module.  \o/
    return b'200 OK', [(b'Content-Type', b'text/plain'), (b'Content-Length', b'12')], [b'Hello world!']


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    HTTPServer(None, 8080, fork=1, application=hello).start()
