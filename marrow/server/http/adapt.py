# encoding: utf-8

from functools import partial

from marrow.util.compat import binary, unicode, native, bytestring, uvalues, IO, formatdate, unquote

from marrow.server.http import release


__all__ = ['wsgi1']


def wsgi1(app):
    def inner(environ):
        def sr(status, headers):
            sr.status = status
            sr.headers = headers
        
        result = app(environ, sr)
        
        if not hasattr(sr, 'status'):
            raise Exception('start_response not called by WSGI application')
        
        return sr.status, sr.headers, result
    
    return inner
