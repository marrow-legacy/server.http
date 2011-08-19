# encoding: utf-8

"""Release information about Marrow HTTP Server."""

from collections import namedtuple


__all__ = ['version_info', 'version']


version_info = namedtuple('version_info', ('major', 'minor', 'micro', 'releaselevel', 'serial'))(0, 9, 0, 'final', 0)

version = ".".join([str(i) for i in version_info[:3]]) + ((version_info.releaselevel[0] + str(version_info.serial)) if version_info.releaselevel != 'final' else '')



# encoding: utf-8

"""Release information about Marrow."""


name = "marrow.server.http"
version = "0.9"
release = "0.9"

summary = "A powerful HTTP/1.1 server for WSGI 2 applications in both Python 2.x and 3.x."
description = """"""
author = "Alice Bevan-McGregor"
email = "alice@gothcandy.com"
url = "http://github.com/pulp/marrow.server.http"
download_url = "http://pypi.python.org/pypi/marrow.server.http/"
copyright = "2010, Alice Bevan-McGregor"
license = "MIT"
