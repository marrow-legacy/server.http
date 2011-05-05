#!/usr/bin/env python
import sys
import os

from distribute_setup import use_setuptools
use_setuptools()

from setuptools import setup, find_packages


if sys.version_info <= (2, 6):
    raise SystemExit("Python 2.6 or later is required.")

exec(open(os.path.join("marrow", "server", "http", "release.py")))

setup(
    name=name,
    version=version,
    description=summary,
    long_description=description,
    author=author,
    author_email=email,
    url=url,
    download_url=download_url,
    license=license,
    keywords='',

    install_requires=[
        'marrow.util < 2.0',
        'marrow.server < 2.0'
    ],
    extras_require={'script': ['marrow.script >= 1.1']},

    test_suite='nose.collector',
    tests_require=['nose', 'coverage'],

    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.1",
        "Programming Language :: Python :: 3.2",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
    ],

    packages=find_packages(exclude=['tests', 'tests.*', 'docs']),
    include_package_data=True,
    package_data={
        '': ['Makefile', 'README.textile', 'LICENSE', 'distribute_setup.py'],
        'docs': ['source/*']
    },
    zip_safe=True,
    namespace_packages=['marrow', 'marrow.server'],

    entry_points={
        'console_scripts': [ 'marrow.httpd = marrow.server.http.command:main [script]' ],
        'marrow.server': ['http = marrow.server.http:HTTPServer']
    }
)
