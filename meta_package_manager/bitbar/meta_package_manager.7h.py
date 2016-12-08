#!/usr/bin/env python
# -*- coding: utf-8 -*-
# <bitbar.title>Meta Package Manager</bitbar.title>
# <bitbar.version>v2.1.0</bitbar.version>
# <bitbar.author>Kevin Deldycke</bitbar.author>
# <bitbar.author.github>kdeldycke</bitbar.author.github>
# <bitbar.desc>List outdated packages and manage upgrades.</bitbar.desc>
# <bitbar.dependencies>python</bitbar.dependencies>
# <bitbar.image>https://i.imgur.com/CiQpQ42.png</bitbar.image>
# <bitbar.abouturl>https://github.com/kdeldycke/meta-package-manager</bitbar.abouturl>

"""
Default update cycle is set to 7 hours so we have a chance to get user's
attention once a day. Higher frequency might ruin the system as all checks are
quite resource intensive, and Homebrew might hit GitHub's API calls quota.
"""

from __future__ import print_function, unicode_literals

import json
import os
from operator import itemgetter
from subprocess import PIPE, Popen


def expand_cli_search_scope():
    """ Tweak environment variable to find non-default system-wide binaries.

    macOS does not put ``/usr/local/bin`` or ``/opt/local/bin`` in the ``PATH``
    for GUI apps. For some package managers this is a problem. Additioanlly
    Homebrew and Macports are using different pathes. So, to make sure we can
    always get to the necessary binaries, we overload the path. Current
    preference order would equate to Homebrew, Macports, then system.
    """
    os.environ['PATH'] = ':'.join([
        '/usr/local/bin',
        '/usr/local/sbin',
        '/opt/local/bin',
        '/opt/local/sbin',
        os.environ.get('PATH', '')])


def run(cmd):
    """ Run a shell command, return error code, output and error message. """
    assert isinstance(cmd, list)
    try:
        process = Popen(cmd, stdout=PIPE, stderr=PIPE)
    except OSError:
        return None, None, "`{}` executable not found.".format(cmd[0])
    output, error = process.communicate()
    return (
        process.returncode,
        output.decode('utf-8').strip(),
        error.decode('utf-8').strip())


def print_error_header():
    """ Generic header for blockng error. """
    print("❌ | dropdown=false".encode('utf-8'))
    print("---")


def print_error(message):
    """ Print a formatted error line by line, in red. """
    for line in message.strip().split("\n"):
        print("{} | color=red font=Menlo".format(line))


def print_menu():
    """ Print menu structure using BitBar's plugin API.

    See: https://github.com/matryer/bitbar#plugin-api
    """
    # Search for generic mpm CLI on system.
    retcode, _, error = run(['mpm'])
    if retcode or error:
        print_error_header()
        if retcode is None:
            print(
                "{} Click here to install it. | bash=pip "
                # TODO: Add minimal requirement on Python package.
                "param1=install param2=--upgrade param3=meta-package-manager "
                "terminal=true refresh=true color=red".format(error))
        else:
            print_error(error)
        return

    # Fetch list of all outdated packages from all package manager available on
    # the system.
    _, output, error = run([
        'mpm', '--output-format', 'json',
        'outdated', '--cli-format', 'bitbar'])

    if error:
        print_error_header()
        print_error(error)
        return

    # Sort outdated packages by manager's name.
    managers = sorted(
        json.loads(output.decode('utf-8')).values(),
        key=itemgetter('name'))

    # Print menu bar icon with number of available upgrades.
    total_outdated = sum([len(m['packages']) for m in managers])
    total_errors = len([True for m in managers if m['error']])
    print(("↑{}{} | dropdown=false".format(
        total_outdated,
        " ⚠️{}".format(total_errors) if total_errors else ""
    )).encode('utf-8'))

    # Print a full detailed section for each manager.
    for manager in managers:
        print("---")

        if manager['error']:
            print_error(manager['error'])

        print("{} outdated {} package{}".format(
            len(manager['packages']),
            manager['name'],
            's' if len(manager['packages']) != 1 else ''))

        if manager['upgrade_all_cli']:
            print("Upgrade all | {} terminal=false refresh=true".format(
                manager['upgrade_all_cli']))

        for pkg_info in manager['packages']:
            print((
                "{name} {installed_version} → {latest_version} | "
                "{upgrade_cli} terminal=false refresh=true".format(
                    **pkg_info)).encode('utf-8'))


if __name__ == '__main__':
    expand_cli_search_scope()
    print_menu()
