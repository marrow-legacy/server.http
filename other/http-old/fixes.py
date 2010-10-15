# encoding: utf-8

import sys
import socket


__all__ = ['prevent_socket_inheritance', '_fileobject_uses_str_type']


if 'win' in sys.platform and not hasattr(socket, 'IPPROTO_IPV6'):
    socket.IPPROTO_IPV6 = 41


try:
    import fcntl

except ImportError:
    try:
        from ctypes import windll, WinError
    
    except ImportError:
        def prevent_socket_inheritance(sock):
            """Dummy function, since neither fcntl nor ctypes are available."""
            pass
    
    else:
        def prevent_socket_inheritance(sock):
            """Mark the given socket fd as non-inheritable (Windows)."""
            if not windll.kernel32.SetHandleInformation(sock.fileno(), 1, 0):
                raise WinError()

else:
    def prevent_socket_inheritance(sock):
        """Mark the given socket fd as non-inheritable (POSIX)."""
        fd = sock.fileno()
        old_flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        fcntl.fcntl(fd, fcntl.F_SETFD, old_flags | fcntl.FD_CLOEXEC)


_fileobject_uses_str_type = isinstance(socket._fileobject(None)._rbuf, basestring)
