# encoding: utf-8

import logging
import inspect
import time

from functools import partial

from marrow.server.protocol import Protocol

from marrow.util.bunch import Bunch
from marrow.util.object import LoggingFile
from marrow.util.compat import binary, unicode, native, bytestring, uvalues, IO, formatdate, unquote

from marrow.server.http import release


__all__ = ['HTTPProtocol']
log = logging.getLogger(__name__)


CRLF = b"\r\n"
dCRLF = b"\r\n\r\n"
HTTP_INTERNAL_ERROR = b" 500 Internal Server Error\r\nContent-Type: text/plain\r\nContent-Length: 48\r\n\r\nThe server encountered an unrecoverable error.\r\n"
VERSION_STRING = b'marrow.httpd/' + release.release.encode('iso-8859-1')
nCRLF = native(CRLF)
NO_HTTP_PREFIX = dict(CONTENT_TYPE=True, CONTENT_LENGTH=True)
errorlog = LoggingFile(logging.getLogger('wsgi.errors'))

STATE = Bunch(
        startup = 1, # Preparing the initial (static) environment.
        request = 2, # Waiting for request headers.
        response = 3, # Waiting for response status and headers.
        body = 4, # Accepting bytestring body chunks.
        dead = 5 # Something happened to kill this connection.
    )


class Request(object):
    def __init__(self, server, protocol, client):
        self.state = STATE.startup
        self.server = server
        self.protocol = protocol
        self.stream = client
        self.head = False
        
        self.environ = None
        env = self.template = dict()
        
        env['REMOTE_ADDR'] = client.address[0]
        env['SERVER_NAME'] = protocol._name
        env['SERVER_ADDR'] = protocol._addr
        env['SERVER_PORT'] = protocol._port
        env['SCRIPT_NAME'] = unicode()
        env['CONTENT_TYPE'] = None
        env['CONTENT_LENGTH'] = None
        
        env['wsgi.input'] = IO()
        env['wsgi.errors'] = errorlog
        env['wsgi.version'] = (2, 0)
        env['wsgi.multithread'] = bool(server.threaded)
        env['wsgi.multiprocess'] = server.fork != 1
        env['wsgi.run_once'] = False
        env['wsgi.url_scheme'] = 'http'
        env['wsgi.async'] = False # TODO
        
        if server.threaded is not False:
            env['wsgi.submit'] = server.executor.submit
        
        self.pipeline = protocol.pipeline


class HTTPProtocol(Protocol):
    def __init__(self, server, testing, application, pipeline=True, ingress=None, egress=None, encoding="utf8", **options):
        super(HTTPProtocol, self).__init__(server, testing, **options)
        
        assert inspect.isgeneratorfunction(application), "Application must be a generator function."
        
        self.application = application
        self.ingress = ingress if ingress else []
        self.egress = egress if egress else []
        self.encoding = encoding
        self.pipeline = pipeline
        
        self._name = server.name
        self._addr = server.address[0] if isinstance(server.address, tuple) else ''
        self._port = str(server.address[1]) if isinstance(server.address, tuple) else '80'
    
    def accept(self, client):
        # This gets passed around to all of the callbacks.
        request = Request(self.server, self, client)
        request.state = STATE.request
        client.read_until(dCRLF, partial(self.headers, request))
    
    def headers(self, request, data):
        """Process HTTP headers.
        
        Defer the body until requested, and consume post-request to be safe.
        """
        # TODO: Proxy support.
        
        # log.debug("Received: %r", data)
        
        # Duplicate the template WSGI environment and split data into lines.
        
        request.environ = environ = dict(request.template)
        line, lines = data[:data.index(CRLF)], native(data).split(nCRLF)
        
        # Parse the HTTP "Request-Line": http://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1
        
        line = [part.strip() for part in line.split()]
        environ['REQUEST_METHOD'] = native(line[0])
        uri = environ['REQUEST_URI'] = line[1]
        environ['SERVER_PROTOCOL'] = native(line[2])
        del line
        
        assert environ['SERVER_PROTOCOL'] in ('HTTP/1.0', 'HTTP/1.1'), "Unknown protocol version."
        
        # Split apart the "Request-URI": http://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1.2
        
        remainder, _, environ['FRAGMENT'] = uri.rpartition(b'#')
        remainder, _, environ['QUERY_STRING'] = remainder.rpartition(b'?')
        path, _, environ['PARAMETERS'] = remainder.rpartition(b';')
        
        if b"://" in path:
            scheme, _, path = path.partition(b'://')
            host, _, path = path.partition(b'/')
            path = _ + path # add the leading slash back
            
            environ['wsgi.url_scheme'] = native(scheme)
            environ['HTTP_HOST'] = native(host)
        
        # This breaks backwards compatibility; PATH_INFO in CGI is messed up.
        environ['PATH_INFO'] = path # Previously: unquote()'d
        
        # Lie to protect the innocent: http://blog.dscpl.com.au/2009/10/wsgi-issues-with-http-head-requests.html
        
        if environ['REQUEST_METHOD'] == 'HEAD':
            environ['REQUEST_METHOD'] = 'GET'
            request.head = True
        
        # Ensure specific values are Unicode.
        
        _ = ('PATH_INFO', 'PARAMETERS', 'QUERY_STRING', 'FRAGMENT')
        environ['wsgi.uri_encoding'], __ = uvalues([environ[i] for i in _], self.encoding)
        environ.update(zip(_, __))
        del _, __
        
        # Process the HTTP headers: http://www.w3.org/Protocols/rfc2616/rfc2616-sec4.html#sec4.2
        
        current, header = None, None
        
        for line in lines[1:]:
            if not line: break
            assert current is not None or line[0] != ' '
            
            # This unfolds header values: http://tools.ietf.org/html/rfc822#section-3.1
            if line[0] == ' ':
                environ[current] += ' ' + line.lstrip()
                continue
            
            current, _, value = line.partition(':')
            current = current.replace('-', '_').upper()
            if current not in NO_HTTP_PREFIX: current = 'HTTP_' + current
            environ[current] = value.strip()
        
        del current, header, line, lines
        
        # Now that we have a complete environment, call the application.
        
        # A misnomer, but only when starting up.
        request.state = STATE.response
        
        self.resume(request, self.application(environ))
    
    def resume(self, request, generator, data=None):
        try:
            while True:
                try:
                    data = generator.send(data)
                except (StopIteration, GeneratorExit):
                    raise
                except:
                    log.exception("Error resuming application.")
                    raise
                
                if data is None:
                    # Co-operative multi-tasing: re-schedule.  Because we can.
                    request.server.io.add_callback(partial(self.resume, request, generator))
                
                elif isinstance(data, int):
                    # UNIX timestamp-based rescheduling.  Because we can.
                    request.server.io.add_timeout(data, partial(self.resume, request, generator))
                
                elif isinstance(data, tuple):
                    # We have headers.
                    assert request.state == STATE.response, "Application returned unexpected response headers."
                    request.state = STATE.body
                    
                    self.response(request, generator, *data)
                    return
                
                elif isinstance(data, binary):
                    # We have a body chunk.
                    assert request.state == STATE.body
                    if request.head: continue
                    request.writer(request, generator, data)
                    return
                
                elif hasattr(data, 'add_done_callback'):
                    # We have a callback to prepare.
                    data.add_done_callback(partial(self.resume, request, generator))
                    return
                
                else:
                    log.warning("Unknown data returned by application.")
                    assert False, "Unknown data returned by application."
        
        except (StopIteration, GeneratorExit):
            self.finish(request)
            return
        
        except:
            self.finish(request, False)
            raise
    
    def response(self, request, generator, status, headers):
        """Write the response status and headers to the client."""
        
        # TODO: Filtering is disabled in this branch.
        # for filter_ in self.protocol.egress:
        #     status, headers, body = filter_(env, status, headers, body)
        
        # Canonicalize the names of the headers returned by the application.
        present = [i[0].lower() for i in headers]
        
        assert isinstance(status, binary), "Response status must be a bytestring."
        
        for i, j in headers:
            assert isinstance(i, binary), "Response header names must be bytestrings."
            assert isinstance(j, binary), "Response header values must be bytestrings."
        
        assert b'transfer-encoding' not in present, "Applications must not set the Transfer-Encoding header."
        assert b'connection' not in present, "Applications must not set the Connection header."
        
        if b'server' not in present:
            headers.append((b'Server', VERSION_STRING))
        
        if b'date' not in present:
            headers.append((b'Date', bytestring(formatdate(time.time(), False, True))))
        
        request.writer = self.write
        
        # Determine if we can pipeline.
        
        env = request.environ
        
        if request.pipeline:
            if env['SERVER_PROTOCOL'] == 'HTTP/1.1':
                request.pipeline = env.get('HTTP_CONNECTION', None) != "close"
            
            elif env['CONTENT_LENGTH'] is not None or env['REQUEST_METHOD'] in ('HEAD', 'GET'):
                request.pipeline = env.get('HTTP_CONNECTION', '').lower() == 'keep-alive' and b'content-length' in present
                if request.pipeline:
                    headers.append((b'Connection', b'keep-alive'))
        
        # Determine if we need to chunkify the response.
        
        if env['SERVER_PROTOCOL'] == "HTTP/1.1" and b'content-length' not in present:
            request.writer = self.write_chunk
            headers.append((b"Transfer-Encoding", b"chunked"))
            headers = env['SERVER_PROTOCOL'].encode('iso-8859-1') + b" " + status + CRLF + CRLF.join([(i + b': ' + j) for i, j in headers]) + dCRLF
        
        else:
            headers = env['SERVER_PROTOCOL'].encode('iso-8859-1') + b" " + status + CRLF + CRLF.join([(i + b': ' + j) for i, j in headers]) + dCRLF
        
        request.stream.write(headers, partial(self.resume, request, generator))
    
    def write(self, request, generator, chunk):
        request.stream.write(chunk, partial(self.resume, request, generator))
    
    def write_chunk(self, request, generator, chunk):
        chunk = bytestring(hex(len(chunk))[2:]) + CRLF + chunk + CRLF
        request.stream.write(chunk, partial(self.resume, request, generator))
    
    def finish(self, request, success=True):
        request.state = STATE.request
        request.environ = None
        
        if not request.pipeline or not success:
            request.state = STATE.dead
            request.stream.close()
            return
        
        request.stream.read_until(dCRLF, partial(self.headers, request))
