"""Adapt an HTTP server."""

import os
import time
import threading
import itertools
import socket

from marrow.util.compat import exception
from marrow.util.bunch import Bunch

from marrow.server.http.const import IFACE_MAPPING


__all__ = ['Server']

log = __import__('logging').getLogger(__name__)



class Server(object):
    """A basic web server API."""
    
    timeout = 15
    Protocol = None
    
    def __init__(self, host=None, port=None, socket=None, wait=True, **kw):
        if not self.Protocol:
            raise Exception("You can not create Server instances without an associated protocol.")
        
        if isinstance(host, tuple): host, port = host
        
        if not socket: self.socket = []
        else: self.socket = socket if isinstance(socket, list) else [socket]
        
        if not host and not port: self.bind = []
        else: self.bind = [bind for bind in itertools.izip(
                host if isinstance(host, list) else [host],
                port if isinstance(port, list) else [port]
            )]
        
        self.exc = None
        self._wait = wait
        self.running = False
        self.callback = Bunch(start=[], stop=[], restart=[])
        
        self.protocol = self.Protocol(self, **kw)
    
    def start(self, callbacks=True):
        """Start the HTTP server."""
        
        log.info("Starting up.")
        
        if not self.bind and not self.socket:
            raise Exception("You must define either an on-disk socket and/or host/port to bind to.")
        
        if self.running:
            raise Exception("Already running.", self.running)
        
        if not self._wait and not self.available:
            raise Exception("Unable to bind socket: socket unavailable.", self.bind, self.socket)
        
        elif self._wait: self.wait()
        
        log.debug("Creating master thread.")
        
        thread = threading.Thread(target=self.thread)
        thread.setName(self.__class__.__name__ + " " + thread.getName())
        thread.start()
        
        log.debug("Waiting for master thread to bind.")
        
        self.wait(True)
        self.running = True
        
        if callbacks:
            log.debug("Notifying registered callbacks.")
            
            for callback in self.callback.start:
                callback(self)
        
        if self.bind:
            log.info("Server ready: %s", self.url)
        
        else: log.info("Server ready.")
    
    def stop(self, callbacks=True):
        if not self.running:
            log.error("Server is not running.")
        
        if callbacks:
            log.debug("Notifying registered callbacks.")
            
            for callback in self.callback.stop:
                callback(self)
        
        log.info("Shutting down.")
        
        self.protocol.stop()
        self.wait()
        self.running = False
    
    def restart(self):
        """Restart the HTTP server."""
        self.stop(False)
        
        log.debug("Notifying registered callbacks.")
        
        for callback in self.callback.restart:
            callback(self)
        
        self.start(False)
    
    def thread(self):
        """Process system events and notifications."""
        
        # TODO: Provide a threading switch to detect graceful shutdown.
        
        try:
            self.protocol.start()
            self.protocol.main()
        
        except KeyboardInterrupt:
            log.info("Recieved Control+C.")
            self.exc = exception()
        
        except SystemExit:
            log.info("Recieved SystemExit.")
            self.exc = exception()
            raise
        
        except:
            log.exception("Unknown server error.")
            self.exc = exception()
            raise
        
        finally:
            self.protocol.stop()            
    
    def url(self):
        return self.protocol.url()
    
    def wait(self, ready=False):
        """Wait until either a port is available, or occupied."""
        timeout = range(self.timeout * 10)
        
        if not ready:
            if self.bind:
                for attempt in timeout:
                    if self.available: break
                    time.sleep(0.1)
                
                if not self.available:
                    raise Exception("Unable to bind socket: socket unavailable.", self.bind, self.socket)
            
            return
        
        while not self.protocol.ready:
            if self.exc: raise self.exc.exception
            time.sleep(0.1)
        
        if self.bind:
            # Try for roughly 15 seconds.
            for attempt in timeout:
                if not self.available: break
                time.sleep(0.1)
            
            if self.available:
                raise Exception("Unknown error binding socket: never became responsive.")
    
    @property
    def available(self):
        def test(host, port, timeout=1.0):
            host = IFACE_MAPPING.get(host, host)

            try:
                connections = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            
            except socket.gaierror:
                if ':' in host:
                    connections = [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (host, port, 0, 0))]
                
                else:
                    connections = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, port))]
            
            for family, kind, protocol, name, sa in connections:
                sock = None
                
                try:
                    sock = socket.socket(family, kind, protocol)
                    sock.settimeout(timeout)
                    sock.connect((host, port))
                    sock.close()
                    
                    return False
                
                except socket.error:
                    if sock: sock.close()
            
            return True
        
        possibilities = [test(host, port) for host, port in self.bind]
        possibilities.extend([os.access(filename, os.W_OK) for filename in self.socket])
        
        return all(possibilities)
