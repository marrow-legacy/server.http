# encoding: utf-8

from pprint import pprint

from functools import partial

from marrow.util.compat import binary, unicode, native, bytestring, uvalues, IO, formatdate, unquote

from marrow.server.http import release


__all__ = ['wsgi1']
log = __import__('logging').getLogger(__name__)


def adapter_generator(ingress, egress):
    def adapter(app):
        def inner(environ):
            def sr(status, headers, exc_info=None):
                sr.status = status
                sr.headers = headers
                sr.exc = exc_info
            
            environ = ingress(environ)
            result = app(environ, sr)
            status, headers, result = egress(sr.status, sr.headers, result)
            
            if not hasattr(sr, 'status'):
                raise Exception('start_response not called by WSGI application')
            
            return status, headers, result
        
        return inner
    
    return adapter


def filter_pep333_ingress(environ):
    for i in ('FRAGMENT', 'PARAMETERS', 'PATH_INFO', 'QUERY_STRING', 'SCRIPT_NAME'):
        environ[i] = native(environ[i])
    
    if environ.get('CONTENT_TYPE', None) is None:
        del environ['CONTENT_TYPE']
    
    return environ


def filter_pep333_egress(status, headers, result):
    headers_ = []
    
    for i, j in headers:
        if isinstance(i, unicode):
            i = i.encode('iso8859-1')
        
        if isinstance(j, unicode):
            j = j.encode('iso8859-1')
        
        headers_.append((i, j))
    
    return status, headers_, result


def filter_pep3333_ingress(environ):
    return environ


def filter_pep3333_egress(status, headers, result):
    return status, headers, result


wsgi1 = adapter_generator(filter_pep333_ingress, filter_pep333_egress)
wsgi2 = adapter_generator(filter_pep3333_ingress, filter_pep3333_egress)
