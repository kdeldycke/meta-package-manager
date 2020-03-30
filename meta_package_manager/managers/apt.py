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

from boltons.cacheutils import cachedproperty

from ..base import PackageManager
from ..platform import LINUX
from ..version import parse_version


class APT(PackageManager):

    """ Documentation:
    http://manpages.ubuntu.com/manpages/xenial/man8/apt.8.html
    """

    platforms = frozenset([LINUX])

    requirement = '1.0.0'

    def get_version(self):
        """ Fetch version from ``apt version`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apt --version
            apt 1.2.15 (amd64)

        In Linux Mint, another command has to be used:

        .. code-block:: shell-session

            $ apt version apt
            1.6.11
        """
        output = self.run([self.cli_path, '--version'])
        version = None
        if output:
            output = output.splitlines()[0].split()
            if len(output) > 1:
                version = output[1]
            else:
                output = self.run([self.cli_path, 'version', 'apt'])
                if output:
                    version = output
        if version:
            return parse_version(version)

    def sync(self):
        """

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apt update --quiet
            Hit:1 http://archive.ubuntu.com xenial InRelease
            Get:2 http://archive.ubuntu.com xenial-updates InRelease [102 kB]
            Get:3 http://archive.ubuntu.com xenial-security InRelease [102 kB]
            Get:4 http://archive.ubuntu.com xenial/main Translation-en [568 kB]
            Fetched 6,868 kB in 2s (2,680 kB/s)
            Reading package lists...
            Building dependency tree...
            Reading state information...
        """
        super(APT, self).sync()
        self.run([self.cli_path] + self.cli_args + ['update', '--quiet'])

    @cachedproperty
    def installed(self):
        """ Fetch installed packages from ``apt list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apt list --installed --quiet
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
        installed = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'list', '--installed', '--quiet'])

        if output:
            regexp = re.compile(r'(\S+)\/\S+ (\S+) .*')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, installed_version = match.groups()
                    installed[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'installed_version': parse_version(installed_version)}

        return installed

    def search(self, query):
        """ Fetch matching packages from ``apt search`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apt search abc --quiet
            Sorting...
            Full Text Search...
            abcde/xenial 2.7.1-1 all
              A Better CD Encoder

            abcm2ps/xenial 7.8.9-1 amd64
              Translates ABC music description files to PostScript

            abcmidi/xenial 20160103-1 amd64
              converter from ABC to MIDI format and back

            berkeley-abc/xenial 1.01+20150706hgc3698e0+dfsg-2 amd64
              ABC - A System for Sequential Synthesis and Verification

            grabcd-encode/xenial 0009-1 all
              rip and encode audio CDs - encoder

            grabcd-rip/xenial 0009-1 all
              rip and encode audio CDs - ripper

            libakonadi-kabc4/xenial 4:4.14.10-1ubuntu2 amd64
              Akonadi address book access library

            libgrabcd-readconfig-perl/xenial 0009-1 all
              rip and encode audio CDs - common files

            libkabc4/xenial 4:4.14.10-1ubuntu2 amd64
              library for handling address book data
        """
        matches = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'search', query, '--quiet'])

        if output:
            regexp = re.compile(
                r'\s*(\S+)\/(\S+) (\S+) (\S+)\s+(.*)', re.DOTALL)
            for package in re.compile(r'(\n\n|.*\.\.\.\n)').split(output):
                match = regexp.match(package)
                if match:
                    package_id, repository, latest_version, arch, \
                        description = match.groups()
                    matches[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': parse_version(latest_version),
                        'exact': self.exact_match(query, package_id)}

        return matches

    @cachedproperty
    def outdated(self):
        """ Fetch outdated packages from ``apt list`` output.

        Raw CLI output samples:

        .. code-block:: shell-session

            $ apt list --upgradable --quiet
            Listing...
            apt/xenial-updates 1.2.19 amd64 [upgradable from: 1.2.15ubuntu0.2]
            nano/xenial-updates 2.5.3-2ubuntu2 amd64 [upgradable from: 2.5.3-2]
        """
        outdated = {}

        output = self.run([self.cli_path] + self.cli_args + [
            'list', '--upgradable', '--quiet'])

        if output:
            regexp = re.compile(
                r'(\S+)\/\S+ (\S+).*\[upgradable from: (\S+)\]')
            for package in output.splitlines():
                match = regexp.match(package)
                if match:
                    package_id, latest_version, installed_version = \
                        match.groups()
                    outdated[package_id] = {
                        'id': package_id,
                        'name': package_id,
                        'latest_version': parse_version(latest_version),
                        'installed_version': parse_version(installed_version)}

        return outdated

    def upgrade_cli(self, package_id=None):
        cmd = [self.cli_path] + self.cli_args + ['update']
        if package_id:
            cmd.append(package_id)
        return cmd

    def upgrade_all_cli(self):
        return self.upgrade_cli()

    def cleanup(self):
        """ Runs:

        .. code-block:: shell-session

            $ sudo apt-get -y autoremove
        """
        super(APT, self).cleanup()
        self.run(
            ['sudo', self.cli_path] + self.cli_args + ['-y', 'autoremove'])
