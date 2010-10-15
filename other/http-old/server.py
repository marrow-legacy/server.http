# encoding: utf-8

import os
import socket

from marrow.util.bunch import Bunch
from marrow.server.pool import ThreadPool
from marrow.server.http import release
from marrow.server.http.const import SOCKET_ERRORS_TO_IGNORE

from fixes import prevent_socket_inheritance
from fwrappers import CP_fileobject
from http import HTTPConnection


log = __import__('logging').getLogger(__name__)



class Server(object):
    def __init__(self, bind, name=None, spawn=10, limit=None):
        self.callbacks = Bunch(start=[], stop=[])
        self.running = False
        self.sock = None
        self.nodelay = True
        
        self.bind = bind
        self.name = name if name else socket.gethostname()
        self.pool = ThreadPool(self, min=spawn or 1, max=limit)
        
        super(Server, self).__init__()
    
    def _set_bind(self, value):
        if isinstance(value, tuple) and value[0] == '':
            value = (None, value[1])

        self._bind_address = value
    
    bind = property(lambda self: self._bind_address, _set_bind)
    
    def start(self):
        raise NotImplementedError()
    
    def stop(self):
        raise NotImplementedError()
    


class HTTPServer(Server):
    protocol = "HTTP/1.1"
    version = "MarrowHTTP/" + release.version
    
    response_header = None
    max_request_header_size = 0
    max_request_body_size = 0
    
    ConnectionClass = HTTPConnection
    
    _bind_address = None
    _interrupt = None

    wsgi_version = (2, 0)
    
    def _set_interrupt(self, interrupt):
        if interrupt is None:
            self._interrupt = None
            return
        
        self._interrupt = True
        self.stop()
        self._interrupt = interrupt
    
    interrupt = property(lambda self: self._interrupt, _set_interrupt)
    
    def __init__(self, app, bind, name=None, spawn=10, limit=None, queuesz=5, timeout=10, shutdown_timeout=5):
        self.app = app

        super(HTTPServer, self).__init__(bind, name, spawn, limit)

        self.queuesz = queuesz
        self.timeout = timeout
        self.shutdown_timeout = shutdown_timeout
    
    def bindto(self, family, type, proto=0):
        self.socket = socket.socket(family, type, proto)
        
        prevent_socket_inheritance(self.socket)
        
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if self.nodelay and not isinstance(self.bind, str):
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        if family == socket.AF_INET6 and self.bind[0] in ('::', '::0', '::0.0.0.0'):
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            
            except (AttributeError, socket.error):
                pass
        
        self.socket.bind(self.bind)
    
    def start(self):
        log.debug("Starting up.")
        
        self.interrupt = None
        
        connections = []
        
        log.debug("Determining socket to bind to.")
        
        if isinstance(self.bind, basestring): # AF_UNIX
            try:
                os.unlink(self.bind)
                os.chmod(self.bind, 0777)
            
            except:
                pass
            
            connections.append((socket.AF_UNIX, socket.SOCK_STREAM, 0, "", self.bind))
        
        else: # AF_INET or AF_INET6
            host, port = self.bind
            
            try:
                connections.extend(socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, 0, socket.AI_PASSIVE))
            
            except socket.gaierror:
                if ':' in self.bind[0]:
                    connections.append((socket.AF_INET6, socket.SOCK_STREAM, 0, "", self.bind + (0, 0)))
                
                else:
                    connections.append((socket.AF_INET, socket.SOCK_STREAM, 0, "", self.bind))
        
        self.sock = None
        
        log.debug("Binding socket.")
        
        for af, socktype, proto, canonname, sa in connections:
            try:
                self.bindto(af, socktype, proto)
            
            except socket.error, msg:
                if self.socket:
                    self.socket.close()
                
                self.socket = None
                continue
            
            break
        
        if not self.socket:
            log.error("Unable to bind to socket.")
            raise socket.error("No socket could be created")
        
        self.socket.settimeout(1)
        self.socket.listen(self.queuesz)
        
        log.debug("Starting thread pool.")
        
        self.pool.start()
        self.running = True
        
        log.debug("Processing startup callbacks.")
        
        for callback in self.callbacks.start:
            if callback(self):
                self.stop()
                return
        
        log.info("Server running.")
        
        while self.running:
            self.tick()
            
            if self.interrupt:
                while self.interrupt is True:
                    time.sleep(0.1)
                
                if self.interrupt:
                    raise self.interrupt
    
    def tick(self):
        try:
            s, addr = self.socket.accept()
            
            if not self.running:
                s.close()
                return
            
            prevent_socket_inheritance(s)
            
            try: s.settimeout(self.timeout)
            except AttributeError: pass
            
            if self.response_header is None:
                self.response_header = "%s Server" % self.version
            
            makefile = CP_fileobject
            
            conn = self.ConnectionClass(self, s, makefile)
            
            if not isinstance(self.bind, basestring):
                # optional values
                # Until we do DNS lookups, omit REMOTE_HOST
                if addr is None: # sometimes this can happen
                    # figure out if AF_INET or AF_INET6.
                    if len(s.getsockname()) == 2:
                        # AF_INET
                        addr = ('0.0.0.0', 0)
                    else:
                        # AF_INET6
                        addr = ('::', 0)
                conn.remote = addr
            
            self.pool.put(conn)
        
        except socket.timeout:
            return
        
        except socket.error, x:
            if x.args[0] in SOCKET_ERROR_EINTR:
                # I *think* this is right. EINTR should occur when a signal
                # is received during the accept() call; all docs say retry
                # the call, and I *think* I'm reading it right that Python
                # will then go ahead and poll for and handle the signal
                # elsewhere. See http://www.cherrypy.org/ticket/707.
                return
            if x.args[0] in SOCKET_ERRORS_NONBLOCKING:
                # Just try again. See http://www.cherrypy.org/ticket/479.
                return
            if x.args[0] in SOCKET_ERRORS_TO_IGNORE:
                # Our socket was closed.
                # See http://www.cherrypy.org/ticket/686.
                return
            raise
    
    def stop(self):
        log.info("Shutting down.")
        
        self.running = False
        
        if self.sock:
            log.debug("Attempting to force socket closed.")
            if not isinstance(self.bind, basestring):
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
            
            try:
                log.debug("Closing socket.")
                sock.close()
            
            except AttributeError:
                pass
            
            self.sock = None
        
        log.debug("Shutting down thread pool.")
        
        self.pool.stop(self.shutdown_timeout)
        
        log.debug("Processing startup callbacks.")
        
        for callback in self.callbacks.stop:
            callback(self)
        
        log.info("Bye!")
    

    def get_environ(self, req):
        """Return a new environ dict targeting the given wsgi.version"""
        
        env_10 = {
                'PATH_INFO': req.path,
                'QUERY_STRING': req.query,
                'REMOTE_ADDR': req.connection.remote[0] or '',
                'REMOTE_PORT': str(req.connection.remote[1] or ''),
                'REQUEST_METHOD': req.method,
                'REQUEST_URI': req.uri,
                'SCRIPT_NAME': '',
                'SERVER_NAME': req.server.name,
                'SERVER_PROTOCOL': req.protocol[1],
                'SERVER_SOFTWARE': "%s WSGI Server" % req.server.version,
                'SERVER_PORT': "" if isinstance(req.server.bind, basestring) else str(req.server.bind[1]),

                'wsgi.version': (2, 0),
                'wsgi.server': self,
                'wsgi.request': req
            }
        
        # CONTENT_TYPE/CONTENT_LENGTH
        for k, v in req.headers.iteritems():
            env_10["HTTP_" + k.upper().replace("-", "_")] = v

        ct = env_10.pop("HTTP_CONTENT_TYPE", None)
        if ct is not None:
            env_10["CONTENT_TYPE"] = ct

        cl = env_10.pop("HTTP_CONTENT_LENGTH", None)
        if cl is not None:
            env_10["CONTENT_LENGTH"] = cl

        env = env_10
        #env = dict([(k.decode('ISO-8859-1'), v) for k, v in env_10.iteritems()])

        # Request-URI
        #env.setdefault(u'wsgi.url_encoding', u'utf-8')
        #try:
        #    for key in [u"PATH_INFO", u"SCRIPT_NAME", u"QUERY_STRING"]:
        #        env[key] = env_10[str(key)].decode(env[u'wsgi.url_encoding'])
        #except UnicodeDecodeError:
        #    # Fall back to latin 1 so apps can transcode if needed.
        #    env[u'wsgi.url_encoding'] = u'ISO-8859-1'
        #    for key in [u"PATH_INFO", u"SCRIPT_NAME", u"QUERY_STRING"]:
        #        env[key] = env_10[str(key)].decode(env[u'wsgi.url_encoding'])

        #for k, v in sorted(env.items()):
        #    if isinstance(v, str) and k not in ('REQUEST_URI', 'wsgi.input'):
        #        env[k] = v.decode('ISO-8859-1')

        return env

    def respond(self, req):
        status, headers, response = req.server.app(self.get_environ(req))

        req.status = status

        for k, v in headers:
            if not isinstance(k, str):
                raise TypeError("WSGI response header key %r is not a byte string." % k)
            if not isinstance(v, str):
                raise TypeError("WSGI response header value %r is not a byte string." % v)

        req.outheaders.extend(headers)

        req.sent_headers = True
        req.send_headers()

        try:
            for chunk in response:
                if chunk:
                    if isinstance(chunk, unicode):
                        chunk = chunk.encode('ISO-8859-1')
                    req.write(chunk)
        finally:
            if hasattr(response, "close"):
                response.close()


