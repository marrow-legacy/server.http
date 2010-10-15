# encoding: utf-8


__all__ = ['headers_dict', 'DELIMETED_HEADERS']

log = __import__('logging').getLogger(__name__)



DELIMETED_HEADERS = [i.lower() for i in [
        'Accept',
        'Accept-Charset',
        'Accept-Encoding',
        'Accept-Language',
        'Accept-Ranges',
        'Allow',
        'Cache-Control',
        'Connection',
        'Content-Encoding',
        'Content-Language',
        'Expect',
        'If-Match',
        'If-None-Match',
        'Pragma',
        'Proxy-Authenticate',
        'TE',
        'Trailer',
        'Transfer-Encoding',
        'Upgrade',
        'Vary',
        'Via',
        'Warning',
        'WWW-Authenticate'
    ]]


def headers_dict(stream, headers=None):
    """Read headers from the given stream into the given header dict.
    
    If hdict is None, a new header dict is created. Returns the populated
    header dict.
    
    Headers which are repeated are folded together using a comma if their
    specification so dictates.
    
    This function raises ValueError when the read bytes violate the HTTP spec.
    You should probably return "400 Bad Request" if this happens.
    """
    
    readline = stream.readline
    if headers is None: headers = {}
    
    while True:
        line = readline()
        
        if not line: raise ValueError()
        if line == "\r\n": break
        
        # Is array slicing faster?
        if not line[-2:] == "\r\n": raise ValueError()
        
        if line[0] in ' \t':
            line = line.strip()
            
            if k not in DELIMETED_HEADERS:
                headers[k] = line
                continue
            
            existing = headers.get(k)
            
            if existing:
                headers[k] = existing + ', ' + line
                continue

        k, _, v = line.partition(":")
        
        k = k.strip().lower()
        v = v.strip()
        
        if k in DELIMETED_HEADERS:
            existing = headers.get(k)
            
            if existing:
                headers[k] = existing + ", " + v
                continue
        
        headers[k] = v
    
    return headers
