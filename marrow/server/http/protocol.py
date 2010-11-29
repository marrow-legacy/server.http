# encoding: utf-8

from __future__ import unicode_literals

import sys
import cgi

from functools import partial

from marrow.server.protocol import Protocol

from marrow.util.compat import binary, unicode, IO


__all__ = ['HTTPProtocol', 'HTTPServer']
log = __import__('logging').getLogger(__name__)


CRLF = b"\r\n"
HTTP_INTERNAL_ERROR = b" 500 Internal Server Error\r\nContent-Type: text/plain\r\nContent-Length: 48\r\n\r\nThe server encountered an unrecoverable error.\r\n"




# TODO: Separate out into marrow.util.

class LoggingFile(object):
    def __init__(self, logger=None):
        self.logger = logger if logger else log.error
    
    def flush(self):
        pass # no-op
    
    def write(self, text):
        self.logger(text)
    
    def writelines(self, lines):
        for line in lines:
            self.logger(line)



class HTTPProtocol(Protocol):
    def __init__(self, server, application, ingress=None, egress=None, **options):
        super(HTTPProtocol, self).__init__(server, **options)
        
        self.application = application
        self.ingress = ingress if ingress else []
        self.egress = egress if egress else []
        
        if sys.version_info < (3, 0):
            self._name = server.name
            self._addr = server.address[0] if isinstance(server.address, tuple) else b''
            self._port = str(server.address[1]) if isinstance(server.address, tuple) else b'80'
        
        else:
            self._name = server.name.encode()
            self._addr = (server.address[0] if isinstance(server.address, tuple) else b'').encode()
            self._port = (str(server.address[1]) if isinstance(server.address, tuple) else b'80').encode()
    
    def accept(self, client):
        self.Connection(self.server, self, client)
    
    class Connection(object):
        def __init__(self, server, protocol, client):
            self.server = server
            self.protocol = protocol
            self.client = client
            
            env = dict()
            env['REMOTE_ADDR'] = client.address[0]
            env['SERVER_NAME'] = protocol._name
            env['SERVER_ADDR'] = protocol._addr
            env['SERVER_PORT'] = protocol._port
            
            env['wsgi.input'] = IO()
            env['wsgi.errors'] = LoggingFile()
            env['wsgi.version'] = (2, 0)
            env['wsgi.multithread'] = server.threaded
            env['wsgi.multiprocess'] = server.fork != 1
            env['wsgi.run_once'] = False
            env['wsgi.url_scheme'] = b'http'
            
            # env['wsgi.script_name'] = b''
            # env['wsgi.path_info'] = b''
            
            self.environ = None
            self.environ_template = env
            
            self.finished = False
            self.pipeline = protocol.options.get('pipeline', True) # TODO
            
            client.read_until(CRLF + CRLF, self.headers)
        
        def write(self, chunk, callback=None):
            assert not self.finished, "Attempt to write to completed request."
            
            if not self.client.closed():
                self.client.write(chunk, callback if callback else self.written)
        
        def written(self):
            if self.finished:
                self._finish()
        
        def finish(self):
            assert not self.finished, "Attempt complete an already completed request."
            
            self.finished = True
            
            if not self.client.writing():
                self._finish()
        
        def headers(self, data):
            """Process HTTP headers, and pull in the body as needed."""
            
            line = data[:data.index(CRLF)].split()
            remainder, _, fragment = line[1].partition(b'#')
            remainder, _, query = remainder.partition(b'?')
            path, _, param = remainder.partition(b';')
            
            self.environ = environ = dict(self.environ_template)
            
            environ['REQUEST_METHOD'] = line[0]
            environ['SCRIPT_NAME'] = b""
            environ['CONTENT_TYPE'] = None
            environ['PATH_INFO'] = path
            environ['PARAMETERS'] = param
            environ['QUERY_STRING'] = query
            environ['FRAGMENT'] = fragment
            environ['SERVER_PROTOCOL'] = line[2]
            environ['CONTENT_LENGTH'] = None
            
            log.warn("Here: %r", environ)
            
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
                current = unicode(header.replace(b'-', b'_'), 'ascii').upper()
                if current not in noprefix: current = 'HTTP_' + current
                environ[current] = value
            
            # Proxy support.
            # for h in ("X-Real-Ip", "X-Real-IP", "X-Forwarded-For"):
            #     self.remote_ip = self.engiron.get(h, None)
            #     if self.remote_ip is not None:
            #         break
            
            if environ.get("HTTP_EXPECT", None) == b"100-continue":
                self.client.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
            
            if environ['CONTENT_LENGTH'] is None:
                if environ.get('HTTP_TRANSFER_ENCODING', b'').lower() == b'chunked':
                    log.warn("HERE")
                    self.client.read_until(CRLF, self.body_chunked)
                    return
                
                self.work()
                return
            
            length = int(length)
            
            if length > self.client.max_buffer_size:
                raise Exception("Content-Length too long.")
            
            self.client.read_bytes(length, self.body)
        
        def body(self, data):
            self.environ['wsgi.input'] = IO(data)
            
            self.work()
        
        def body_chunked(self, data):
            length = data.strip(CRLF).split(';')[0]
            
            if length == b'0':
                self.client.read_until(CRLF, self.body_trailers)
                return
            
            self.client.read_bytes(int(length, 16) + 2, self.body_chunk)
        
        def body_chunk(self, data):
            self.environ['wsgi.input'].write(data[:-2])
            self.client.read_until(CRLF, self.body_chunked)
        
        def body_trailers(self, data):
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
                
                chunked = env['SERVER_PROTOCOL'] == b"HTTP/1.1" and 'content-length' not in [i[0].lower() for i in headers]
                if chunked:
                    headers.append((b"Transfer-Encoding", b"chunked"))
                    headers = env['SERVER_PROTOCOL'] + b" " + status + CRLF + CRLF.join([(i + b': ' + j) for i, j in headers]) + CRLF + CRLF
                    self.write(headers, partial(self._write_body_chunked, iter(body)))
                    return
                
                headers = env['SERVER_PROTOCOL'] + b" " + status + CRLF + CRLF.join([(i + b': ' + j) for i, j in headers]) + CRLF + CRLF
                
                self.write(headers, partial(self._write_body, iter(body)))
            
            except:
                log.exception("Unhandled application exception.")
                self.write(env['SERVER_PROTOCOL'] + HTTP_INTERNAL_ERROR, self.finish)
        
        def _write_body(self, body):
            try:
                chunk = next(body)
                self.write(chunk, partial(self._write_body, body))
            
            except StopIteration:
                self.finish()
        
        def _write_body_chunked(self, body):
            try:
                chunk = next(body)
                chunk = unicode(hex(len(chunk)))[2:].encode('ascii') + CRLF + chunk + CRLF
                self.write(chunk, partial(self._write_body_chunked, body))
            
            except StopIteration:
                self.write(b"0" + CRLF + CRLF, self.finish)
        
        def _finish(self):
            # TODO: Pre-calculate this and pass self.client.close as the body writer callback only if we need to disconnect.
            # TODO: Execute self.client.read_until in _write_body if we aren't disconnecting.
            # These are to support threading, where the body writer callback is executed in the main thread.
            env = self.environ
            disconnect = True
            
            if self.pipeline:
                if env['SERVER_PROTOCOL'] == 'HTTP/1.1':
                    disconnect = env.get('HTTP_CONNECTION', None) == b"close"
                
                elif env['CONTENT_LENGTH'] is not None or env['REQUEST_METHOD'] in (b'HEAD', b'GET'):
                    disconnect = env.get('HTTP_CONNECTION', None) != b'Keep-Alive'
            
            self.finished = False
            
            if disconnect:
                self.client.close()
                return
            
            self.client.read_until(CRLF + CRLF, self.headers)
