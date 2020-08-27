# -*- coding: utf-8 -*-
#
# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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

import re

import simplejson as json

from ..base import PackageManager
from ..platform import LINUX, MACOS, WINDOWS
from ..version import TokenizedString, parse_version


class Pip(PackageManager):

    """We will use system's default Python to call out ``pip`` as a module.

    This is a more robust way of managing packages: "if you're on Windows there
    is an added benefit to using python -m pip as it lets pip update itself."
    Source: https://snarky.ca/why-you-should-use-python-m-pip/
    """

    platforms = frozenset([MACOS, LINUX, WINDOWS])

    requirement = "10.0.0"

    # We will use system's default python to call out pip as a module.
    cli_name = "python"

    global_args = [
        "-m",
        "pip",  # Canonical call to Python's pip module.
        "--no-color",  # Suppress colored output.
    ]

    def get_version(self):
        """Fetch version.

        .. code-block:: shell-session

            ► python -m pip --no-color --version
            pip 2.0.2 from /usr/local/lib/python/site-packages/pip (python 3.7)
        """
        output = self.run_cli(self.global_args, "--version")
        if output:
            return parse_version(output.split()[1])

    @property
    def installed(self):
        """ Fetch installed packages.

        .. code-block:: shell-session

            ► python -m pip list --no-color --format=json --verbose --quiet \
            > | jq
            [
             {
                "version": "1.3",
                "name": "backports.functools-lru-cache",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
              },
              {
                "version": "0.9999999",
                "name": "html5lib",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
              },
              {
                "name": "setuptools",
                "version": "46.0.0",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": ""
              },
              {
                "version": "2.8",
                "name": "Jinja2",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": ""
              },
              (...)
            ]
        """
        installed = {}

        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            self.global_args, "list", "--format=json", "--verbose", "--quiet"
        )

        if output:
            for package in json.loads(output):
                package_id = package["name"]
                installed[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package["version"]),
                }

        return installed

    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. code-block:: shell-session

            ► python -m pip --no-color search abc
            ABC (0.0.0)                 - UNKNOWN
            micropython-abc (0.0.1)     - Dummy abc module for MicroPython
            abc1 (1.2.0)                - a list about my think
            abcd (0.3.0)                - AeroGear Build Cli for Digger
            abcyui (1.0.0)              - Sorry ,This is practice!
            astroabc (1.4.2)            - A Python implementation of an
                                          Approximate Bayesian Computation
                                          Sequential Monte Carlo (ABC SMC)
                                          sampler for parameter estimation.
            collective.js.abcjs (1.10)  - UNKNOWN
            cosmo (1.0.5)               - Python ABC sampler
        """
        matches = {}

        output = self.run_cli(self.global_args, "search", query)

        if output:
            regexp = re.compile(
                r"""
                ^(?P<package_id>\S+)  # A string with a char at least.
                \                     # A space.
                \((?P<version>.*?)\)  # Content between parenthesis.
                [ ]+-                 # A space or more, then a dash.
                (?P<description>      # Start of the multi-line desc group.
                    (?:[ ]+.*\s)+     # Lines of strings prefixed by spaces.
                )
                """,
                re.MULTILINE | re.VERBOSE,
            )

            for package_id, version, description in regexp.findall(output):

                # Exclude packages not featuring the search query in their ID
                # or name.
                if not extended:
                    query_parts = set(map(str, TokenizedString(query)))
                    pkg_parts = set(map(str, TokenizedString(package_id)))
                    if not query_parts.issubset(pkg_parts):
                        continue

                # Filters out fuzzy matches, only keep stricly matching
                # packages.
                if exact and query != package_id:
                    continue

                matches[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "latest_version": parse_version(version),
                }

        return matches

    @property
    def outdated(self):
        """ Fetch outdated packages.

        .. code-block:: shell-session

            ► python -m pip --no-color list --format=json --outdated \
            > --verbose --quiet | jq
            [
              {
                "latest_filetype": "wheel",
                "version": "0.7.9",
                "name": "alabaster",
                "latest_version": "0.7.10",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
              },
              {
                "latest_filetype": "wheel",
                "version": "0.9999999",
                "name": "html5lib",
                "latest_version": "0.999999999",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "2.8",
                "name": "Jinja2",
                "latest_version": "2.9.5",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "0.5.3",
                "name": "mccabe",
                "latest_version": "0.6.1",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "2.2.0",
                "name": "pycodestyle",
                "latest_version": "2.3.1",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "2.1.3",
                "name": "Pygments",
                "latest_version": "2.2.0",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": ""
               }
            ]
        """
        outdated = {}

        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            self.global_args,
            "list",
            "--format=json",
            "--outdated",
            "--verbose",
            "--quiet",
        )

        if output:
            for package in json.loads(output):
                package_id = package["name"]
                outdated[package_id] = {
                    "id": package_id,
                    "name": package_id,
                    "installed_version": parse_version(package["version"]),
                    "latest_version": parse_version(package["latest_version"]),
                }

        return outdated

    def upgrade_cli(self, package_id):
        """Build-up package upgrade CLI.

        .. code-block:: shell-session

            ► python -m pip --no-color install --user --upgrade six
            Collecting six
              Using cached six-1.15.0-py2.py3-none-any.whl (10 kB)
            Installing collected packages: six
              Attempting uninstall: six
                Found existing installation: six 1.14.0
                Uninstalling six-1.14.0:
                  Successfully uninstalled six-1.14.0
            Successfully installed six-1.15.0
        """
        return [
            self.cli_path,
            self.global_args,
            "install",
            "--user",
            "--upgrade",
            package_id,
        ]

    def upgrade_all_cli(self):
        """Pip lacks support of a proper full upgrade command. Raising an
        error let the parent class upgrade packages one by one.

        See: https://github.com/pypa/pip/issues/59
        """
        raise NotImplementedError
