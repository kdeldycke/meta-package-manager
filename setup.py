#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Kevin Deldycke <kevin@deldycke.com>
#                    and contributors.
# All Rights Reserved.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import codecs
import os
import re

from setuptools import find_packages, setup

MODULE_NAME = 'meta_package_manager'
PACKAGE_NAME = MODULE_NAME.replace('_', '-')

DEPENDENCIES = [
    'click >= 5.0',
    'click_log',
    'tabulate',
]

EXTRA_DEPENDENCIES = {
    # Extra dependencies are made available through the
    # `$ pip install .[keyword]` command.
    'tests': [
        'nose',
        'coverage',
        'pycodestyle',
        'pylint'],
    'develop': [
        'isort',
        'wheel',
        'setuptools >= 24.2.1',
        'bumpversion'],
}


def read_file(*args):
    """ Return content of a file relative to this ``setup.py``. """
    file_path = os.path.join(os.path.dirname(__file__), *args)
    return codecs.open(file_path, encoding='utf-8').read()


def get_version():
    """ Extracts version from the ``__init__.py`` file at the module's root.
    """
    init_file = read_file(MODULE_NAME, '__init__.py')
    matches = re.search(
        r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', init_file, re.M)
    if matches:
        return matches.group(1)
    raise RuntimeError("Unable to find version string in __init__.py .")


def get_long_description():
    return "{}\n{}".format(read_file('README.rst'), read_file('CHANGES.rst'))


setup(
    name=PACKAGE_NAME,
    version=get_version(),
    description="Unified API to handle several package managers.",
    long_description=get_long_description(),
    keywords="CLI package pip apm npm homebrew brew cask osx macos node atom "
             "ruby gem appstore mas bitbar plugin",

    author='Kevin Deldycke',
    author_email='kevin@deldycke.com',
    url='https://github.com/kdeldycke/meta-package-manager',
    license='GPLv2+',

    packages=find_packages(),
    # https://www.python.org/dev/peps/pep-0345/#version-specifiers
    python_requires='>= 2.7, != 3.0, != 3.1, != 3.2',
    install_requires=DEPENDENCIES,
    tests_require=DEPENDENCIES + EXTRA_DEPENDENCIES['tests'],
    extras_require=EXTRA_DEPENDENCIES,
    dependency_links=[
    ],
    test_suite='{}.tests'.format(MODULE_NAME),

    classifiers=[
        # See: https://pypi.python.org/pypi?:action=list_classifiers
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Environment :: MacOS X',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: '
        'GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: MacOS :: MacOS X',
        # List of python versions and their support status:
        # https://en.wikipedia.org/wiki/CPython#Version_history
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Archiving :: Packaging',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Software Distribution',
        'Topic :: Utilities',
    ],

    entry_points={
        'console_scripts': [
            'mpm={}.cli:cli'.format(MODULE_NAME),
        ],
    }
)
