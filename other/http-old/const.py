# encoding: utf-8

import re
import errno
import socket


__all__ = [
        'CRLF',
        'IFACE_MAPPING',
        'QUOTED_SLASH', 'SFO_STR',
        'SOCKET_ERROR_EINTR', 'SOCKET_ERRORS_TO_IGNORE', 'SOCKET_ERRORS_NONBLOCKING'
    ]



CRLF = "\r\n"
IFACE_MAPPING = {'0.0.0.0': '127.0.0.1', '::': '::1', '::0': '::1', '::0.0.0.0': '::1'}
QUOTED_SLASH = re.compile("(?i)%2F")

SFO_STR = isinstance(socket._fileobject(None)._rbuf, basestring)


def _platform_specific_errors(*errors):
    """Return a set of potentially platform-specific error values."""
    values = set([getattr(errno, k, None) for k in errors])
    values.discard(None)
    return values

SOCKET_ERROR_EINTR = _platform_specific_errors("EINTR", "WSAEINTR")
SOCKET_ERRORS_TO_IGNORE = _platform_specific_errors("EPIPE", "EBADF", "WSAEBADF", "ENOTSOCK", "WSAENOTSOCK", "ETIMEDOUT", "WSAETIMEDOUT", "ECONNREFUSED", "WSAECONNREFUSED", "ECONNRESET", "WSAECONNRESET", "ECONNABORTED", "WSAECONNABORTED", "ENETRESET", "WSAENETRESET", "EHOSTDOWN", "EHOSTUNREACH")
SOCKET_ERRORS_TO_IGNORE.add("timed out")
SOCKET_ERRORS_TO_IGNORE.add("The read operation timed out")
SOCKET_ERRORS_NONBLOCKING = _platform_specific_errors('EAGAIN', 'EWOULDBLOCK', 'WSAEWOULDBLOCK')
