# encoding: utf-8

import cgi

from functools import partial

try:
    from cStringIO import StringIO

except ImportError:
    from cStringIO import StringIO

from marrow.server.protocol import Protocol


__all__ = ['HTTPProtocol', 'HTTPServer']
log = __import__('logging').getLogger(__name__)



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
            env['SERVER_PORT'] = server.address[1] if isinstance(server.address, tuple) else 80
            env['wsgi.input'] = None
            env['wsgi.errors'] = None
            env['wsgi.version'] = (2, 0)
            env['wsgi.multithread'] = False
            env['wsgi.multiprocess'] = False
            env['wsgi.run_once'] = False
            env['wsgi.url_scheme'] = 'http'
            
            self.environ = env
            
            self.finished = False
            self.pipeline = protocol.options.get('pipeline', True) # TODO
            
            client.read_until("\r\n\r\n", self.headers)
        
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
            
            line = data[:data.index('\r\n')].split()
            
            # TODO: Split the request path into parts.
            headers = dict(
                    REQUEST_METHOD=line[0],
                    SCRIPT_NAME="",
                    PATH_INFO=line[1].strip(),
                    QUERY_STRING="",
                    SERVER_NAME="",
                    SERVER_PORT="",
                    SERVER_PROTOCOL=line[2],
                    CONTENT_LENGTH=None
                )
            
            current = None
            noprefix = dict(CONTENT_TYPE=True, CONTENT_LENGTH=True)
            
            # This is lame.
            # WSGI is, I think, badly broken by re-processing the header names.
            # Conformance to CGI is not the pancea of compatability everyone imagined.
            for line in data.split('\r\n')[1:]:
                if not line: break
                assert current is not None or line[0] != ' ', "%r %r" % (current, line) # TODO: Do better than dying abruptly.
                
                if line[0] == ' ':
                    headers[current] += line.lstrip()
                    continue
                
                current, _, value = line.partition(':')
                current = current.replace('-', '_').upper()
                if current not in noprefix: current = 'HTTP_' + current
                headers[current] = value
            
            # Proxy support.
            # for h in ("X-Real-Ip", "X-Real-IP", "X-Forwarded-For"):
            #     self.remote_ip = self.headers.get(h, None)
            #     if self.remote_ip is not None:
            #         break
            
            self.environ.update(headers)
            
            if not headers['CONTENT_LENGTH']:
                self.work()
                return
            
            length = int(length)
            
            if length > self.client.max_buffer_size:
                raise Exception("Content-Length too long.")
            
            if headers.get("HTTP_EXPECT", None) == "100-continue":
                self.client.write("HTTP/1.1 100 (Continue)\r\n\r\n")
            
            self.client.read_bytes(length, self.body)
        
        def body(self, data):
            self.environ['wsgi.input'] = StringIO(data)
            
            self.work()
        
        def work(self):
            env = self.environ
            status, headers, body = self.protocol.application(env)
            
            self.write("%s %s\r\n%s\r\n\r\n" % (
                    env['SERVER_PROTOCOL'],
                    status,
                    "\r\n".join([': '.join((i, j)) for i, j in headers]),
                ), partial(self._write_body, iter(body)))
        
        def _write_body(self, body):
            try:
                chunk = body.next()
                self.write(chunk, partial(self._write_body, body))
            
            except StopIteration:
                self.finish()
        
        def _finish(self):
            env = self.environ
            disconnect = True
            
            if self.pipeline:
                if env['SERVER_PROTOCOL'] == 'HTTP/1.1':
                    disconnect = env.get('HTTP_CONNECTION', None) == "close"
                
                elif env['CONTENT_LENGTH'] is not None or env['REQUEST_METHOD'] in ('HEAD', 'GET'):
                    disconnect = env.get('HTTP_CONNECTION', None) != 'Keep-Alive'
            
            self.finished = False
            
            if disconnect:
                self.client.close()
                return
            
            self.client.read_until("\r\n\r\n", self.headers)
