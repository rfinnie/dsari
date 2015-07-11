#!/usr/bin/env python

from distutils.core import setup

setup(
    name='dsari',
    description='Do Something and Record It',
    author='Ryan Finnie',
    author_email='ryan@finnie.org',
    url='https://github.com/rfinnie/dsari',
    packages=['dsari'],
    package_data={'dsari': ['templates/*.html']},
    scripts=['dsari-daemon', 'dsari-render'],
)

