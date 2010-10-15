# encoding: utf-8


import os
import re
import sys
import rfc822
import socket
import Queue

import threading
import time
import traceback
from urllib import unquote
from urlparse import urlparse
import warnings

import errno

from marrow.util.compat import exception, IO
from marrow.util.bunch import Bunch

from marrow.server.pool import ThreadPool
from marrow.server.http import fixes
from marrow.server.http import release
from marrow.server.http2.sockfo import CP_fileobject

from api import Server
from marrow.server.http.const import *


__all__ = ['HTTPServer']

log = __import__('logging').getLogger(__name__)



class HTTPServer(Server):
    """A full-fledged HTTP/1.1 HTTP server for WSGI 2.0 applications.
    
    A simple usage example:
    
        from marrow.server.http import HTTPServer
        
        def helloworld(environ):
            return '200 OK', [('Content-Type', 'text/plain')], "Hello world!\n"
        
        server = HTTPServer('0.0.0.0', 8080, app=helloworld)
        
    
    """
    
    class Protocol(object):
        option = Bunch(
                socket = Bunch(queue=5, timeout=10, nodelay=True),
                limit = Bunch(headers=512*1024, body=100*1024*1024),
                
                wsgi = (2, 0),
                protocol = 'HTTP/1.1',
                version = 'Marrow/' + release.version,
                nslookup = False,
                
                thread = Bunch(pool=10, maximum=None, timeout=5),
                # ssl = Bunch(context=None, certificate=None, chain=None, key=None, module='pyopenssl')
            )
        
        instance = None
        
        def _set_interrupt(self, interrupt):
            self._interrupt = True
            self.stop()
            self._interrupt = interrupt
        
        interrupt = property(lambda self: self._interrupt, _set_interrupt, doc="Set this to an Exception instance to interrupt the server.")
        
        def __init__(self, server, app, name=None, **options):
            # TODO: Have a sane, somewhat recursive way to update the options.
            self.server = server
            self.app = app
            
            if name is None:
                name = socket.gethostname()
            
            self.name = name
            
            self.pool = ThreadPool(self, self.option.thread.pool, self.option.thread.maximum)
            
            self.ready = False
        
        def start(self):
            """Run the web server forever.
            
            The controlling Server instance manages shutdown for us.
            """
            
            self._interrupt = False
            self.socket = None
            
            connections = []
            
            log.debug("Binding sockets.")
            
            if self.server.socket:
                # AF_UNIX on-disk socket.
                
                # TODO: Verify this does anything... O_o
                
                try: os.unlink(self.server.socket)
                except: pass
                
                # TODO: Make this configurable.
                try: os.chmod(self.server.socket, 0777)
                except: pass
                
                connections.append((self.server.socket, socket.AF_UNIX, socket.SOCK_STREAM, 0, "", self.server.socket))
            
            elif self.server.bind:
                # AF_INET or AF_INET6 IP-based socket.
                
                for host, port in self.server.bind:
                    try:
                        connections.extend(socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE))
                    
                    except socket.gaierror:
                        if ':' in host:
                            connections.append((socket.AF_INET6, socket.SOCK_STREAM, 0, "", (host, port, 0, 0)))
                            continue
                        
                        connections.append((socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, port)))
            
            for family, kind, protocol, name, sa in connections:
                self.bind(sa, family, kind, protocol)
                break # TODO: Fixme.
            
            # Start the worker threads.
            log.debug("Starting worker threads.")
            self.pool.start()
            
            log.debug("Protocol ready.")
            
            self.ready = True
        
        def main(self):
            while self.ready:
                self.tick()
                
                if self.interrupt:
                    while self.interrupt is True:
                        # Wait for self.stop() to complete.
                        time.sleep(0.1)
                    
                    if self.interrupt:
                        raise self.interrupt
        
        def stop(self):
            """Gracefully shutdown a server that is serving forever."""
            
            self.ready = False
            
            sock = self.socket
            
            if sock:
                if not self.server.socket:
                    # Touch our own socket to make accept() return immediately.
                    try:
                        host, port = sock.getsockname()[:2]
                    
                    except socket.error, x:
                        if x.args[0] not in SOCKET_ERRORS_TO_IGNORE:
                            raise
                    
                    else:
                        for res in socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM):
                            af, socktype, proto, canonname, sa = res
                            s = None
                            
                            try:
                                s = socket.socket(af, socktype, proto)
                                s.settimeout(1.0)
                                s.connect((host, port))
                                s.close()
                            
                            except socket.error:
                                if s: s.close()
                
                getattr(sock, 'close', lambda: None)()
                
                self.socket = None

            self.pool.stop(self.option.thread.timeout)
        
        def bind(self, addr, family, kind, protocol=0):
            """Create (or recreate) the actual socket object."""
            sock = socket.socket(family, kind, protocol)
            fixes.prevent_socket_inheritance(sock)
            
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if self.option.socket.nodelay and isinstance(addr, tuple):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # TODO: Fix the fucked-up-ness that is this bullshit.
            # We need to be passing around more coherant data between methods of this class.
            
            # If listening on the IPV6 any address ('::' = IN6ADDR_ANY), activate dual-stack.
            if family == socket.AF_INET6 and addr[0] in ('::', '::0', '::0.0.0.0'):
                try:
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                
                except (AttributeError, socket.error):
                    pass

            sock.bind(addr)
            
            sock.settimeout(1)
            sock.listen(self.option.socket.queue)
            
            self.socket = sock
        
        def tick(self):
            """Accept a new connection and put it on the Queue."""
            
            try:
                s, addr = self.socket.accept()
                
                if not self.ready:
                    log.warning("Connection attempted from %r before server was ready.", addr)
                    return
                
                fixes.prevent_socket_inheritance(s)
                
                if hasattr(s, 'settimeout'):
                    s.settimeout(self.option.socket.timeout)
                
                # if self.response_header is None:
                #     self.response_header = "%s Server" % self.version
                
                #makefile = CP_fileobject
                #conn = self.ConnectionClass(self, s, makefile)
                conn = s
                
                # if not isinstance(self.server.bind, basestring):
                #     # optional values
                #     # Until we do DNS lookups, omit REMOTE_HOST
                #     if addr is None: # sometimes this can happen
                #         # figure out if AF_INET or AF_INET6.
                #         if len(s.getsockname()) == 2:
                #             # AF_INET
                #             addr = ('0.0.0.0', 0)
                #         else:
                #             # AF_INET6
                #             addr = ('::', 0)
                #     conn.remote_addr = addr[0]
                #     conn.remote_port = addr[1]
                
                self.pool.put(conn)
            
            except socket.timeout:
                # The only reason for the timeout in start() is so we can
                # notice keyboard interrupts on Win32, which don't interrupt
                # accept() by default
                return
            
            except socket.error, x:
                if x.args[0] in SOCKET_ERROR_EINTR:
                    return
                
                if x.args[0] in SOCKET_ERRORS_NONBLOCKING:
                    return
                
                if x.args[0] in SOCKET_ERRORS_TO_IGNORE:
                    return
                
                raise
    
    def url(self):
        if self.server.socket:
            return self.server.socket
        
        host, port = self.server.bind[0]
        
        return "%s://%s:%d" % (
                # "https" if self.option.ssl.certificate else "http",
                "http",
                IFACE_MAPPING.get(host, host),
                port
            )


if __name__ == '__main__':
    def helloworld(environ):
        return '200 OK', [('Content-Type', 'text/plain')], ["Hello world!\n"]
    
    server = HTTPServer('0.0.0.0', 8080, app=helloworld)
    server.start()