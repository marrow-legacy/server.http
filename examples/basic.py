#!/usr/bin/env python
# encoding: utf-8

from marrow.server.http import HTTPServer


def hello_waiter():
    import time
    time.sleep(0.5) # simulate slow template generation
    return b'Hello world!'


def hello(request):
    yield b'200 OK', [(b'Content-Type', b'text/plain'), (b'Content-Length', b'12')]
    
    data = (yield request['wsgi.submit'](hello_waiter)).result()
    
    yield data


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    HTTPServer(None, 8080, threaded=25, application=hello).start()
