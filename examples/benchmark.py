#!/usr/bin/env python
# encoding: utf-8

from __future__ import unicode_literals
from __future__ import print_function

import signal
import subprocess

from marrow.io.ioloop import IOLoop
from marrow.script import execute
from marrow.server.http import HTTPServer



def hello(request):
    return b'200 OK', [(b'Content-Length', 13), (b'Content-Type', b'text/plain')], [b'Hello world!\n']


def main(host="127.0.0.1", port=8888):
    """A simple benchmark of Marrow's HTTP server.
    
    This script requires that ApacheBench (ab) be installed.
    Based on the simple benchmark for Tornado.
    
    Running with profiling:
    
    python -m cProfile -o /tmp/prof benchmark.py
    python -c 'import pstats; pstats.Stats("/tmp/prof").strip_dirs().sort_stats("time").print_callers(20)'
    """
    
    server = HTTPServer(host=host, port=port, application=hello)
    
    def handle_sigchld(sig, frame):
        server.io.add_callback(server.stop)
    
    signal.signal(signal.SIGCHLD, handle_sigchld)
    
    
    server.start(testing=IOLoop.instance())
    proc = subprocess.Popen("ab -n 10000 -c 25 http://%s:%d/" % (host, port), shell=True)
    server.io.start()



if __name__ == '__main__':
    execute(main)
