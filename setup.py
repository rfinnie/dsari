#!/usr/bin/env python

import os
from setuptools import setup
import dsari


def read(filename):
    return open(os.path.join(os.path.dirname(__file__), filename)).read()


setup(
    name='dsari',
    description='Do Something and Record It',
    long_description=read('README'),
    version=dsari.__version__,
    license='GPLv2+',
    platforms=['Unix'],
    author='Ryan Finnie',
    author_email='ryan@finnie.org',
    url='https://github.com/rfinnie/dsari',
    download_url='https://github.com/rfinnie/dsari/releases',
    packages=['dsari'],
    package_data={'dsari': ['templates/*.html']},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2 :: Only',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Software Development :: Testing',
    ],
    install_requires=[
        'croniter',
        'python-dateutil',
        'Jinja2>=2.4',
    ],
    entry_points={
        'console_scripts': [
            'dsari-daemon = dsari.daemon:main',
            'dsari-info = dsari.info:main',
            'dsari-render = dsari.render:main',
        ],
    },
)
