# encoding: utf-8

import socket
import rfc822

from urllib import unquote

from const import CRLF
from exc import MaxSizeExceeded
from fwrappers import CP_fileobject, SizeCheckWrapper, KnownLengthRFile

from marrow.util.compat import exception

from marrow.server.common import headers_dict
from marrow.server.http.const import SOCKET_ERRORS_TO_IGNORE


log = __import__('logging').getLogger(__name__)


class HTTPRequest(object):
    def __init__(self, server, connection):
        self.server = server
        self.connection = connection
        
        self.running = False
        self.processing = False
        
        self.scheme = "http"
        self.response = 'HTTP/1.0'
        
        self.headers = {}
        self.outheaders = []
        
        self.close_connection = False
        self.chunked_write = False
        self.sent_headers = False
    
    def parse(self):
        """Parse the next HTTP request start-line and message-headers."""
        self.rfile = SizeCheckWrapper(self.connection.rfile, self.server.max_request_header_size)
        
        try:
            line = self.rfile.readline()

            # Generate 408 errors from here on out.
            self.processing = True

            if not line:
                self.running = False
                return

            if line == CRLF:
                line = self.rfile.readline()
                if not line:
                    self.running = False
                    return

            if not line[-2:] == CRLF:
                self.simple_response("400 Bad Request", "HTTP requires CRLF line terminators.")
                return

            try:
                self.method, uri, protocol = line.strip().split(" ")
                self.uri = uri

            except ValueError:
                log.exception("Malformed request.")
                self.simple_response("400 Bad Request", "Malformed request.")
                return

            scheme, _, remainder = uri.partition("://")

            if not remainder:
                remainder = scheme
                scheme = None

            authority, _, path = uri.partition('/')
            path, _s, self.query = path.partition('?')

            if scheme: self.scheme = scheme

            if not path:
                path = authority
                authority = None

            if '#' in path:
                self.simple_response("400 Bad Request", "Illegal hash fragment in the requested URI.")
                return

            path.replace("%2F", "\0").replace("%2f", "\0")
            path = unquote(path)
            path.replace("\0", "%2F")

            self.path = path

            rp = int(protocol[5]), int(protocol[7])
            sp = int(self.server.protocol[5]), int(self.server.protocol[7])

            if sp[0] != rp[0]:
                self.simple_response("505 HTTP Version Not Supported")
                return

            self.protocol = (protocol, "HTTP/%s.%s" % min(rp, sp))
        
        except MaxSizeExceeded:
            log.exception("Request URI too long.")
            self.simple_response("414 Request-URI Too Long", "The Request-URI sent with the request exceeds the maximum allowed bytes.")
            return
        
        try:
            self.read_request_headers()
        
        except MaxSizeExceeded:
            log.exception("Request entity too large.")
            self.simple_response("413 Request Entity Too Large", "The headers sent with the request exceed the maximum allowed bytes.")
            return
        
        self.running = True
    
    def read_request_headers(self):
        try:
            headers = headers_dict(self.rfile, self.headers)
        
        except ValueError:
            log.exception("Bad request.")
            self.simple_response("400 Bad Request") #, ex.args[0])
            return
        
        self.chunked = False
        protocol = self.protocol[1]
        mrbs = self.server.max_request_body_size
        
        if mrbs and int(headers.get("Content-Length", 0)) > mrbs:
            raise MaxSizeExceeded()
        
        # Persistent connection support.
        if protocol == "HTTP/1.1":
            # Both server and client are HTTP/1.1
            if self.headers.get("Connection", "") == "close":
                self.close_connection = True
        
        else:
            # Either the server or client (or both) are HTTP/1.0
            if self.headers.get("Connection", "") != "Keep-Alive":
                self.close_connection = True
        
        # Transfer-Encoding support.
        te = []
        if protocol == "HTTP/1.1":
            _ = headers.get("Transfer-Encoding")
            
            if te:
                for i in te.split(","):
                    v = i.strip()
                    if v: te.append(v.lower())
        
        if te:
            for enc in te:
                if enc == "chunked":
                    self.chunked = True
                
                else:
                    # Note that, even if we see "chunked", we must reject
                    # if there is an extension we don't recognize.
                    self.simple_response("501 Unimplemented")
                    self.close_connection = True
                    return
        
        if headers.get("Expect", "") == "100-continue":
            # Don't use simple_response here, because it emits headers
            # we don't want. See http://www.cherrypy.org/ticket/951
            msg = self.server.protocol + " 100 Continue\r\n\r\n"
            try:
                self.connection.wfile.sendall(msg)
            except socket.error, x:
                if x.args[0] not in SOCKET_ERRORS_TO_IGNORE:
                    log.exception("Socket error.")
                    raise
    
    def respond(self):
        """Call the gateway and write its iterable output."""
        mrbs = self.server.max_request_body_size
        if self.chunked:
            self.rfile = ChunkedRFile(self.connection.rfile, mrbs)
        else:
            cl = int(self.headers.get("Content-Length", 0))
            if mrbs and mrbs < cl:
                if not self.sent_headers:
                    self.simple_response("413 Request Entity Too Large",
                        "The entity sent with the request exceeds the maximum "
                        "allowed bytes.")
                return
            self.rfile = KnownLengthRFile(self.connection.rfile, cl)
        
        self.server.respond(self)
        
        if self.running and not self.sent_headers:
            self.sent_headers = True
            self.send_headers()
        
        if self.chunked_write:
            self.connection.wfile.sendall("0\r\n\r\n")
    
    def simple_response(self, status, msg=""):
        """Write a simple response back to the client."""
        status = str(status)
        buf = ["Content-Length: %s\r\n" % len(msg),
               "Content-Type: text/plain\r\n"]
        
        if status[:3] in ("413", "414"):
            # Request Entity Too Large / Request-URI Too Long
            self.close_connection = True
            if self.protocol[1] == 'HTTP/1.1':
                # This will not be true for 414, since read_request_line
                # usually raises 414 before reading the whole line, and we
                # therefore cannot know the proper response_protocol.
                buf.append("Connection: close\r\n")
            else:
                # HTTP/1.0 had no 413/414 status nor Connection header.
                # Emit 400 instead and trust the message body is enough.
                status = "400 Bad Request"
        
        buf.append(CRLF)
        if msg:
            if isinstance(msg, unicode):
                msg = msg.encode("ISO-8859-1")
            buf.append(msg)
        
        status_line = self.server.protocol + " " + status + CRLF
        try:
            self.connection.wfile.sendall(status_line + "".join(buf))
        except socket.error, x:
            if x.args[0] not in SOCKET_ERRORS_TO_IGNORE:
                log.exception("Socket error.")
                raise
    
    def write(self, chunk):
        """Write unbuffered data to the client."""
        if self.chunked_write and chunk:
            buf = [hex(len(chunk))[2:], CRLF, chunk, CRLF]
            self.connection.wfile.sendall("".join(buf))
        else:
            self.connection.wfile.sendall(chunk)
    
    def send_headers(self):
        """Assert, process, and send the HTTP response message-headers.
        
        You must set self.status, and self.outheaders before calling this.
        """
        hkeys = [key.lower() for key, value in self.outheaders]
        status = int(self.status[:3])
        
        if status == 413:
            # Request Entity Too Large. Close conn to avoid garbage.
            self.close_connection = True
        elif "content-length" not in hkeys:
            # "All 1xx (informational), 204 (no content),
            # and 304 (not modified) responses MUST NOT
            # include a message-body." So no point chunking.
            if status < 200 or status in (204, 205, 304):
                pass
            else:
                if (self.protocol[1] == 'HTTP/1.1'
                    and self.method != 'HEAD'):
                    # Use the chunked transfer-coding
                    self.chunked_write = True
                    self.outheaders.append(("Transfer-Encoding", "chunked"))
                else:
                    # Closing the conn is the only way to determine len.
                    self.close_connection = True
        
        if "connection" not in hkeys:
            if self.protocol[1] == 'HTTP/1.1':
                # Both server and client are HTTP/1.1 or better
                if self.close_connection:
                    self.outheaders.append(("Connection", "close"))
            else:
                # Server and/or client are HTTP/1.0
                if not self.close_connection:
                    self.outheaders.append(("Connection", "Keep-Alive"))
        
        if (not self.close_connection) and (not self.chunked):
            # Read any remaining request body data on the socket.
            # "If an origin server receives a request that does not include an
            # Expect request-header field with the "100-continue" expectation,
            # the request includes a request body, and the server responds
            # with a final status code before reading the entire request body
            # from the transport connection, then the server SHOULD NOT close
            # the transport connection until it has read the entire request,
            # or until the client closes the connection. Otherwise, the client
            # might not reliably receive the response message. However, this
            # requirement is not be construed as preventing a server from
            # defending itself against denial-of-service attacks, or from
            # badly broken client implementations."
            remaining = getattr(self.rfile, 'remaining', 0)
            if remaining > 0:
                self.rfile.read(remaining)
        
        if "date" not in hkeys:
            self.outheaders.append(("Date", rfc822.formatdate()))
        
        if "server" not in hkeys:
            self.outheaders.append(("Server", self.server.name))
        
        buf = [self.server.protocol + " " + self.status + CRLF]
        for k, v in self.outheaders:
            buf.append(k + ": " + v + CRLF)
        buf.append(CRLF)
        self.connection.wfile.sendall("".join(buf))


class HTTPConnection(object):
    """An HTTP connection (active socket).
    
    server: the Server object which received this connection.
    socket: the raw socket object (usually TCP) for this connection.
    makefile: a fileobject class for reading from the socket.
    """
    
    remote = (None, None)
    
    rbufsize = -1
    RequestHandlerClass = HTTPRequest
    
    def __init__(self, server, sock, makefile=CP_fileobject):
        self.server = server
        self.socket = sock
        self.rfile = makefile(sock, "rb", self.rbufsize)
        self.wfile = makefile(sock, "wb", -1)
    
    def communicate(self):
        """Read each request and respond appropriately."""
        request_seen = False
        try:
            while True:
                # (re)set req to None so that if something goes wrong in
                # the RequestHandlerClass constructor, the error doesn't
                # get written to the previous request.
                req = None
                req = self.RequestHandlerClass(self.server, self)
                
                # This order of operations should guarantee correct pipelining.
                req.parse()
                if not req.running:
                    # Something went wrong in the parsing (and the server has
                    # probably already made a simple_response). Return and
                    # let the conn close.
                    return
                
                request_seen = True
                req.respond()
                if req.close_connection:
                    return
        except socket.error, e:
            errnum = e.args[0]
            if errnum == 'timed out':
                # Don't error if we're between requests; only error
                # if 1) no request has been started at all, or 2) we're
                # in the middle of a request.
                # See http://www.cherrypy.org/ticket/853
                if (not request_seen) or (req and req.processing):
                    # Don't bother writing the 408 if the response
                    # has already started being written.
                    if req and not req.sent_headers:
                        req.simple_response("408 Request Timeout")
            elif errnum not in SOCKET_ERRORS_TO_IGNORE:
                log.exception("Socket error.")
                if req and not req.sent_headers:
                    req.simple_response("500 Internal Server Error", exception().formatted)
            return
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            log.exception("Unexpected exception.")
            if req and not req.sent_headers:
                req.simple_response("500 Internal Server Error", exception().formatted)
    
    linger = False
    
    def close(self):
        """Close the socket underlying this connection."""
        self.rfile.close()
        
        if not self.linger:
            # Python's socket module does NOT call close on the kernel socket
            # when you call socket.close(). We do so manually here because we
            # want this server to send a FIN TCP segment immediately. Note this
            # must be called *before* calling socket.close(), because the latter
            # drops its reference to the kernel socket.
            if hasattr(self.socket, '_sock'):
                self.socket._sock.close()
            self.socket.close()
        else:
            # On the other hand, sometimes we want to hang around for a bit
            # to make sure the client has a chance to read our entire
            # response. Skipping the close() calls here delays the FIN
            # packet until the socket object is garbage-collected later.
            # Someday, perhaps, we'll do the full lingering_close that
            # Apache does, but not today.
            pass
