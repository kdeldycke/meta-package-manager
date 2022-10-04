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

import re
from typing import Iterator

from click_extra.platform import LINUX, MACOS, WINDOWS

from ..base import Package, PackageManager
from ..capabilities import search_capabilities, version_not_implemented
from ..version import parse_version


class Gem(PackageManager):

    """
    ..tip::

        Installs require ``sudo`` on system ruby. I (@tresni) recommend doing something like:

        .. code-block:: shell-session

            ► sudo dseditgroup -o edit -a -t user wheel

        And then do ``visudo`` to make it so the ``wheel`` group does not require
        a password. There is a line already there for it, you just need to
        uncomment it and save.
    """

    name = "Ruby Gems"

    homepage_url = "https://rubygems.org"

    platforms = frozenset({LINUX, MACOS, WINDOWS})

    # Default to the version shipped with the latest maintained macOS version,
    # i.e. macOS 10.13 High Sierra, which is bundled with gem 2.5.2.
    requirement = "2.5.0"

    """
    .. code-block:: shell-session

        ► gem --version
        3.0.3
    """

    # Help mpm a little bit in its search for the `gem` binary.
    cli_search_path = ("/usr/local/opt/ruby/bin/gem", "/usr/local/opt/ruby/bin")

    post_args = ("--quiet",)  # Silence command progress meter

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► gem list --quiet
            bigdecimal (default: 1.4.1)
            bundler (default: 1.17.2)
            CFPropertyList (2.3.6)
            cmath (default: 1.0.0)
            csv (default: 3.0.9)
            date (default: 2.0.0)
            fileutils (1.4.1, default: 1.1.0)
            io-console (0.5.6, default: 0.4.7)
            ipaddr (default: 1.2.2)
            molinillo (0.5.4, 0.4.5, 0.2.3)
            nokogiri (1.5.6)
            psych (2.0.0)
            rake (0.9.6)
            rdoc (4.0.0)
            sqlite3 (1.3.7)
            test-unit (2.0.0.0)
        """
        output = self.run_cli("list")

        regexp = re.compile(r"(\S+) \((.+)\)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, versions = match.groups()
                # Guess latest installed version.
                version = max(
                    parse_version(v)
                    for v in re.compile(r",|default:| ").split(versions)
                    if v
                )
                yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► gem outdated --quiet
            did_you_mean (1.0.0 < 1.0.2)
            io-console (0.4.5 < 0.4.6)
            json (1.8.3 < 2.0.1)
            minitest (5.8.3 < 5.9.0)
            power_assert (0.2.6 < 0.3.0)
            psych (2.0.17 < 2.1.0)
        """
        output = self.run_cli("outdated")

        regexp = re.compile(r"(\S+) \((\S+) < (\S+)\)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, current_version, latest_version = match.groups()
                yield self.package(
                    id=package_id,
                    installed_version=current_version,
                    latest_version=latest_version,
                )

    @search_capabilities(extended_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports extended mode.

        .. code-block:: shell-session

            ► gem search python --versions --quiet
            at_coder_friends-generator-python_ref (0.2.0)
            bee_python (0.2.3)
            dependabot-python (0.117.5)
            logstash-filter-python (0.0.1 java)
            python (0.0.1)
            python-generator (1.1.0)
            python_with_git_test (2.499.8)
            rabbit-slide-niku-erlangvm-for-pythonista (2015.09.12)
            RubyToPython (0.0)

        .. code-block:: shell-session

            ► gem search python --versions --exact --quiet
            python (0.0.1)
        """
        search_arg = []
        if exact:
            search_arg.append("--exact")

        output = self.run_cli("search", query, "--versions", search_arg)

        regexp = re.compile(
            r"""
            (?P<package_id>\S+)     # Any string.
            \                       # A space.
            \(                      # Start of content in parenthesis.
                (?P<version>\S+)    # Version string.
                (?:\ \S+)?          # Optional platform value after space.
            \)
            """,
            re.VERBOSE,
        )

        for package_id, version in regexp.findall(output):
            yield self.package(id=package_id, latest_version=version)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► gem install --user-install --quiet markdown
            Fetching kramdown-2.3.1.gem
            Fetching concurrent-ruby-1.1.9.gem
            (...)
            Fetching rubyzip-2.3.2.gem
            Fetching logutils-0.6.1.gem
            Fetching markdown-1.2.0.gem
            Successfully installed kramdown-2.3.1
            Successfully installed rubyzip-2.3.2
            (...)
            Successfully installed markdown-1.2.0
            (...)
            Parsing documentation for markdown-1.2.0
            Installing ri documentation for markdown-1.2.0
            Done installing documentation for (...) markdown after 19 seconds
            12 gems installed
        """
        return self.run_cli(
            "install",
            "--user-install",
            *self.post_args,
            package_id,
            auto_post_args=False,
        )

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► gem update --user-install --quiet
        """
        return self.build_cli(
            "update",
            "--user-install",
            *self.post_args,
            auto_post_args=False,
        )

    @version_not_implemented
    def upgrade_one_cli(
        self, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► gem update --user-install --quiet markdown
        """
        return self.build_cli(
            "update",
            "--user-install",
            *self.post_args,
            package_id,
            auto_post_args=False,
        )

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            ► gem uninstall --user-install --quiet left-pad
            Successfully uninstalled left-pad-1.1.0
        """
        return self.run_cli("uninstall", package_id)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► gem cleanup --quiet
            Cleaning up installed gems...
            Attempting to uninstall test-unit-3.2.9
            Unable to uninstall test-unit-3.2.9:
                Gem::FilePermissionError: You don't have write permissions \
                for the /Library/Ruby/Gems/2.6.0 directory.
            Attempting to uninstall did_you_mean-1.3.0
            Unable to uninstall did_you_mean-1.3.0:
                Gem::FilePermissionError: You don't have write permissions \
                for the /Library/Ruby/Gems/2.6.0 directory.
            Clean up complete
        """
        self.run_cli("cleanup")
