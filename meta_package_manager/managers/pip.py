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

from __future__ import annotations

import json
import re
from typing import Iterator

from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented


class Pip(PackageManager):

    """We will use the Python binary to call out ``pip`` as a module instead of a CLI.

    This is a more robust way of managing packages: "if you're on Windows there
    is an added benefit to using `python -m pip` as it lets `pip` update itself."
    Source: https://snarky.ca/why-you-should-use-python-m-pip/
    """

    homepage_url = "https://pip.pypa.io"

    platforms = frozenset({MACOS, LINUX, WINDOWS})

    requirement = "10.0.0"

    # Targets `python3` CLI first to allow for some systems (like macOS) to keep the
    # default `python` CLI tied to the Python 2.x ecosystem.
    cli_names = ("python3", "python")

    pre_args = (
        "-m",
        "pip",  # Canonical call to Python's pip module.
        "--no-color",  # Suppress colored output.
    )

    version_cli_options = tuple(list(pre_args) + ["--version"])
    version_regex = r"pip\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► python -m pip --no-color --version
        pip 2.0.2 from /usr/local/lib/python/site-packages/pip (python 3.7)
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► python -m pip --no-color list --format=json --verbose --quiet \
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
        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli("list", "--format=json", "--verbose", "--quiet")

        if output:
            for package in json.loads(output):
                yield self.package(
                    id=package["name"], installed_version=package["version"]
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

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
        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            "list",
            "--format=json",
            "--outdated",
            "--verbose",
            "--quiet",
        )

        if output:
            for package in json.loads(output):
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                    latest_version=package["latest_version"],
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search_xxx_disabled(
        self, query: str, extended: bool, exact: bool
    ) -> Iterator[Package]:

        """Fetch matching packages.

        .. warning::
            That function was previously named ``search`` but has been renamed
            to make it invisible from the ``mpm`` framework, disabling search
            feature altogether for ``pip``.

            This had to be done has Pip's maintainers disabled the server-side
            API because of unmanageable high-load. See:
            https://github.com/pypa/pip/issues/5216#issuecomment-744605466

        .. caution::
            Search is extended by default. So we returns the best subset of results and let
            :py:meth:`meta_package_manager.base.PackageManager.refiltered_search` refine them

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
        output = self.run_cli("search", query)

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
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► python -m pip --no-color install arrow
            Collecting arrow
              Using cached arrow-1.1.1-py3-none-any.whl (60 kB)
            Collecting python-dateutil>=2.7.0
              Using cached python_dateutil-2.8.2-py2.py3-none-any.whl (247 kB)
            Requirement already satisfied: six>=1.5 in python3.9/site-packages (1.16.0)
            Installing collected packages: python-dateutil, arrow
            Successfully installed arrow-1.1.1 python-dateutil-2.8.2
        """
        return self.run_cli("install", package_id)

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

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

        ,, note::

            Pip lacks support of a proper full upgrade command. Raising an error let the
            parent class upgrade packages one by one.

            See: https://github.com/pypa/pip/issues/59
        """
        return self.build_cli("install", "--user", "--upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            ► python -m pip --no-color uninstall --yes arrow
        """
        return self.run_cli("uninstall", "--yes", package_id)
