#!/usr/bin/env python
# encoding: utf-8

from __future__ import print_function

import os
import logging
import pkg_resources

from marrow.util.object import load_object

from marrow.script import script, annotate, describe, short

from marrow.server.http import HTTPServer
from marrow.server.http.release import version


__all__ = ['marrowhttpd']



@script(
        title = 'Marrow HTTP/1.1 Server',
        version = version,
        copyright = "Copyright 2010 Alice Bevan-McGregor\nThis is free software under the MIT license; see the source and accompanying LICENSE file for copying conditions. There is NO warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE."
    )
@describe(
        factory = "A callable which returns arguments for HTTPServer.",
        host = "The interface to bind to, defaults to all.\nE.g. 127.0.0.1",
        port = "The port number to bind to, defaults to 8080.",
        fork = "The number of processes to spawn. Defaults to 1. Set to zero to detect the number of logical processors.",
        verbose = "Increase logging level to DEBUG.",
        quiet = "Decrease logging level to WARN."
    )
def marrowhttpd(factory, host=None, port=8080, fork=1, verbose=False, quiet=False, **options):
    """Marrow HTTP/1.1 Server
    
    This script allows you to use a factory function to configure middleware, application settings, and filters.  Specify the dot-notation path (e.g. mypkg.myapp:factory) as the first positional argument.
    
    To demonstrate the server use "marrow.server.http.testing:hello" as the factory.  This factory accepts one argument, --name, allowing you to personalize the response.
    
    You can specify an unlimited number of --name=value arguments which will be passed to the factory.
    """
    
    if verbose and quiet:
        print("Can not set verbose and quiet simultaneously.")
        return 1
    
    try:
        factory = load_object(factory)
    
    except:
        print("Error loading factory: %s", factory)
        return 2
    
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARN if quiet else logging.INFO)
    
    HTTPServer(host, port, fork=fork, **factory(**options)).start()


def main():
    from marrow.script import execute
    execute(marrowhttpd)


if __name__ == '__main__':
    main()
