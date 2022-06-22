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

from click_extra.platform import LINUX

from .. import logger
from ..base import Package, PackageManager


class APT(PackageManager):

    """Base package manager shared by variation of the apt command.

    Documentation:
    - https://wiki.debian.org/AptCLI
    - http://manpages.ubuntu.com/manpages/xenial/man8/apt.8.html

    See other command equivalences at: https://wiki.archlinux.org/title/Pacman/Rosetta
    """

    homepage_url = "https://wiki.debian.org/AptCLI"

    platforms = frozenset({LINUX})

    requirement = "1.0.0"

    post_args = ("--quiet",)

    version_regex = r"apt\s+(?P<version>\S+)"
    """
    .. code-block:: shell-session

        ► apt --version
        apt 2.0.6 (amd64)
    """

    @property
    def installed(self):
        """Fetch installed packages.

        .. code-block:: shell-session

            ► apt list --installed --quiet
            Listing...
            adduser/xenial,now 3.113+nmu3ubuntu4 all [installed]
            base-files/xenial-updates,now 9.4ubuntu4.3 amd64 [installed]
            base-passwd/xenial,now 3.5.39 amd64 [installed]
            bash/xenial-updates,now 4.3-14ubuntu1.1 amd64 [installed]
            bc/xenial,now 1.06.95-9build1 amd64 [installed]
            bsdmainutils/xenial,now 9.0.6ubuntu3 amd64 [installed,automatic]
            bsdutils/xenial-updates,now 1:2.27.1-6ubuntu3.1 amd64 [installed]
            ca-certificates/xenial,now 20160104ubuntu1 all [installed]
            coreutils/xenial,now 8.25-2ubuntu2 amd64 [installed]
            cron/xenial,now 3.0pl1-128ubuntu2 amd64 [installed]
            dash/xenial,now 0.5.8-2.1ubuntu2 amd64 [installed]
            debconf/xenial,now 1.5.58ubuntu1 all [installed]
            debianutils/xenial,now 4.7 amd64 [installed]
            diffutils/xenial,now 1:3.3-3 amd64 [installed]
            dpkg/xenial-updates,now 1.18.4ubuntu1.1 amd64 [installed]
            dstat/xenial,now 0.7.2-4 all [installed]
            e2fslibs/xenial,now 1.42.13-1ubuntu1 amd64 [installed]
            e2fsprogs/xenial,now 1.42.13-1ubuntu1 amd64 [installed]
            ethstatus/xenial,now 0.4.3ubuntu2 amd64 [installed]
            file/xenial,now 1:5.25-2ubuntu1 amd64 [installed]
            findutils/xenial,now 4.6.0+git+20160126-2 amd64 [installed]
            fio/xenial,now 2.2.10-1ubuntu1 amd64 [installed]
            gcc-6-base/xenial,now 6.0.1-0ubuntu1 amd64 [installed]
            groff-base/xenial,now 1.22.3-7 amd64 [installed,automatic]
        """
        output = self.run_cli("list", "--installed")

        regexp = re.compile(r"(\S+)\/\S+ (\S+) .*")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield Package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self):
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► apt list --upgradable --quiet
            Listing...
            apt/xenial-updates 1.2.19 amd64 [upgradable from: 1.2.15ubuntu0.2]
            nano/xenial-updates 2.5.3-2ubuntu2 amd64 [upgradable from: 2.5.3-2]
        """
        output = self.run_cli("list", "--upgradable")

        regexp = re.compile(r"(\S+)\/\S+ (\S+).*\[upgradable from: (\S+)\]")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, latest_version, installed_version = match.groups()
                yield Package(
                    id=package_id,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. code-block:: shell-session

            ► apt search abc --names-only --quiet
            Sorting...
            Full Text Search...
            abcde/xenial 2.7.1-1 all
              A Better CD Encoder

            abcmidi/xenial 20160103-1 amd64
              converter from ABC to MIDI format and back

            berkeley-abc/xenial 1.01+20150706hgc3698e0+dfsg-2 amd64
              ABC - A System for Sequential Synthesis and Verification

            grabcd-rip/xenial 0009-1 all
              rip and encode audio CDs - ripper

            libakonadi-kabc4/xenial 4:4.14.10-1ubuntu2 amd64
              Akonadi address book access library

        .. code-block:: shell-session

            ► apt search ^sed$ --names-only --quiet
            Sorting...
            Full Text Search...
            sed/xenial 2.1.9-3 all
              Blah blah blah

        .. code-block:: shell-session

            ► apt search abc --full --quiet
            Sorting...
            Full Text Search...
            abcde/xenial 2.7.1-1 all
              This package contains the essential basic system utilities.
              .
              Specifically, this package includes:
              basename cat chgrp chmod chown chroot cksum comm cp csplit cut
              dircolors dirname du echo env expand expr factor false fmt
              hostid id install join link ln logname ls md5sum mkdir mkfifo
              nohup od paste pathchk pinky pr printenv printf ptx pwd
              sha1sum seq shred sleep sort split stat stty sum sync tac tail
              tr true tsort tty uname unexpand uniq unlink users vdir wc who

            midi/xenial 20160103-1 amd64
              converter from ABC to MIDI format and back
            (...)
        """
        search_arg = "--names-only"
        if exact:
            # Rely on apt regexp support to speed-up exact match.
            query = f"^{query}$"
        # Extended search are always non-exact.
        elif extended:
            # Include full description in extended search to check up the match
            # in the CLI output after its execution.
            search_arg = "--full"

        output = self.run_cli("search", query, search_arg)

        regexp = re.compile(
            r"""
            ^(?P<package_id>\S+)  # A string with a char at least.
            /.+\                  # A slash, any string, then a space.
            (?P<version>.+)       # Any string.
            \                     # A space.
            (?:.+)\n              # Any string ending the line.
            (?P<description>      # Start of the multi-line desc group.
                (?:\ \ .+\n)+     # Lines of strings prefixed by 2 spaces.
            )
            """,
            re.MULTILINE | re.VERBOSE,
        )

        for package_id, version, description in regexp.findall(output):
            yield Package(
                id=package_id, description=description, latest_version=version
            )

    def install(self, package_id):
        """Install one package.

        .. code-block:: shell-session

            ► sudo apt install git --yes --quiet
        """
        return self.run_cli("install", package_id, "--yes", sudo=True)

    def upgrade_cli(self, package_id=None):
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► sudo apt upgrade --yes --quiet

        .. code-block:: shell-session

            ► sudo apt install --only-upgrade git --yes --quiet
        """
        params = ("upgrade",)
        if package_id:
            params = ("install", "--only-upgrade", package_id)

        return self.build_cli(*params, "--yes", sudo=True)

    def sync(self):
        """Sync package metadata.

        .. code-block:: shell-session

            ► sudo apt update --yes --quiet
            Hit:1 http://archive.ubuntu.com xenial InRelease
            Get:2 http://archive.ubuntu.com xenial-updates InRelease [102 kB]
            Get:3 http://archive.ubuntu.com xenial-security InRelease [102 kB]
            Get:4 http://archive.ubuntu.com xenial/main Translation-en [568 kB]
            Fetched 6,868 kB in 2s (2,680 kB/s)
            Reading package lists...
            Building dependency tree...
            Reading state information...
        """
        self.run_cli("update", "--yes", sudo=True)

    def cleanup(self):
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► sudo apt autoremove --yes --quiet
            ► sudo apt clean --yes --quiet
        """
        for command in ("autoremove", "clean"):
            self.run_cli(command, "--yes", sudo=True)


class APT_Mint(APT):

    """Special version of apt for Linux Mint.

    Exactly the same as its parent but implement specific version extraction.
    """

    name = "Linux Mint's apt"

    homepage_url = "https://github.com/kdeldycke/meta-package-manager/issues/52"

    cli_names = ("apt",)

    version_cli_options = ("version", "apt")
    """
    .. code-block:: shell-session

        ► apt version apt
        1.6.11
    """

    def search(self, query, extended, exact):
        """Fetch matching packages.

        .. caution::
            Search does not supports extended matching.

        .. code-block:: shell-session

            ► /usr/local/bin/apt search sed --quiet
            v   librust-slog-2.5+erased-serde-dev  -
            p   python3-blessed                    - Practical wrapper
            i   sed                                - GNU stream editor
            p   sed:i386                           - GNU stream editor

        .. code-block:: shell-session

            ► /usr/local/bin/apt search ^sed$ --quiet
            i   sed              - GNU stream editor
            p   sed:i386         - GNU stream editor
        """
        if extended:
            logger.warning(f"{self.id} does not implement extended search operation.")

        if exact:
            # Rely on apt regexp support to speed-up exact match.
            query = f"^{query}$"

        output = self.run_cli("search", query)

        regexp = re.compile(
            r"""
            \S                       # One non-space character.
            \s+                      # One space or more.
            (?P<package_id>[^\s:]+)  # Any non-space until whitespace or semi-colon.
            (?:\:\S+)?               # Optional arch suffix after package and semi-colon.
            \s+                      # One space or more.
            -                        # A dash.
            \ ?                      # An optional space.
            (?P<description>\S+)?    # Optional non-space string.
            """,
            re.VERBOSE,
        )

        for package_id, description in regexp.findall(output):
            yield Package(id=package_id, description=description)
