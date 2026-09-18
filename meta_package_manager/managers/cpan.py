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

import os
import re
from pathlib import Path
from typing import ClassVar

from extra_platforms import ALL_PLATFORMS

from ..capabilities import version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class CPAN(PackageManager):
    """The cpan client of the Comprehensive Perl Archive Network.

    The tracked version is CPAN.pm's library version, not the cpan script version
    printed on the same line.

    Installs may require `sudo` when using the system Perl; `local::lib` gives
    user-local installs instead. The write operations carry dormant privileged
    markers: `--sudo` or a `sudo = true` override escalates them, while nothing
    escalates by default. cpan cannot uninstall a module, so no remove operation
    is declared.

    ```{caution}
    Perl's core modules (`warnings`, `feature`, `POSIX`, `B`, and the like) exist
    only inside Perl itself, with no standalone CPAN distribution, so their
    versions are tied to whichever Perl you run. `cpan -O` reports them as outdated
    whenever that Perl trails the newest one CPAN has indexed, yet `cpan -u` can
    never upgrade them in place, since only a newer Perl carries newer core
    modules. `mpm` relays both faithfully. This holds for any Perl, whether the
    macOS system one or a Homebrew install.

    On the macOS system Perl at `/usr/bin/perl`, that Perl sits on the sealed,
    read-only system volume and cannot be replaced even with `sudo`, so the list
    never clears.

    With a writable, user-controlled Perl ahead on your `PATH` (via
    `brew install perl`, since `mpm` drives whichever `cpan` comes first), the
    list does clear, but on a recurring delay: each yearly Perl release reaches
    CPAN before Homebrew publishes its bottle, so for a few weeks `cpan -O` flags
    the new release's core modules as outdated against your current ones. Perl
    `5.44.0`, released 2026-07-15, opened one such window against the `5.42`
    series Homebrew still bottled. Running `brew upgrade perl` once the new bottle
    lands moves your core modules to the new set and clears the list, until the
    next release reopens the window.

    If you do not track Perl modules with `cpan` at all,
    [disable the manager entirely](#selecting-and-configuring-cpan): set
    `cpan = false` in your mpm config, or pass `--no-cpan`. See
    [#1983](https://github.com/kdeldycke/meta-package-manager/issues/1983) for the
    original report.
    ```

    ```{note}
    On Debian and Ubuntu, Perl reaches its core modules through `@INC` directories
    that are symlinks, like `/usr/share/perl/5.40` pointing to `5.40.1`. `cpan -l`
    does not enter a directory it is given as a symlink, so it lists none of those
    modules, while `cpan -O` still reports them as outdated. `mpm` therefore runs
    `cpan -l` a second time with the resolved directories in `PERL5LIB`, and adds
    the modules that only this second run finds.
    ```
    """

    name = "Perl CPAN"

    homepage_url = "https://www.cpan.org"
    repository_url = "https://github.com/andk/cpanpm"
    wikipedia_url = "https://en.wikipedia.org/wiki/CPAN"
    logo = "perl"

    keywords = ("perl",)

    platforms = ALL_PLATFORMS

    requirement = ">=1.64"

    extra_env: ClassVar = {"PERL_MM_USE_DEFAULT": "1"}
    """Suppress the interactive configuration cpan may launch on first run."""

    version_cli_options = ("-v",)

    version_regexes = (r"CPAN\.pm\s+version\s+(?P<version>\S+)",)
    """Read the CPAN.pm version, the meaningful one, rather than the script's.

    ```{code-block} shell-session

    $ cpan -v
    Loading internal logger. Log::Log4perl recommended for better logging
    >(info): /usr/bin/cpan script version 1.678, CPAN.pm version 2.36
    ```
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\t(?:undef|(?P<installed_version>\S+))$",
    )
    """One `Module<TAB>version` row of `cpan -l`.

    A module with no version reports the literal `undef`, which the alternation
    keeps out of the version group, so the module is yielded version-less.
    """

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>\S+)\s{2,}(?P<installed_version>\d+\.\d+)"
        r"\s{2,}(?P<latest_version>\d+\.\d+)$",
    )
    """One row of the `cpan -O` report.

    App::Cpan prints each row with `printf "%-40s  %.4f  %.4f\\n"`, so a real row
    separates its columns by at least two spaces and both versions are numeric.
    Both halves of that shape are required, because a bare three-token match also
    catches the progress line CPAN::FTP prints while it refreshes its index,
    `Fetching with HTTP::Tiny:`. The banner, the `Reading` line, the indented
    `Database was generated` line, the column header and the dashed separator
    fail on the same two counts.
    """

    _INC_PROBE = 'print "$_\\n" for @INC'
    """Perl one-liner printing `@INC`, one directory per line."""

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed modules.

        ```{code-block} shell-session

        $ cpan -l
        Loading internal logger. Log::Log4perl recommended for better logging
        Glib	1.3294
        Cairo	1.109
        Clone	0.47
        Text::CharWidth	0.04
        Text::Iconv	1.7
        HTML::TokeParser	3.83
        HTML::PullParser	3.83
        HTML::Entities	3.83
        HTML::Parser	3.83
        HTML::LinkExtor	3.83
        HTML::Filter	3.83
        HTML::HeadParser	3.83
        Net::SSLeay	1.94
        Net::DBus	1.2.0
        Net::DBus::Error	undef
        Net::DBus::Callback	undef
        Net::DBus::Reactor	undef
        ```

        `cpan -l` walks each `@INC` directory with `File::Find`, which does not
        enter a starting directory that is a symlink. When
        `_symlinked_inc_targets()` finds such directories, a second run puts their
        resolved paths in `PERL5LIB`, which `cpan -l` then walks too:

        ```{code-block} console

        $ PERL5LIB=/usr/share/perl/5.40.1:/usr/lib/aarch64-linux-gnu/perl/5.40.1 cpan -l
        Loading internal logger. Log::Log4perl recommended for better logging
        UNIVERSAL	1.17
        version	0.9930
        English	1.11
        _charnames	1.50
        fields	2.25
        ```

        From that second run, only the modules the first one missed are kept.
        `PERL5LIB` puts the resolved directories ahead of the rest of `@INC`, and
        Debian's `perl-base` package ships a second copy of some core modules, like
        `strict` and `warnings`: keeping every row would list those modules twice.

        ```{todo}
        Drop the second run, with `_sibling_perl()` and `_symlinked_inc_targets()`,
        once a fixed `cpan -l` reaches the Perl that Debian and Ubuntu ship. Reported
        upstream as [andk/cpanpm#202](https://github.com/andk/cpanpm/issues/202).
        ```
        """
        listed: set[str] = set()
        for package in self.parse_regex_lines(
            self._INSTALLED_REGEXP, self.run_cli("-l")
        ):
            listed.add(package.id)
            yield package

        targets = self._symlinked_inc_targets()
        if not targets:
            return
        # PERL5LIB replaces the inherited value, so the user's own entries (a
        # local::lib tree) are kept after the resolved directories.
        search_path = [*targets]
        if os.environ.get("PERL5LIB"):
            search_path.append(os.environ["PERL5LIB"])
        output = self.run_cli(
            "-l",
            override_extra_env={
                **self.extra_env,
                "PERL5LIB": os.pathsep.join(search_path),
            },
        )
        for package in self.parse_regex_lines(self._INSTALLED_REGEXP, output):
            if package.id not in listed:
                listed.add(package.id)
                yield package

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated modules.

        ```{code-block} shell-session

        $ cpan -O
        Loading internal logger. Log::Log4perl recommended for better logging
        Reading '/home/user/.cpan/Metadata'
          Database was generated on Wed, 16 Sep 2026 14:17:02 GMT
        Module Name                                Local    CPAN
        -------------------------------------------------------------------------
        App::Cpan                                 1.6780  1.6790
        App::Prove                                3.4800  3.5200
        App::Prove::State                         3.4800  3.5200
        App::Prove::State::Result                 3.4800  3.5200
        App::Prove::State::Result::Test           3.4800  3.5200
        Archive::Tar                              3.0200  3.1200
        Archive::Tar::Constant                    3.0200  3.1200
        ```
        """
        output = self.run_cli("-O")
        yield from self.parse_regex_lines(self._OUTDATED_REGEXP, output)

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one module.

        A bare module name installs it.

        ```{code-block} shell-session

        $ cpan Try::Tiny
        ```
        """
        return self.run_cli(package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all modules.

        ```{code-block} shell-session

        $ cpan -u
        ```
        """
        return self.build_cli("-u", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one module.

        ```{code-block} shell-session

        $ cpan -i Try::Tiny
        ```
        """
        return self.build_cli("-i", package_id, sudo=True)

    def _sibling_perl(self) -> Path | None:
        """The `perl` installed beside the resolved `cpan`, or `None`.

        Perl installs its `cpan` script in the same directory as the `perl` binary:
        `installscript` and `installbin` are both `/usr/bin` on Ubuntu and on macOS.
        That binary's `@INC` is therefore the one `cpan -l` walks.
        """
        if self.cli_path is None:
            return None
        for name in ("perl", "perl.exe"):
            candidate = self.cli_path.parent / name
            if candidate.is_file():
                return candidate
        return None

    def _symlinked_inc_targets(self) -> tuple[str, ...]:
        """Resolved paths of the `@INC` directories `cpan -l` cannot walk.

        An `@INC` entry that is a symlink to a directory is resolved, unless another
        entry already reaches its target. The result is empty when no `perl` sits
        beside `cpan` to ask.

        ```{code-block} console

        $ perl -e 'print "$_\\n" for @INC'
        /etc/perl
        /usr/local/lib/aarch64-linux-gnu/perl/5.40.1
        /usr/local/share/perl/5.40.1
        /usr/lib/aarch64-linux-gnu/perl5/5.40
        /usr/share/perl5
        /usr/lib/aarch64-linux-gnu/perl-base
        /usr/lib/aarch64-linux-gnu/perl/5.40
        /usr/share/perl/5.40
        /usr/local/lib/site_perl
        ```
        """
        perl = self._sibling_perl()
        if perl is None:
            return ()
        output = self.run_cli(
            "-e",
            self._INC_PROBE,
            override_cli_path=perl,
            auto_extra_env=False,
        )
        walked: set[Path] = set()
        linked: list[Path] = []
        for line in output.splitlines():
            entry = Path(line)
            if not entry.is_absolute():
                continue
            if entry.is_symlink():
                linked.append(entry)
            elif entry.is_dir():
                walked.add(entry.resolve())
        targets: list[str] = []
        for entry in linked:
            target = entry.resolve()
            if target.is_dir() and target not in walked and str(target) not in targets:
                targets.append(str(target))
        return tuple(targets)
