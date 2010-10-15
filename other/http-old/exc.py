# encoding: utf-8


__all__ = ['MaxSizeExceeded']


class NoSSLError(Exception):
    """Exception raised when a client speaks HTTP to an HTTPS socket."""
    pass


class FatalSSLAlert(Exception):
    """Exception raised when the SSL implementation signals a fatal alert."""
    pass


class MaxSizeExceeded(Exception):
    pass
