# encoding: utf-8

import socket


class CP_fileobject(socket._fileobject):
    """Faux file object attached to a socket object."""

    def sendall(self, data):
        """Sendall for non-blocking sockets."""
        while data:
            try:
                bytes_sent = self.send(data)
                data = data[bytes_sent:]
            except socket.error, e:
                if e.args[0] not in socket_errors_nonblocking:
                    raise

    def send(self, data):
        return self._sock.send(data)
