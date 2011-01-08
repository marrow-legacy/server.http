# encoding: utf-8

"""This file contains appliation test rigs for use in unit tests."""


from pprint import pformat
from marrow.util.compat import unicode


def prune(request, input=False):
    """A helper function to clean the request of un-testable variables."""
    del request['SERVER_NAME']
    del request['SERVER_PORT']
    del request['wsgi.errors']
    
    if not input:
        del request['wsgi.input']
    
    else:
        request['wsgi.input'] = request['wsgi.input'].read()
        
        if not request['wsgi.input']:
            del request['wsgi.input']


def generator(request):
    def inner():
        for i in range(10):
            yield str(i)
    
    return b"200 OK", [(b'Content-Length', b'10')], inner()


def die(request):
    1/0


def echo(chunked, request):
    prune(request, True)
    
    result = unicode(pformat(request)).encode('utf8')
    headers = [(b'Content-Type', b'text/plain; charset=utf8')]
    
    if not chunked:
        headers.append((b'Content-Length', unicode(len(result)).encode('ascii')))
    
    return b'200 OK', headers, (result.split(b"\n") if chunked else [result])


def body_echo(request):
    prune(request, True)
    
    if 'wsgi.input' not in request:
        request['wsgi.input'] = b""
    
    headers = [(b'Content-Type', b'text/plain; charset=utf8')]
    
    if 'HTTP_CONTENT_LENGTH' in request:
        headers.append((b'Content-Length', unicode(len(request['wsgi.input'])).encode('ascii')))
    
    return b'200 OK', headers, [request['wsgi.input']]
