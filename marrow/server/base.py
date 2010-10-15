# encoding: utf-8

"""Core socket management."""

import select
import socket


from Queue import Queue, Empty
from threading import Event, Thread
from collections import defaultdict, deque
from inspect import isclass

from marrow.server.pool import ThreadPool

from pulp.util.bunch import Bunch


__all__ = []
log = __import__('logging').getLogger(__name__)



class Server(object):
    """A basic threaded TCP socket server.
    
    The protocol class attriubte should be overridden in subclasses or instances to provide actual functionality.
    """
    
    protocol = None
    
    clients = []
    responses = Queue()
    
    callbacks = Bunch({'startup': [], 'shutdown': []})
    
    def __init__(self, host, port=None, pool=500, minimum=5, maximum=100, divisor=10, timeout=60, *args, **kw):
        """Accept the minimal server configuration.
        
        If port is omitted, the host is assumed to be an on-disk UNIX domain socket file.
        
        The protocol is instantiated here, if it is a class, and passed a reference to the server and any additional arguments.
        """
        
        super(Server, self).__init__()
        
        self.socket = None
        self.address = (host if host is not None else '', port)
        self.pool = pool
        self.running = False
        self.finished = Event()
        
        if isclass(self.protocol):
            self.protocol = self.protocol(self, *args, **kw)
        
        self.worker = ThreadPool(lambda request: self.protocol.process(*request), minimum=minimum, maximum=maximum, divisor=divisor, timeout=timeout)
        self._responder = Thread(target=self.responder, name="responder")
    
    def __call__(self, block=True):
        """Primary reactor loop.
        
        This handles standard signals as interpreted by Python, such as Ctrl+C.
        """
        
        if self.running:
            raise Exception("Already running.")
        
        try:
            log.info("Starting up.")
            
            self.socket = self._socket()
            self.socket.settimeout(1)
            self.socket.bind(self.address)
            self.socket.listen(self.pool)
            
            self._responder.start()
            
            self.running = True
            
            log.debug("Executing startup callbacks.")
            
            self.protocol.start(self)
            
            for callback in self.callbacks.startup:
                callback(self)
            
            log.info("Running.")
            
            self.listening()
        
        except KeyboardInterrupt:
            log.info("Recieved Control+C.")
        
        except SystemExit:
            log.info("Recieved SystemExit.")
            raise
        
        except:
            log.exception("Unknown server error.")
            raise
        
        finally:
            self.stop()
    
    def wait(self, timeout=None):
        self.finished.wait(timeout)
    
    def _socket(self):
        """Create a listening socket.
        
        This handles IPv6 and allows socket re-use by spawned processes.
        
        TCP_NODELAY should be set on client sockets as needed by the protocol.
        """
        
        host, port = self.address
        
        try:
            addr, family, kind, protocol, name, sa = ((host, port), ) + socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE)[0]
        
        except socket.gaierror:
            if ':' in host:
                addr, family, kind, protocol, name, sa = ((host, port), socket.AF_INET6, socket.SOCK_STREAM, 0, "", (host, port, 0, 0))
            
            else:
                addr, family, kind, protocol, name, sa = ((host, port), socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, port))
        
        sock = socket.socket(family, kind, protocol)
        # fixes.prevent_socket_inheritance(sock)
        
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # If listening on the IPV6 any address ('::' = IN6ADDR_ANY), activate dual-stack.
        if family == socket.AF_INET6 and addr[0] in ('::', '::0', '::0.0.0.0'):
            try:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            
            except (AttributeError, socket.error):
                pass
        
        return sock
    
    
    def listening(self):
        """Override this to implement asynchronous sockets, etc."""
        
        self_socket = [self.socket]
        
        while self.running:
            all_sockets = self_socket + self.clients
            rlist, wlist, xlist = select.select(all_sockets, [], all_sockets, 10.0)
            
            if self.finished.isSet():
                for client in all_sockets:
                    client.shutdown(2)
                    client.close()
                
                break
            
            if not rlist and not wlist and not xlist:
                # Quickly loop to allow for shutdown via another thread.
                continue
            
            assert self.socket not in xlist, "Listening socket returned with extended status!"
            
            if self.socket in rlist:
                rlist.remove(self.socket)
                
                client, address = self.socket.accept()
                
                if not self.protocol.connected(self, client, address):
                    self.clients.append(client)
                
                else:
                    client.shutdown(2)
                    client.close()
            
            for client in rlist:
                try:
                    self.protocol.readable(self, client)
                
                except:
                    log.exception("Protocol error.")
                    client.shutdown(2)
                    client.close()
                    raise
            
            for client in wlist:
                self.protocol.writeable(self, client)
                
                if not server.responses[client]:
                    del server.responses[client]
            
            for client in xlist:
                log.warning("Socket %r in extended select list.", client)
    
    def responder(self):
        try:
            while True:
                try:
                    client, response = self.responses.get(True, 10)
                    
                    if self.finished.isSet():
                        log.debug("Responder death by external request, %d unsent responses.", self.responses.qsize())
                        self.responses.task_done()
                        break
                    
                    self.protocol.writeable(self, client, response)
                    self.responses.task_done()
                
                except Empty:
                    if self.finished.isSet():
                        log.debug("Worker death by external request.")
                        break
        
        except:
            log.exception("Internal error in responder thread.")
    
    def stop(self):
        if not self.running:
            return
        
        log.info("Shutting down.")
        
        self.running = False
        self.finished.set()
        
        if not self.socket:
            return
        
        try:
            self.socket.close()
        
        except:
            log.exception("Error stopping the listening socket.")
        
        log.debug("Waiting for responder to finish.")
        self.responses.put(None)
        self._responder.join()
        
        log.debug("Stopping worker thread pool.")
        self.worker.stop()
        
        log.debug("Executing shutdown callbacks.")
        
        for callback in self.callbacks.shutdown:
            callback(self)
        
        log.info("Stopped.")


if __name__ == '__main__':
    import logging
    
    logging.basicConfig(level=logging.DEBUG)
    
    from marrow.server.api import IProtocol
    
    class EchoProtocol(IProtocol):
        def connected(self, server, client, address):
            log.debug("Connection from %r -- %r.", client, address)
        
        def readable(self, server, client):
            log.debug("Client %r readable.", client)
            server.worker((server, client, client.recv(10)))
        
        def writeable(self, server, client, response):
            log.debug("Client %r writeable.", client)
            client.sendall(response)
        
        def process(self, server, client, request):
            log.debug("Processing request from %r: %r", client, request)
            server.responses.put((client, request))
    
    class MyServer(Server):
        protocol = EchoProtocol
    
    server = MyServer(None, 8000)
    server()
