# encoding: utf-8

import cgi

from functools import partial

try:
    from cStringIO import StringIO

except ImportError:
    from cStringIO import StringIO

from marrow.server.protocol import Protocol

from marrow.util.compat import binary, unicode


__all__ = ['HTTPProtocol', 'HTTPServer']
log = __import__('logging').getLogger(__name__)


HTTP_INTERNAL_ERROR = b" 500 Internal Server Error\r\nContent-Type: text/plain\r\nContent-Length: 48\r\n\r\nThe server encountered an unrecoverable error.\r\n"



# TODO: Separate out.

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
    def __init__(self, server, application, **options):
        super(HTTPProtocol, self).__init__(server, **options)
        
        self.application = application
    
    def accept(self, client):
        self.Connection(self.server, self, client)
    
    class Connection(object):
        def __init__(self, server, protocol, client):
            self.server = server
            self.protocol = protocol
            self.client = client
            
            env = dict()
            env['REMOTE_ADDR'] = client.address[0]
            env['SERVER_NAME'] = server.name
            env['SERVER_ADDR'] = server.address[0] if isinstance(server.address, tuple) else ''
            env['SERVER_PORT'] = server.address[1] if isinstance(server.address, tuple) else 80
            env['wsgi.input'] = None
            env['wsgi.errors'] = LoggingFile()
            env['wsgi.version'] = (2, 0)
            env['wsgi.multithread'] = False
            env['wsgi.multiprocess'] = server.fork != 1
            env['wsgi.run_once'] = False
            env['wsgi.url_scheme'] = b'http'
            
            self.environ = env
            
            self.finished = False
            self.pipeline = protocol.options.get('pipeline', True) # TODO
            
            client.read_until(b"\r\n\r\n", self.headers)
        
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
            
            line = data[:data.index(b'\r\n')].split()
            remainder, _, fragment = line[1].partition(b'#')
            remainder, _, query = remainder.partition(b'?')
            path, _, param = remainder.partition(b';')
            
            headers = dict()
            environ = dict(
                    REQUEST_METHOD=line[0],
                    SCRIPT_NAME=b"",
                    CONTENT_TYPE=b"",
                    PATH_INFO=path,
                    PARAMETERS=param,
                    QUERY_STRING=query,
                    FRAGMENT=fragment,
                    SERVER_PROTOCOL=line[2],
                    CONTENT_LENGTH=None,
                    HEADERS=headers
                )
            
            current, header = None, None
            noprefix = dict(CONTENT_TYPE=True, CONTENT_LENGTH=True)
            
            # This is lame.
            # WSGI is, I think, badly broken by re-processing the header names.
            # Conformance to CGI is not the pancea of compatability everyone imagined.
            for line in data.split(b'\r\n')[1:]:
                if not line: break
                assert current is not None or line[0] != b' ', "%r %r" % (current, line) # TODO: Do better than dying abruptly.
                
                if line[0] == b' ':
                    _ = line.lstrip()
                    environ[current] += _
                    # headers[header] += _
                    continue
                
                header, _, value = line.partition(b': ')
                current = unicode(header.replace(b'-', b'_')).upper()
                if current not in noprefix: current = 'HTTP_' + current
                environ[current] = value
                # headers[header] = value
            
            # Proxy support.
            # for h in ("X-Real-Ip", "X-Real-IP", "X-Forwarded-For"):
            #     self.remote_ip = self.engiron.get(h, None)
            #     if self.remote_ip is not None:
            #         break
            
            self.environ.update(environ)
            
            if not environ['CONTENT_LENGTH']:
                self.work()
                return
            
            length = int(length)
            
            if length > self.client.max_buffer_size:
                raise Exception("Content-Length too long.")
            
            if environ.get("HTTP_EXPECT", None) == b"100-continue":
                self.client.write(b"HTTP/1.1 100 (Continue)\r\n\r\n")
            
            self.client.read_bytes(length, self.body)
        
        def body(self, data):
            # TODO: Create a real file-like object.
            self.environ['wsgi.input'] = StringIO(data)
            
            self.work()
        
        def work(self):
            # TODO: expand with 'self.writer' callable to support threading efficiently.
            # Single-threaded we can write directly to the stream, multi-threaded we need to queue responses for the main thread to deliver.
            
            try:
                env = self.environ
                status, headers, body = self.protocol.application(env)
            
                self.write(env['SERVER_PROTOCOL'] + b" " + \
                        status + b"\r\n" + \
                        b"\r\n".join([': '.join((i, j)) for i, j in headers])
                    ), partial(self._write_body, iter(body)))
            
            except:
                log.exception("Unhandled application exception.")
                self.write(env['SERVER_PROTOCOL'] + HTTP_INTERNAL_ERROR, self.finish)
        
        def _write_body(self, body):
            # TODO: expand with 'self.writer' callable to support threading efficiently.
            # Single-threaded we can write directly to the stream, multi-threaded we need to queue responses for the main thread to deliver.
            
            try:
                chunk = body.next()
                self.write(chunk, partial(self._write_body, body))
            
            except StopIteration:
                self.finish()
        
        def _finish(self):
            # TODO: Pre-calculate this and pass self.client.close as the body writer callback only if we need to disconnect.
            # TODO: Execute self.client.read_until in _write_body if we aren't disconnecting.
            # These are to support threading, where the body writer callback is executed in the main thread.
            env = self.environ
            disconnect = True
            
            if self.pipeline:
                if env['SERVER_PROTOCOL'] == 'HTTP/1.1':
                    disconnect = env.get('HTTP_CONNECTION', None) == b"close"
                
                elif env['CONTENT_LENGTH'] is not None or env['REQUEST_METHOD'] in ('HEAD', 'GET'):
                    disconnect = env.get('HTTP_CONNECTION', None) != b'Keep-Alive'
            
            self.finished = False
            
            if disconnect:
                self.client.close()
                return
            
            self.client.read_until(b"\r\n\r\n", self.headers)
