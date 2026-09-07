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
from html import unescape

from extra_platforms import LINUX_LIKE

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class EOPKG(PackageManager):
    """Solus' eopkg package manager, a PiSi fork.

    `installed` and `outdated` parse eopkg's fixed-width, `|`-delimited
    status table; the column regex requires that pipe structure, so the header
    and `===` separator rows fall through. `--no-color` is forced to keep
    the output free of ANSI escapes.

    Mutating operations pass `--yes-all` to auto-confirm eopkg's prompts so
    they run unattended.

    ```{note}
    eopkg `4.x` is a [Nuitka](https://nuitka.net) onefile bundle, and the Python
    it carries reads its stdout encoding from the locale alone. Under `C` or
    `POSIX` that encoding is `ascii`. The first summary holding a character it
    cannot encode then aborts the command with
    `Error: System error. Program terminated.` and exit `1`, after a truncated
    listing. `list-upgrades` and `list-available` write every summary raw, so
    either `Cap’n Proto` or `ImageMagick®` stops them; `search` escapes `®` but
    not `’`, so only the first stops it.

    No `extra_env` pins the locale here, because mpm never reaches that state.
    [PEP 538](https://peps.python.org/pep-0538/) coercion exports
    `LC_CTYPE=C.UTF-8` from mpm's own interpreter, and eopkg inherits it. A
    shell exports nothing, which is why the same command fails by hand and
    works through mpm. Measured on Solus `4.9` with eopkg `4.4.0`.
    ```
    """

    name = "Solus eopkg"

    homepage_url = "https://github.com/getsolus/eopkg/"
    logo = "solus"

    keywords = ("solus",)

    platforms = LINUX_LIKE

    default_sudo = True

    requirement = ">=3.2.0"

    pre_args = ("--no-color",)

    _LIST_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+\|.+?\|\s*(?P<installed_version>\S+)"
        r"\s*\|.+?\|.+?\|.+$",
    )
    _SEARCH_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s+- (?P<description>.+)$",
        re.MULTILINE,
    )

    version_regexes = (r"eopkg\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ eopkg --version
    eopkg 4.4.0
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ eopkg --no-color list-installed --install-info
        Package Name          |St|        Version|  Rel.|  Distro|             Date
        ===========================================================================
        aalib                 | i|        1.4.0_5|     9|   Solus|07 Sep 2026 10:08
        abseil-cpp            | i|     20260107.1|    11|   Solus|07 Sep 2026 10:08
        accounts-qml-module   | i|            0.7|     6|   Solus|07 Sep 2026 10:08
        accountsservice       | i|        23.13.9|    38|   Solus|07 Sep 2026 10:08
        acl                   | i|          2.3.2|    22|   Solus|07 Sep 2026 10:08
        alsa-firmware         | i|          1.2.4|     8|   Solus|07 Sep 2026 10:08
        alsa-lib              | i|         1.2.14|    41|   Solus|07 Sep 2026 10:08
        alsa-plugins          | i|         1.2.12|    26|   Solus|07 Sep 2026 10:08
        alsa-ucm-conf         | i|         1.2.13|     1|   Solus|07 Sep 2026 10:08
        alsa-utils            | i|         1.2.13|    29|   Solus|07 Sep 2026 10:08
        anthy                 | i|          9100h|     4|   Solus|07 Sep 2026 10:08
        aom                   | i|         3.12.1|    26|   Solus|07 Sep 2026 10:08
        appstream             | i|          1.1.2|    17|   Solus|07 Sep 2026 10:08
        appstream-catalog     | i|       20260417|    52|   Solus|07 Sep 2026 10:08
        appstream-qt6         | i|          1.1.2|    17|   Solus|07 Sep 2026 10:08
        argon2                | i|       20190702|     6|   Solus|07 Sep 2026 10:08
        ```

        The listing carries no footer: its last line is a package, so every line
        after the two header rows is one. A package whose name overflows the
        first column pushes the pipe right instead of being truncated, which is
        why the regex anchors on the pipes rather than on fixed offsets.
        """
        output = self.run_cli("list-installed", "--install-info")

        yield from self.parse_regex_lines(self._LIST_REGEXP, output)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        `--install-info` describes the package as it stands on the system, so the
        version column is the *installed* one and the upgrade target is absent.
        eopkg reports the candidate version through `info` alone, one package per
        invocation, so `latest_version` is left unset rather than paid for with
        one subprocess per outdated package.

        ```{code-block} shell-session

        $ eopkg --no-color list-upgrades --install-info
        Package Name          |St|        Version|  Rel.|  Distro|             Date
        ===========================================================================
        acl                  | i|          2.3.2|    22|   Solus|07 Sep 2026 10:08
        alsa-lib             | i|         1.2.14|    41|   Solus|07 Sep 2026 10:08
        alsa-ucm-conf        | i|         1.2.13|     1|   Solus|07 Sep 2026 10:08
        alsa-utils           | i|         1.2.13|    29|   Solus|07 Sep 2026 10:08
        anthy                | i|          9100h|     4|   Solus|07 Sep 2026 10:08
        aom                  | i|         3.12.1|    26|   Solus|07 Sep 2026 10:08
        appstream            | i|          1.1.2|    17|   Solus|07 Sep 2026 10:08
        ```
        """
        output = self.run_cli("list-upgrades", "--install-info")

        yield from self.parse_regex_lines(self._LIST_REGEXP, output)

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{caution}
        Search does not supports exact matching.
        ```

        Naked search without parameters is the same as extended search with all filtering
        parameters (i.e. `--name --summary --description`):

        ```{code-block} console

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
        ```

        For default search on package name only, we rescript filtering to `--name` only:

        ```{code-block} shell-session

        $ eopkg --no-color search --name htop
        htop            - htop (interactive process viewer for Linux)
        htop-dbginfo    - Debug symbols for htop
        neohtop         - Blazing-fast system monitoring for your desktop.
        neohtop-dbginfo - Debug symbols for neohtop
        ```

        Summaries reach this listing exactly as the repository index stores them,
        character references included, where `list-available` resolves the same
        text. So `imagemagick` describes itself as `ImageMagick&#xAE; suite` here
        and `ImageMagick® suite` there, and {func}`html.unescape` reconciles the
        two. Measured against eopkg `4.4.0`.

        ```{code-block} shell-session

        $ eopkg --no-color search --name imagemagick
        imagemagick         - ImageMagick&#xAE; suite to create, edit, compose, or convert bitmap images
        imagemagick-dbginfo - Debug symbols for imagemagick
        imagemagick-devel   - Development files for imagemagick
        imagemagick-docs    - Documentation for imagemagick
        ```
        """
        # Extended search is the default behavior, so it adds no flag at all:
        # an empty string would be passed through as an empty argv element.
        # Non-extended search restricts matching to the package name.
        args = () if extended else ("--name",)

        output = self.run_cli("search", *args, query)

        for package_id, description in self._SEARCH_REGEXP.findall(output):
            yield self.package(id=package_id, description=unescape(description))

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

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
        ```
        """
        return self.run_cli("install", "--yes-all", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ sudo eopkg --no-color upgrade --yes-all
        ```
        """
        return self.build_cli("upgrade", "--yes-all", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

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
        ```
        """
        return self.build_cli("upgrade", "--yes-all", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

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
        ```
        """
        return self.run_cli("remove", "--yes-all", package_id, sudo=True)

    def sync(self) -> None:
        """Sync package metadata.

        ```{code-block} shell-session

        $ sudo eopkg --no-color update-repo
        Updating repository: Solus
        eopkg-index.xml.xz.sha1sum  (40.0  B)100%   0.00 --/- [--:--:--] [complete]
        eopkg-index.xml.xz           (3.1 MB)100%  87.40 KB/s [00:00:34] [complete]
        Package database updated.
        ```
        """
        self.run_cli("update-repo", sudo=True)

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore:
        - orphaned packages,
        - outdated package locks
        - package cache and package manager cache

        ```{code-block} shell-session

        $ sudo eopkg --no-color remove-orphans --yes-all
        $ sudo eopkg --no-color clean
        $ sudo eopkg --no-color delete-cache
        ```
        """
        self.run_cli("remove-orphans", "--yes-all", sudo=True)
        self.run_cli("clean", sudo=True)
        self.run_cli("delete-cache", sudo=True)
