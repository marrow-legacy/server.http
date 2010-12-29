#!/usr/bin/env python
# encoding: utf-8

from __future__ import unicode_literals
from __future__ import print_function

import signal
import subprocess

from marrow.io.ioloop import IOLoop
from marrow.script import execute, script, describe
from marrow.server.http import HTTPServer



def hello(request):
    return b'200 OK', [(b'Content-Length', 13), (b'Content-Type', b'text/plain')], [b'Hello world!\n']


@script(
        title="Marrow HTTPD Benchmark",
        version="1.0",
        copyright="Copyright 2010 Alice Bevan-McGregor"
    )
@describe(
        host="The interface to bind to, defaults to \"127.0.0.1\".",
        port="The port number to bind to, defaults to 8888.",
        pedantic="Enable strict WSGI 2 compliance checks."
    )
def main(host="127.0.0.1", port=8888, pedantic=False):
    """A simple benchmark of Marrow's HTTP server.
    
    This script requires that ApacheBench (ab) be installed.
    Based on the simple benchmark for Tornado.
    
    Running with profiling:
    
    python -m cProfile -o /tmp/prof benchmark.py
    python -c 'import pstats; pstats.Stats("/tmp/prof").strip_dirs().sort_stats("time").print_callers(20)'
    """
    
    server = HTTPServer(host=host, port=port, application=hello, pedantic=pedantic)
    
    def handle_sigchld(sig, frame):
        server.io.add_callback(server.stop)
    
    signal.signal(signal.SIGCHLD, handle_sigchld)
    
    
    server.start(testing=IOLoop.instance())
    proc = subprocess.Popen("ab -n 10000 -c 25 http://%s:%d/" % (host, port), shell=True)
    server.io.start()



if __name__ == '__main__':
    execute(main)
