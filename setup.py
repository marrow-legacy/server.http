#!/usr/bin/env python
# encoding: utf-8

import sys, os

try:
    from distribute_setup import use_setuptools
    use_setuptools()

except ImportError:
    pass

from setuptools import setup, find_packages, Extension


if sys.version_info <= (2, 5):
    raise SystemExit("Python 2.5 or later is required.")

if sys.version_info >= (3,0):
    def execfile(filename, globals_=None, locals_=None):
        if globals_ is None:
            globals_ = globals()
        
        if locals_ is None:
            locals_ = globals_
        
        exec(compile(open(filename).read(), filename, 'exec'), globals_, locals_)

else:
    from __builtin__ import execfile

execfile(os.path.join("marrow", "server", "http", "release.py"), globals(), locals())



setup(
        name = name,
        version = version,
        
        description = summary,
        long_description = description,
        author = author,
        author_email = email,
        url = url,
        download_url = download_url,
        license = license,
        keywords = '',
        
        install_requires = ['marrow.util', 'marrow.server'],
        
        test_suite = 'nose.collector',
        tests_require = ['nose', 'coverage', 'nose-achievements'],
        
        classifiers = [
                "Development Status :: 4 - Beta",
                "Environment :: Console",
                "Intended Audience :: Developers",
                "License :: OSI Approved :: MIT License",
                "Operating System :: OS Independent",
                "Programming Language :: Python",
                "Topic :: Software Development :: Libraries :: Python Modules",
                "Topic :: Internet :: WWW/HTTP :: HTTP Servers"
            ],
        
        packages = find_packages(exclude=['tests', 'tests.*', 'docs']),
        include_package_data = True,
        package_data = {
                '': ['Makefile', 'README.textile', 'LICENSE', 'distribute_setup.py'],
                'docs': ['source/*']
            },
        zip_safe = True,
        ext_modules = [
                Extension('marrow.server.http.parser.pyhttp11', [
                        'marrow/server/http/parser/pyhttp11.c',
                        'marrow/server/http/parser/http11_parser.c'
                    ])
            ],
        
        namespace_packages = ['marrow', 'marrow.server'],
        
        entry_points = {
                'marrow.server': ['http = marrow.server.http:HTTPServer']
            }
    )
