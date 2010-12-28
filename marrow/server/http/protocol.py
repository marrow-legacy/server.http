# encoding: utf-8

import logging
import sys
import cgi

import time
from functools import partial
from inspect import getouterframes, currentframe

from marrow.server.protocol import Protocol
from marrow.server.http import release

from marrow.util.compat import binary, unicode, IO

try:
    from email.utils import formatdate

except ImportError:
    from rfc822 import formatdate


__all__ = ['HTTPProtocol', 'HTTPServer']
log = logging.getLogger(__name__)


CRLF = b"\r\n"
dCRLF = b"\r\n\r\n"
HTTP_INTERNAL_ERROR = b" 500 Internal Server Error\r\nContent-Type: text/plain\r\nContent-Length: 48\r\n\r\nThe server encountered an unrecoverable error.\r\n"
__versionstring__ = b'marrow.httpd/' + release.release



# TODO: Separate out into marrow.util.
try:
    range = xrange

except:
    pass


# TODO: Separate out into marrow.util.
def bytestring(s, encoding="iso-8859-1", fallback="iso-8859-1"):
    if not isinstance(s, unicode):
        fname, line = getouterframes(currentframe())[1][1:3]
        log.warn("Value is already byte string.\n%s:%d", fname, line)
        return s
    
    try:
        s.encode(encoding)
    
    except UnicodeDecodeError:
        s.encode(fallback)


# TODO: Separate out into marrow.util.
def native(s, encoding="iso-8859-1", fallback="iso-8859-1"):
    if isinstance(s, str):
        fname, line = getouterframes(currentframe())[1][1:3]
        log.warn("Value is already native string.\n%s:%d", fname, line)
        return s
    
    try:
        return s.encode(encoding)
    
    except:
        return s.encode(fallback)


# TODO: Separate out into marrow.util.
class LoggingFile(object): # pragma: no cover
    def __init__(self, logger=None, level=logging.ERROR):
        logger = logger if logger else logging.getLogger('wsgi.errors')
        self.logger = partial(logger.log, level)
    
    def write(self, text):
        self.logger(text)
    
    def writelines(self, lines):
        for line in lines:
            self.logger(line)
    
    def close(self, *args, **kw): 
        """A no-op method used for several of the file-like object methods."""
        pass
    
    def next(self, *args, **kw):
        """An error-raising exception usedbfor several of the methods."""
        raise IOError("Logging files can not be read.")
    
    flush = close
    read = next
    readline = next
    readlines = next

errorlog = LoggingFile()


class HTTPProtocol(Protocol):
    def __init__(self, server, testing, application, ingress=None, egress=None, pedantic=True, **options):
        super(HTTPProtocol, self).__init__(server, testing, **options)
        
        self.application = application
        self.ingress = ingress if ingress else []
        self.egress = egress if egress else []
        self.pedantic = pedantic
        
        self._name = native(server.name)
        self._addr = native(server.address[0]) if isinstance(server.address, tuple) else ''
        self._port = str(server.address[1]) if isinstance(server.address, tuple) else '80'
    
    def accept(self, client):
        self.Connection(self.server, self, client)
    
    class Connection(object):
        def __init__(self, server, protocol, client):
            self.server = server
            self.protocol = protocol
            self.client = client
            
            env = dict()
            env['REMOTE_ADDR'] = native(client.address[0])
            env['SERVER_NAME'] = native(protocol._name)
            env['SERVER_ADDR'] = native(protocol._addr)
            env['SERVER_PORT'] = native(protocol._port)
            
            env['wsgi.input'] = IO()
            env['wsgi.errors'] = errorlog
            env['wsgi.version'] = (2, 0)
            env['wsgi.multithread'] = getattr(server, 'threaded', False) # TODO: Temporary hack until marrow.server 1.0 release.
            env['wsgi.multiprocess'] = server.fork != 1
            env['wsgi.run_once'] = False
            env['wsgi.url_scheme'] = 'http' # TODO: Remove unicode_literals.
            
            # env['wsgi.script_name'] = b''
            # env['wsgi.path_info'] = b''
            
            self.environ = None
            self.environ_template = env
            
            self.finished = False
            self.pipeline = protocol.options.get('pipeline', True) # TODO
            
            client.read_until(dCRLF, self.headers)
        
        def write(self, chunk, callback=None):
            assert not self.finished, "Attempt to write to completed request."
            
            if not self.client.closed():
                self.client.write(chunk, callback)
        
        def finish(self):
            assert not self.finished, "Attempt complete an already completed request."
            
            self.finished = True
            
            if not self.client.writing():
                self._finish()
        
        def headers(self, data):
            """Process HTTP headers, and pull in the body as needed."""
            
            # log.debug("Recieved: %r", data)
            
            line = data[:data.index(CRLF)].split()
            remainder, _, fragment = line[1].partition(b'#')
            remainder, _, query = remainder.partition(b'?')
            path, _, param = remainder.partition(b';')
            
            self.environ = environ = dict(self.environ_template)
            
            if b"://" in path:
                scheme, _, path = path.partition(b'://')
                host, _, path = path.partition(b'/')
                path = b'/' + path
                
                environ['wsgi.url_scheme'] = scheme
                environ['HTTP_HOST'] = host
            
            # TODO: REQUEST_URI, bytestring.
            environ['REQUEST_METHOD'] = line[0]
            environ['CONTENT_TYPE'] = None
            environ['FRAGMENT'] = fragment
            environ['SERVER_PROTOCOL'] = line[2]
            environ['CONTENT_LENGTH'] = None
            
            # SCRIPT_NAME, PATH_INFO, PARAMETERS, and QUERY_STRING, unicode -- wsgi.uri_encoding UTF8 fallback iso-8859-1.
            environ['SCRIPT_NAME'] = b""
            environ['PATH_INFO'] = path # urldecode
            environ['PARAMETERS'] = param # urldecode
            environ['QUERY_STRING'] = query.decode('iso-8859-1')
            
            current, header = None, None
            noprefix = dict(CONTENT_TYPE=True, CONTENT_LENGTH=True)
            
            for line in data.split(CRLF)[1:]:
                if not line: break
                assert current is not None or line[0] != b' ' # TODO: Do better than dying abruptly.
                
                if line[0] == b' ':
                    _ = line.lstrip()
                    environ[current] += _
                    continue
                
                header, _, value = line.partition(b': ')
                current = native(header.replace(b'-', b'_')).upper() # TODO: Unroll the native() logic here.
                if current not in noprefix: current = 'HTTP_' + current
                environ[current] = value
            
            # TODO: Proxy support.
            # for h in ("X-Real-Ip", "X-Real-IP", "X-Forwarded-For"):
            #     self.remote_ip = self.engiron.get(h, None)
            #     if self.remote_ip is not None:
            #         break
            
            if environ.get("HTTP_EXPECT", None) == b"100-continue":
                self.client.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
            
            if environ['CONTENT_LENGTH'] is None:
                if environ.get('HTTP_TRANSFER_ENCODING', b'').lower() == b'chunked':
                    self.client.read_until(CRLF, self.body_chunked)
                    return
                
                self.work()
                return
            
            length = int(environ['CONTENT_LENGTH'])
            
            if length > self.client.max_buffer_size:
                # TODO: Return appropriate HTTP response in addition to logging the error.
                raise Exception("Content-Length too long.")
            
            self.client.read_bytes(length, self.body)
        
        def body(self, data):
            # log.debug("Recieved body: %r", data)
            self.environ['wsgi.input'] = IO(data)
            self.work()
        
        def body_chunked(self, data):
            # log.debug("Recieved chunk header: %r", data)
            length = int(data.strip(CRLF).split(b';')[0], 16)
            # log.debug("Chunk length: %r", length)
            
            if length == 0:
                self.client.read_until(CRLF, self.body_trailers)
                return
            
            self.client.read_bytes(length + 2, self.body_chunk)
        
        def body_chunk(self, data):
            # log.debug("Recieved chunk: %r", data)
            self.environ['wsgi.input'].write(data[:-2])
            self.client.read_until(CRLF, self.body_chunked)
        
        def body_trailers(self, data):
            # log.debug("Recieved chunk trailers: %r", data)
            self.environ['wsgi.input'].seek(0)
            # TODO: Update headers with additional headers.
            self.work()
        
        def work(self):
            # TODO: expand with 'self.writer' callable to support threading efficiently.
            # Single-threaded we can write directly to the stream, multi-threaded we need to queue responses for the main thread to deliver.
            
            try:
                env = self.environ
                
                for filter_ in self.protocol.ingress:
                    filter_(env)
                
                status, headers, body = self.protocol.application(env)
                
                for filter_ in self.protocol.egress:
                    status, headers, body = filter_(env, status, headers, body)
                
                # These conversions are optional; if the application is well-behaved they can be disabled.
                # Of course, if pedantic is False, m.s.http isn't WSGI 2 compliant. (But it is faster!)
                if self.protocol.pedantic:
                    # Convert from unicode (native or otherwise) to bytestring.
                    if isinstance(status, unicode):
                        status = status.encode('iso-8859-1')
                
                    # Do likewise for the header values.
                    # Interesting note, in timeit timings, this is about 2x faster than re-creating the list: 
                    # Good headers: (all bytestrings)
                    # List creation and iteration: 4.53897809982
                    # List iteration and substitution: 3.99575710297
                    # Mixed headers: (half bytestrings)
                    # List creation and iteration: 7.10801100731
                    # List iteration and substitution: 3.94248199463
                    # Bad headers: (all unicode)
                    # List creation and iteration: 8.7310090065
                    # List iteration and substitution: 4.10248017311
                    # TODO: Remove above note at some point.
                    for i in range(len(headers)):
                        name, value = i
                    
                        if not isinstance(name, unicode) and not isinstance(value, unicode):
                            continue
                    
                        if isinstance(name, unicode):
                            name = name.encode('iso-8859-1')
                    
                        if isinstance(value, unicode):
                            value = value.encode('iso-8859-1')
                    
                        i = (name, value)
                
                # Canonicalize the names of the headers returned by the application.
                present = [i[0].lower() for i in headers]
                
                # Further optional conformance checks.
                if self.protocol.pedantic:
                    if b'transfer-encoding' in present: raise Exception()
                    if b'connection' in present: raise Exception()
                
                if b'server' not in present:
                    headers.append((b'Server', __versionstring__))
                
                if b'date' not in present:
                    headers.append((b'Date', unicode(formatdate(time.time(), False, True)).encode('ascii')))
                
                # TODO: Ensure hop-by-hop and persistence headers are not returned.
                
                if env['SERVER_PROTOCOL'] == b"HTTP/1.1" and b'content-length' not in present:
                    headers.append((b"Transfer-Encoding", b"chunked"))
                    headers = env['SERVER_PROTOCOL'] + b" " + status + CRLF + CRLF.join([(i + b': ' + j) for i, j in headers]) + dCRLF
                    self.write(headers, partial(self.write_body_chunked_pedantic if self.protocol.pedantic else self.write_body_chunked, body, iter(body)))
                    return
                
                headers = env['SERVER_PROTOCOL'] + b" " + status + CRLF + CRLF.join([(i + b': ' + j) for i, j in headers]) + dCRLF
                
                self.write(headers, partial(self.write_body_pedantic if self.protocol.pedantic else self.write_body, body, iter(body)))
            
            except:
                log.exception("Unhandled application exception.")
                self.write(env['SERVER_PROTOCOL'] + HTTP_INTERNAL_ERROR, self.finish)
        
        def write_body_pedantic(self, original, body):
            try:
                chunk = bytestring(next(body))
                self.write(chunk, partial(self.write_body_pedantic, original, body))
            
            except StopIteration:
                self.finish()
            
            finally:
                try:
                    original.close()
                except AttributeError:
                    pass
        
        def write_body(self, original, body):
            try:
                chunk = next(body)
                self.write(chunk, partial(self.write_body, original, body))
            
            except StopIteration:
                self.finish()
            
            finally:
                try:
                    original.close()
                except AttributeError:
                    pass
        
        def write_body_chunked_pedantic(self, original, body):
            try:
                chunk = bytestring(next(body))
                chunk = unicode(hex(len(chunk)))[2:].encode('ascii') + CRLF + chunk + CRLF
                self.write(chunk, partial(self.write_body_chunked_pedantic, original, body))
            
            except StopIteration:
                try:
                    original.close()
                except AttributeError:
                    pass
                
                self.write(b"0" + dCRLF, self.finish)
        
        def write_body_chunked(self, original, body):
            try:
                chunk = next(body)
                chunk = unicode(hex(len(chunk)))[2:].encode('ascii') + CRLF + chunk + CRLF
                self.write(chunk, partial(self.write_body_chunked, original, body))
            
            except StopIteration:
                try:
                    original.close()
                except AttributeError:
                    pass
                
                self.write(b"0" + dCRLF, self.finish)
        
        def _finish(self):
            # TODO: Pre-calculate this and pass self.client.close as the body writer callback only if we need to disconnect.
            # TODO: Execute self.client.read_until in write_body if we aren't disconnecting.
            # These are to support threading, where the body writer callback is executed in the main thread.
            env = self.environ
            disconnect = True
            
            if self.pipeline:
                if env['SERVER_PROTOCOL'] == b'HTTP/1.1':
                    disconnect = env.get('HTTP_CONNECTION', None) == b"close"
                
                elif env['CONTENT_LENGTH'] is not None or env['REQUEST_METHOD'] in (b'HEAD', b'GET'):
                    disconnect = env.get('HTTP_CONNECTION', b'').lower() != b'keep-alive'
            
            self.finished = False
            
            # log.debug("Disconnect client? %r", disconnect)
            
            if disconnect:
                self.client.close()
                return
            
            self.client.read_until(dCRLF, self.headers)
