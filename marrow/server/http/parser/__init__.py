# encoding: utf-8

"""HTTP 1.1 header/body parser, producing a WSGI-compatible environment.

This module (and sub-modules) are copyright their respective authors:

    2005, Zed A. Shaw (Mongrel, http://github.com/fauna/mongrel/blob/master/LICENSE)
    2009, Donovan Preston

Originally found at http://github.com/fzzzy/pyhttp11 without licensing information.
Modified to conform to the WSGI specification.
"""

from marrow.server.http.parser.pyhttp11 import HTTPParser


__all__ = ['HTTPParser']
