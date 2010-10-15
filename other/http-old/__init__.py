# encoding: utf-8

import logging
from server import HTTPServer


log = __import__('logging').getLogger(__name__)


if __name__ == '__main__':
    logging.basicConfig(level=10)
    
    def hello(environ): return '200 OK', [('Content-Type', 'text/plain')], ['Hello world!\n']
        
    server = HTTPServer(hello, ('0.0.0.0', 8080))
    
    try:
        server.start()
    
    except (KeyboardInterrupt, SystemExit):
        server.stop()
