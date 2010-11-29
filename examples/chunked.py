#!/usr/bin/env python
# encoding: utf-8

import pprint
import logging
from marrow.server.http import HTTPServer



def hello(request):
    # request['wsgi.errors'].write("Oh noes!") # Example error, output through the logging module.  \o/
    logging.info("Request:\n%s", pprint.pformat(request))
    return b'200 OK', [(b'Content-Type', b'text/plain')], [b'Hello ', b'world!']


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    HTTPServer(None, 8080, application=hello).start()
