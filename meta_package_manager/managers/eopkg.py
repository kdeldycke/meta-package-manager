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

import re

from extra_platforms import LINUX_LIKE

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


class EOPKG(PackageManager):
    name = "Solus package manager"

    homepage_url = "https://github.com/getsolus/eopkg/"

    platforms = LINUX_LIKE

    requirement = "3.2.0"

    pre_args = ("--no-color",)

    version_regexes = (r"eopkg\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ eopkg --version
        eopkg 3.2.0
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ eopkg --no-color list-installed --install-info
            Package Name          |St|        Version|  Rel.|  Distro|       Date
            =====================================================================
            aalib                 | i|        1.4.0_5|     8|   Solus|14 Oct 2024
            abseil-cpp            | i|     20240116.2|    10|   Solus|14 Oct 2024
            accountsservice       | i|        23.13.9|    36|   Solus|14 Oct 2024
            acl                   | i|          2.3.2|    21|   Solus|14 Oct 2024
            adwaita-icon-theme    | i|           46.2|    28|   Solus|14 Oct 2024
            adwaita-icon-theme-legacy  | i|           46.2|     2|   Solus|14 Oct 2024
            alsa-firmware         | i|          1.2.4|     7|   Solus|14 Oct 2024
            alsa-lib              | i|         1.2.12|    38|   Solus|14 Oct 2024
            alsa-plugins          | i|         1.2.12|    26|   Solus|14 Oct 2024
            alsa-utils            | i|         1.2.12|    28|   Solus|14 Oct 2024
            aom                   | i|         3.10.0|    24|   Solus|14 Oct 2024
            appstream             | i|          1.0.1|     9|   Solus|14 Oct 2024
            appstream-data        | i|             49|    51|   Solus|14 Oct 2024
            appstream-glib        | i|          0.8.2|    13|   Solus|14 Oct 2024
            argon2                | i|       20190702|     6|   Solus|14 Oct 2024
            at-spi2               | i|         2.52.0|    44|   Solus|14 Oct 2024
            atkmm                 | i|         2.28.4|    19|   Solus|14 Oct 2024
            attr                  | i|          2.5.2|    25|   Solus|14 Oct 2024
            audit                 | i|          4.0.2|    19|   Solus|14 Oct 2024
            avahi                 | i|            0.8|    27|   Solus|14 Oct 2024
            baobab                | i|           46.0|    27|   Solus|14 Oct 2024
        """
        output = self.run_cli("list-installed", "--install-info")

        regexp = re.compile(
            r"^(?P<package_id>\S+)\s+\|\.+\|\s+(?P<version>\.+)\|\.+\|\.+\|\.+$"
        )

        for package in output.splitlines()[:-2]:
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ eopkg --no-color list-upgrades --install-info
            Package Name          |St|        Version|  Rel.|  Distro|       Date
            =====================================================================
            adwaita-icon-theme   | i|           46.2|    28|   Solus|14 Oct 2024
            appstream-data       | i|             49|    51|   Solus|14 Oct 2024
            at-spi2              | i|         2.52.0|    44|   Solus|14 Oct 2024
            baobab               | i|           46.0|    27|   Solus|14 Oct 2024
        """
        output = self.run_cli("list-upgrades", "--install-info")

        regexp = re.compile(
            r"^(?P<package_id>\S+)\s+\|\.+\|\s+(?P<version>\.+)\|\.+\|\.+\|\.+$"
        )

        for package in output.splitlines()[:-2]:
            match = regexp.match(package)
            if match:
                package_id, installed_version = match.groups()
                yield self.package(id=package_id, installed_version=installed_version)

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not supports exact matching.

        Naked search without parameters is the same as extended search with all filtering
        parameters (i.e. ``--name --summary --description``):

        .. code-block:: shell-session

            $ eopkg --no-color search firefox
            gjs-dbginfo                 - Debug symbols for gjs
            bleachbit                   - BleachBit frees disk space and maintains privacy
            firefox                     - Firefox web browser
            eid-mw-firefox              - Belgian eID add-on for Mozilla Firefox
            gjs                         - GNOME JavaScript
            font-fira-ttf               - Mozilla's new typeface, used in Firefox OS
            geckodriver                 - WebDriver for Firefox
            firefox-dbginfo             - Debug symbols for firefox
            nvidia-vaapi-driver-dbginfo - Debug symbols for nvidia-vaapi-driver
            font-clear-sans-ttf         - Clear Sans Fonts - TrueType
            gjs-devel                   - Development files for gjs
            geckodriver-dbginfo         - Debug symbols for geckodriver

            $ eopkg --no-color search firefox --name --summary --description
            gjs-dbginfo                 - Debug symbols for gjs
            bleachbit                   - BleachBit frees disk space and maintains privacy
            firefox                     - Firefox web browser
            eid-mw-firefox              - Belgian eID add-on for Mozilla Firefox
            gjs                         - GNOME JavaScript
            font-fira-ttf               - Mozilla's new typeface, used in Firefox OS
            geckodriver                 - WebDriver for Firefox
            firefox-dbginfo             - Debug symbols for firefox
            nvidia-vaapi-driver-dbginfo - Debug symbols for nvidia-vaapi-driver
            font-clear-sans-ttf         - Clear Sans Fonts - TrueType
            gjs-devel                   - Development files for gjs
            geckodriver-dbginfo         - Debug symbols for geckodriver

        For default search on package name only, we rescript filtering to ``--name`` only:

        .. code-block:: shell-session

            $ eopkg --no-color search firefox --name
            firefox         - Firefox web browser
            eid-mw-firefox  - Belgian eID add-on for Mozilla Firefox
            firefox-dbginfo - Debug symbols for firefox
        """
        # Extended search is the default behavior.
        arg = ""
        # Non-extended search restrict matching to package name only.
        if not extended:
            arg = "--name"

        output = self.run_cli("search", arg, query)

        regexp = re.compile(r"^(?P<package_id>\S+)\s+- (?P<description>\.+)$")

        for package_id, description in regexp.findall(output):
            yield self.package(id=package_id, description=description)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sudo eopkg --no-color install --yes-all 0ad
            Warning: Updates available, checking reverse dependencies of runtime dependencies for safety.
            Following packages will be installed:
            0ad          0ad-data         assimp           at-spi2             baobab             breeze-icons      budgie-control-center  budgie-desktop      dav1d                  enet                   evolution-data-server       ffmpeg
            file-roller  firefox          fmt              fontconfig          gcr-4              gloox             gnome-calculator       gnome-calendar      gnome-online-accounts  gnome-settings-daemon  gnome-system-monitor        gnome-terminal
            gvfs         harfbuzz         ibus             kf6-karchive        kf6-kauth          kf6-kbookmarks    kf6-kcodecs            kf6-kcolorscheme    kf6-kcompletion        kf6-kconfig            kf6-kconfigwidgets          kf6-kcoreaddons
            kf6-kcrash   kf6-kdbusaddons  kf6-kded         kf6-kdoctools       kf6-kglobalaccel   kf6-kguiaddons    kf6-ki18n              kf6-kiconthemes     kf6-kio                kf6-kitemviews         kf6-kjobwidgets             kf6-knotifications
            kf6-kparts   kf6-kservice     kf6-kwallet      kf6-kwidgetsaddons  kf6-kwindowsystem  kf6-kxmlgui       kf6-solid              kpmcore             ldb                    libadwaita             libarchive                  libass
            libcheese    libgtk-4         libgtkmm-4       libgtksourceview5   libheif            libpng            libportal              libportal-gtk4      libreoffice-common     librsvg                libsodium                   libtiff
            libtool      libvte           libwebkit-gtk41  libwebkit-gtk6      lzo                mesalib           miniupnpc              nautilus-extension  nemo                   network-manager        networkmanager-openconnect  openconnect
            pipewire     pipewire-lib     pixman           poppler             poppler-utils      postgresql-libpq  python-pysmbc          qt6-base            qt6-declarative        qt6-multimedia         qt6-quick3d                 qt6-quicktimeline
            qt6-wayland  rav1e            rhythmbox        samba               sdl2               svt-av1           thunderbird            wayland             xapp                   xmlsec1                xorg-server                 xorg-xwayland
            xreader      xviewer          zenity
            Total size of package(s): 1.94 GB
            Downloading 1 / 111
            Package ldb found in repository Solus
            ldb-2.8.2-31-1-x86_64.eopkg    (137.0 KB)100%      0.00 --/- [--:--:--] [complete]
            (...)
            Package 0ad-data found in repository Solus
            0ad-data-0.0.26a-10-1-x86_64.eopkg (1.4 GB) 39%
            (...)
        """
        return self.run_cli("install", "--yes-all", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ sudo eopkg --no-color upgrade --yes-all
        """
        return self.build_cli("upgrade", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages (default) or only the one provided
        as parameter.

        .. code-block:: shell-session

            $ sudo eopkg --no-color upgrade --yes-all xz
            Updating repositories
            Updating repository: Solus
            eopkg-index.xml.xz.sha1sum     (40.0  B)100%      0.00 --/- [--:--:--] [complete]
            Solus repository information is up-to-date.
            Warning: Safety switch forces the installation of following packages:
            os-release
            Warning: Safety switch forces the upgrade of following packages:
            bash    bash-completion  brotli   eopkg    gawk            glib2    glibc         gobject-introspection  hwdata  json-c   libcap2  libdw
            libelf  libjson-glib     libnspr  libnss   libpipeline     libssh2  libunistring  lvm2                   lzip    ncurses  nghttp2  nghttp3
            pisi    readline         sqlite3  systemd  wireless-regdb  xz
            Total size of package(s): 55.40 MB
            Warning: There are extra packages due to dependencies.
            Downloading 1 / 32
            Package ncurses found in repository Solus
            ncurses-6.5.20241006-29-1-x86_64.eopkg (767.0 KB)100%      0.00 --/- [--:--:--] [complete]
            (...)
            [✓] Syncing filesystems                                                success
            [✓] Updating dynamic library cache                                     success
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [✓] Updating hwdb                                                      success
            [✓] Updating system users                                              success
            [✓] Updating systemd tmpfiles                                          success
            [✓] Reloading systemd configuration                                    success
            [ ] Re-starting vendor-enabled .socket units                           skipped
            [ ] Re-executing systemd                                               skipped
            [✓] Compiling glib-schemas                                             success
            [✓] Creating GIO modules cache                                         success
            [✓] Updating manpages database                                         success
            [✓] Reloading udev rules                                               success
            [✓] Applying udev rules                                                success
        """
        return self.build_cli("upgrade", "--yes-all", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ sudo eopkg --no-color remove --yes-all firefox
            The following list of packages will be removed
            in the respective order to satisfy dependencies:
            firefox
            Removing package firefox
            Rebuilding the FilesDB...
            Adding packages to FilesDB /var/lib/eopkg/info/files.db:
            ................
            847 packages added in total.
            Done rebuilding FilesDB (version: 3)
            Removed firefox
            [✓] Syncing filesystems                                                success
            [✓] Updating dynamic library cache                                     success
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Updating clr-boot-manager                                          skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Registering QoL migration on next boot                             skipped
            [ ] Re-starting vendor-enabled .socket units                           skipped
            [ ] Re-executing systemd                                               skipped
            [✓] Updating icon theme cache: hicolor                                 success
            [✓] Updating desktop database                                          success
            [✓] Updating manpages database                                         success
        """
        return self.run_cli("remove", "--yes-all", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ sudo --no-color eopkg update-repo
            Updating repository: Solus
            eopkg-index.xml.xz.sha1sum  (40.0  B)100%   0.00 --/- [--:--:--] [complete]
            eopkg-index.xml.xz           (3.1 MB)100%  87.40 KB/s [00:00:34] [complete]
            Package database updated.
        """
        self.run_cli("update-repo", sudo=True)

    def cleanup(self) -> None:
        """Removes things we don't need anymore:
        - orphaned packages,
        - outdated package locks
        - package cache and package manager cache

        .. code-block:: shell-session

            $ sudo eopkg --no-color remove-orphans --yes-all
            $ sudo eopkg --no-color clean
            $ sudo eopkg --no-color delete-cache
        """
        self.run_cli("remove-orphans", "--yes-all", sudo=True)
        self.run_cli("clean", sudo=True)
        self.run_cli("delete-cache", sudo=True)
