# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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

from click_extra.platforms import FREEBSD, LINUX, MACOS, NETBSD

from meta_package_manager.base import Package, PackageManager
from meta_package_manager.capabilities import (
    version_not_implemented,
)


class PKG(PackageManager):
    name = "FreeBSD System Manager"

    homepage_url = "https://github.com/freebsd/pkg"

    platforms = FREEBSD, LINUX, NETBSD, MACOS

    requirement = "1.20.0"

    """
    .. code-block:: shell-session
        ► pkg --version
        1.20.9
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            ► pkg query -e "%a = 0" "%n %v %c"
            7-zip 21.07_2 Console version of the 7-Zip file archiver
            ap24-mod_mpm_itk 2.4.7_2 Run each vhost under a separate uid and gid
            apache24 2.4.57 Version 2.4.x of Apache web server
            aquantia-atlantic-kmod 0.0.5_1 Aquantia AQtion (Atlantic) Network Driver (Development Preview)
            arcconf 3.07.23971,1 Adaptec SCSI/SAS RAID administration tool
            areca-cli-amd64 1.14.7.150519,1 Command Line Interface for the Areca ARC-xxxx RAID controllers
            base64 1.5_1 Utility to encode and decode base64 files
            bash 5.1.12 GNU Project's Bourne Again SHell
            beadm 1.4_1 Solaris-like utility to manage Boot Environments on ZFS
        """
        output = self.run_cli("query", "-e", r'"%a = 0"', r'"%n %v %c"')

        regexp = re.compile(r"(\S+) (\S+) (.+)")
        for package in output.splitlines():
            match = regexp.match(package)
            if match:
                package_id, installed_version, description = match.groups()
                yield self.package(
                    id=package_id,
                    description=description,
                    installed_version=installed_version,
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            ► pkg upgrade --dry-run
            Updating FreeBSD repository catalogue...
            FreeBSD repository is up to date.
            All repositories are up to date.
            Checking for upgrades (312 candidates): 100%
            Processing candidates (312 candidates): 100%
            The following 466 package(s) will be affected (of 0 checked):

            Installed packages to be REMOVED:
                freenas-files: 13.0_1700495253
                py39-midcli: 20190509171453
                py39-middlewared: 13.0_1700495253

            New packages to be INSTALLED:
                abseil: 20230125.3 [FreeBSD]
                argp-standalone: 1.5.0 [FreeBSD]
                brotli: 1.1.0,1 [FreeBSD]

            Installed packages to be UPGRADED:
                7-zip: 21.07_2 -> 23.01 [FreeBSD]
                apache24: 2.4.57 -> 2.4.58_1 [FreeBSD]
                apr: 1.7.0.1.6.1_1 -> 1.7.3.1.6.3_1 [FreeBSD]
                aquantia-atlantic-kmod: 0.0.5_1 -> 0.0.5_2 [FreeBSD]
                bash: 5.1.12 -> 5.2.21 [FreeBSD]

        .. note::

            We rely on ``pkg upgrade`` instead of ``pkg version`` because the latter
            does not provides the new version:

            .. code-block:: shell-session

                ► pkg version --like "<"
                Updating FreeBSD repository catalogue...
                FreeBSD repository is up to date.
                All repositories are up to date.
                7-zip-21.07_2                      <
                apache24-2.4.57                    <
                apr-1.7.0.1.6.1_1                  <
                aquantia-atlantic-kmod-0.0.5_1     <
                bash-5.1.12                        <
        """
        output = self.run_cli("upgrade", "--dry-run")

        outdated_list = output.split("Installed packages to be UPGRADED:", 1)[1].strip()

        regexp = re.compile(r"(\S+): (\S+) -> (\S+) .+")
        for package in outdated_list.splitlines():
            match = regexp.match(package.strip())
            if match:
                package_id, installed_version, latest_version = match.groups()
                yield self.package(
                    id=package_id,
                    latest_version=latest_version,
                    installed_version=installed_version,
                )

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Default search on ID substring:

        .. code-block:: shell-session

            ► pkg search --raw --raw-format json-compact --search name nginx
            {
                "name": "nginx",
                "version": "1.24.0_14,3",
                "comment": "Robust and small WWW server",
                (...)
            }
            {
                "name": "nginx-devel",
                "version": "1.25.3_9",
                "comment": "Robust and small WWW server",
                (...)
            }
            {
                "name": "nginx-ultimate-bad-bot-blocker",
                "version": "4.2020.03.2005_1",
                "comment": "Nginx bad bot and other things blocker",
                (...)
            }
            {
                "name": "p5-Nginx-ReadBody",
                "version": "0.07_1",
                "comment": "Nginx embedded perl module to read a request",
                (...)
            }
            (...)

        Exact search on ID:

        .. code-block:: shell-session

            ► pkg search --raw --raw-format json-compact --search name --exact nginx
            {
                "name": "nginx",
                "origin": "www/nginx",
                "version": "1.24.0_14,3",
                "comment": "Robust and small WWW server",
                "maintainer": "joneum@FreeBSD.org",
                "www": "https://nginx.com/",
                "abi": "FreeBSD:13:amd64",
                "arch": "freebsd:13:x86:64",
                "prefix": "/usr/local",
                "sum": "c39a7696e6eda7bfedba251e4480e50d4c65c520d5a783a584b19b3ef883",
                "flatsize": 1464332,
                "path": "All/nginx-1.24.0_14,3.pkg",
                "repopath": "All/nginx-1.24.0_14,3.pkg",
                "licenselogic": "single",
                "licenses": [
                    "BSD2CLAUSE"
                ],
                "pkgsize": 473632,
                "desc": "NGINX is a high performance edge web server with the (...)",
                "deps": {
                    "pcre2": {
                        "origin": "devel/pcre2",
                        "version": "10.42"
                    }
                },
                "categories": [
                    "www"
                ],
                "shlibs_required": [
                    "libpcre2-8.so.0"
                ],
                "options": {
                    "AJP": "off",
                    "ARRAYVAR": "off",
                    "AWS_AUTH": "off",
                    "BROTLI": "off",
                    "CACHE_PURGE": "off",
                    "CLOJURE": "off",
                    "COOKIE_FLAG": "off",
                    "CT": "off",
                    "DEBUG": "off",
                    "DEBUGLOG": "off",
                    "DEVEL_KIT": "off",
                    "DRIZZLE": "off",
                    "DSO": "on",
                    "DYNAMIC_UPSTREAM": "off",
                    "ECHO": "off",
                    "ENCRYPTSESSION": "off",
                    "FILE_AIO": "on",
                    "FIPS_CHECK": "off",
                    "FORMINPUT": "off",
                    "GOOGLE_PERFTOOLS": "off",
                    "GRIDFS": "off",
                    "GSSAPI_HEIMDAL": "off",
                    "GSSAPI_MIT": "off",
                    "HEADERS_MORE": "off",
                    "HTTP": "on",
                    "HTTPV2": "on",
                    "HTTPV3": "off",
                    "HTTPV3_BORING": "off",
                    "HTTPV3_LSSL": "off",
                    "HTTPV3_QTLS": "off",
                    "HTTP_ACCEPT_LANGUAGE": "off",
                    "HTTP_ADDITION": "on",
                    "HTTP_AUTH_DIGEST": "off",
                    "HTTP_AUTH_KRB5": "off",
                    "HTTP_AUTH_LDAP": "off",
                    "HTTP_AUTH_PAM": "off",
                    "HTTP_AUTH_REQ": "on",
                    "HTTP_CACHE": "on",
                    "HTTP_DAV": "on",
                    "HTTP_DAV_EXT": "off",
                    "HTTP_DEGRADATION": "off",
                    "HTTP_EVAL": "off",
                    "HTTP_FANCYINDEX": "off",
                    "HTTP_SUBS_FILTER": "off",
                    "HTTP_TARANTOOL": "off",
                    "HTTP_UPLOAD": "off",
                    "HTTP_UPLOAD_PROGRESS": "off",
                    "HTTP_UPSTREAM_CHECK": "off",
                    "HTTP_UPSTREAM_FAIR": "off",
                    "HTTP_UPSTREAM_STICKY": "off",
                    "HTTP_VIDEO_THUMBEXTRACTOR": "off",
                    "HTTP_XSLT": "off",
                    "HTTP_ZIP": "off",
                    "ICONV": "off",
                    "IPV6": "on",
                    "LET": "off",
                    "LINK": "off",
                    "LUA": "off",
                    "MAIL": "on",
                    "MAIL_IMAP": "off",
                    "MAIL_POP3": "off",
                    "MAIL_SMTP": "off",
                    "MAIL_SSL": "on",
                    "MEMC": "off",
                    "MODSECURITY3": "off",
                    "NAXSI": "off",
                    "NJS": "off",
                    "NJS_XML": "off",
                    "OPENTRACING": "off",
                    "PASSENGER": "off",
                    "POSTGRES": "off",
                    "RDS_CSV": "off",
                    "RDS_JSON": "off",
                    "REDIS2": "off",
                    "RTMP": "off",
                    "SET_MISC": "off",
                    "SFLOW": "off",
                    "SHIBBOLETH": "off",
                    "SLOWFS_CACHE": "off",
                    "SRCACHE": "off",
                    "STREAM": "on",
                    "STREAM_REALIP": "on",
                    "STREAM_SSL": "on",
                    "STREAM_SSL_PREREAD": "on",
                    "STS": "off",
                    "THREADS": "on",
                    "VOD": "off",
                    "VTS": "off",
                    "WEBSOCKIFY": "off",
                    "WWW": "on",
                    "XSS": "off"
                },
                "annotations": {
                    "FreeBSD_version": "1302001",
                    "build_timestamp": "2024-01-07T10:41:34+0000",
                    "built_by": "poudriere-git-3.4.0",
                    "cpe": "cpe:2.3:a:f5:nginx:1.24.0:::::freebsd13:x64:14",
                    "port_checkout_unclean": "no",
                    "port_git_hash": "756e18783",
                    "ports_top_checkout_unclean": "no",
                    "ports_top_git_hash": "756e18783"
                }
            }

        Extended search:

        .. code-block:: shell-session

            ► pkg search --raw --raw-format json-compact --search name --search comment --search description nginx
        """
        search_args = ["--raw", "--raw-format", "json-compact", "--search", "name"]
        if exact:
            search_args.append("--exact")
        # Expand search to the comment and description fields.
        if extended:
            search_args += ["--search", "comment", "--search", "description"]

        output = self.run_cli(search_args, query)

        for package in map(json.loads, output.splitlines()):
            yield self.package(
                id=package["name"],
                description=package["comment"],
                latest_version=package["version"],
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            ► pkg install --yes dmg2img
            Updating FreeBSD repository catalogue...
            FreeBSD repository is up to date.
            All repositories are up to date.
            Checking integrity... done (0 conflicting)
            The following 1 package(s) will be affected (of 0 checked):

            New packages to be INSTALLED:
                dmg2img: 1.6.7 [FreeBSD]

            Number of packages to be installed: 1
            [1/1] Installing dmg2img-1.6.7...
            [1/1] Extracting dmg2img-1.6.7: 100%
        """
        return self.run_cli("install", "--yes", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► pkg upgrade --yes
        """
        return self.build_cli("upgrade", "--yes")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            ► pkg upgrade --yes dmg2img
        """
        return self.build_cli("upgrade", "--yes", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            ► pkg delete --yes dmg2img
            Checking integrity... done (0 conflicting)
            Deinstallation has been requested for the following 1 packages (of 0 packages in the universe):

            Installed packages to be REMOVED:
                dmg2img: 1.6.7

            Number of packages to be removed: 1
            [1/1] Deinstalling dmg2img-1.6.7...
            [1/1] Deleting files for dmg2img-1.6.7: 100%
            pkg: Package database is busy while closing!
        """
        return self.run_cli("delete", "--yes", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            ► IGNORE_OSVERSION=yes pkg update
            Updating FreeBSD repository catalogue...
            Fetching meta.conf: 100%    163 B   0.2kB/s    00:01
            Fetching packagesite.pkg: 100%    7 MiB   3.6MB/s    00:02
            Processing entries: 100%
            FreeBSD repository update completed. 33804 packages processed.
            All repositories are up to date.

        The ``IGNORE_OSVERSION=yes`` prevents blocking update:

        .. code-block:: shell-session

            ► pkg update
            Updating FreeBSD repository catalogue...
            Fetching meta.conf: 100%    163 B   0.2kB/s    00:01
            Fetching packagesite.pkg: 100%    7 MiB   3.6MB/s    00:02
            Processing entries:   0%
            Newer FreeBSD version for package zziplib:
            To ignore this error set IGNORE_OSVERSION=yes
            - package: 1302001
            - running kernel: 1301000
            Ignore the mismatch and continue? [y/N]:
        """
        self.run_cli("update", override_extra_env={"IGNORE_OSVERSION": "yes"})

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            ► pkg autoremove --yes
            Checking integrity... done (0 conflicting)
            Nothing to do.

        .. code-block:: shell-session

            ► pkg clean --yes --all
            Nothing to do.
        """
        self.run_cli("autoremove", "--yes")
        self.run_cli("clean", "--yes", "--all")
