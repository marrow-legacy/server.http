#!/usr/bin/env python
# encoding: utf-8

import sys
import cProfile
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
        host="The interface to bind to.\nDefault: \"127.0.0.1\"",
        port="The port number to bind to.\nDefault: 8888",
        pedantic="Enable strict WSGI 2 compliance checks.",
        profile="If enabled, profiling results will be saved to \"results.prof\".",
        threaded="If defined, spawn this many threads.\nDefault: No threading."
    )
def main(host="127.0.0.1", port=8888, pedantic=False, profile=False, threaded=0):
    """A simple benchmark of Marrow's HTTP server.
    
    This script requires that ApacheBench (ab) be installed.
    Based on the simple benchmark for Tornado.
    
    If profiling is enabled, you can examine the results by running:
    
    python -c 'import pstats; pstats.Stats("/tmp/prof").strip_dirs().sort_stats("time").print_callers(20)'
    """
    
    elif threaded == 0:
        threaded = False
    
    def do():
        
        server = HTTPServer(host=host, port=port, application=hello, pedantic=pedantic, threading=threaded)
        
        def handle_sigchld(sig, frame):
            server.io.add_callback(server.stop)
        
        signal.signal(signal.SIGCHLD, handle_sigchld)
        
        server.start(testing=IOLoop.instance())
        proc = subprocess.Popen("ab -n 10000 -c 25 http://%s:%d/" % (host, port), shell=True)
        server.io.start()
    
    try:
        if not profile:
            do()
    
        else:
            cProfile.runctx('do()', globals(), locals(), 'results.prof')
            sys.stdout.write(b"\nProfiling results written to: results.prof\n\n")
    
    except KeyboardInterrupt:
        sys.stdout.write(b"\nBenchmark cancelled.\n\n")



if __name__ == '__main__':
    execute(main)
