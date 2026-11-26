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
from functools import cached_property
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
    escalates by default.

    Where cpan installs to a local::lib directory by default, `mpm outdated` and
    `mpm upgrade --all` skip the modules outside that directory: `cpan -u` would
    install a newer copy of each of them there, ahead of the copy of the system.
    An `INSTALL_BASE` in `PERL_MM_OPT`, which local::lib exports, sets this
    default. A Perl whose site directory the user cannot write to sets it too:
    there, the first run of CPAN.pm sets up local::lib in `~/perl5`. The system
    Perl of Arch Linux and of macOS is such a Perl. `mpm upgrade` still updates a
    module it names, and `mpm --sudo`, which runs `cpan -u` as root, turns the
    rule off.

    ```{caution}
    Perl's core modules (`warnings`, `feature`, `POSIX`, `B`, and the like) exist
    only inside Perl itself, with no standalone CPAN distribution, so their
    versions are tied to whichever Perl you run. `cpan -O` reports them as outdated
    whenever that Perl trails the newest one CPAN has indexed, yet `cpan -u` can
    never upgrade them in place, since only a newer Perl carries newer core
    modules. On a Perl that installs to its own site directory, `mpm` relays both
    faithfully. On a system Perl, the local::lib rule above keeps them out of
    `mpm outdated`, unless `mpm --sudo` turns the rule off.

    On the macOS system Perl at `/usr/bin/perl`, that Perl sits on the sealed,
    read-only system volume and cannot be replaced even with `sudo`, so under
    `mpm --sudo` the list never clears.

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
    [disable the manager entirely](#configuration): set `cpan = false` in your
    mpm config, or pass `--no-cpan`. See
    [#1983](https://github.com/kdeldycke/meta-package-manager/issues/1983) for the
    original report.
    ```
    """

    # cpan cannot uninstall a module, which is why no `remove` operation is
    # declared.
    #
    # On Debian and Ubuntu, Perl reaches its core modules through `@INC`
    # directories that are symlinks, like `/usr/share/perl/5.40` pointing to
    # `5.40.1`. `cpan -l` does not enter a directory it is given as a symlink,
    # so it lists none of those modules, while `cpan -O` still reports them
    # as outdated. `mpm` therefore runs `cpan -l` a second time with the
    # resolved directories in `PERL5LIB`, and adds the modules that only this
    # second run finds.
    operation_notes: ClassVar = {
        "remove": "CPAN's client cannot uninstall a module at all.",
        "outdated": (
            "Lists only the modules of the local::lib directory when cpan installs "
            "there by default."
        ),
        "upgrade_all": (
            "Upgrades only the modules of the local::lib directory when cpan installs "
            "there by default."
        ),
    }

    name = "Perl CPAN"

    homepage_url = "https://www.cpan.org"
    documentation_url = "https://metacpan.org/pod/CPAN"
    repository_url = "https://github.com/andk/cpanpm"
    wikipedia_url = "https://en.wikipedia.org/wiki/CPAN"
    logo = "perl"

    keywords = ("perl",)

    platforms = ALL_PLATFORMS

    privileged_operations = frozenset({"install", "upgrade", "upgrade_all"})

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

    _CONFIG_PROBE = 'print "$Config{$_}\\n" for qw(installsitelib version archname)'
    """Perl one-liner printing the site directory, the version and the architecture.

    It runs with `-MConfig`.
    """

    _INSTALL_BASE_REGEXP = re.compile(r"""\bINSTALL_BASE=("[^"]*"|'[^']*'|\S+)""")
    """The `INSTALL_BASE` argument in `PERL_MM_OPT`, quoted or not."""

    _SHEBANG_REGEXP = re.compile(rb"^#!\s*(\S+)")
    """The interpreter path of a script's shebang line."""

    @cached_property
    def _perl_config(self) -> tuple[str, str, str] | None:
        """The site directory, version and architecture of the Perl of `cpan`.

        `None` when `_perl()` finds no `perl`, or when the probe prints
        something else. The probe loads no CPAN.pm code. On Omarchy `4.5.0`:

        ```{code-block} console

        $ perl -MConfig -e 'print "$Config{$_}\\n" for qw(installsitelib version archname)'
        /usr/share/perl5/site_perl
        5.44.0
        aarch64-linux-thread-multi
        ```
        """  # noqa: E501
        perl = self._perl()
        if perl is None:
            return None
        output = self.run_cli(
            "-MConfig",
            "-e",
            self._CONFIG_PROBE,
            override_cli_path=perl,
            auto_extra_env=False,
            auto_extra_args=False,
            force_exec=True,
        )
        lines = output.splitlines()
        if len(lines) != 3:
            return None
        site_lib, version, archname = lines
        return site_lib, version, archname

    def _probe_user_install_dir(self) -> Path | None:
        """The local::lib directory, if cpan installs there by default, else `None`.

        The hook behind
        {attr}`~meta_package_manager.manager.PackageManager.user_install_dir`.
        Perl's installers decide in this order:

        1. An `INSTALL_BASE` in `PERL_MM_OPT` wins: `ExtUtils::MakeMaker`
           installs there, and local::lib exports the variable. On Omarchy
           `4.5.0`, the first run of CPAN.pm added it to `~/.bashrc`.
        2. Without it, cpan installs to the site directory of its Perl. When
           that directory exists but the user cannot write to it, the first run
           of CPAN.pm sets up local::lib in the directory that
           `PERL_LOCAL_LIB_ROOT` names first, else `~/perl5`. Root owns the site
           directory of the system Perl on Arch Linux and on macOS.

        ```{code-block} console

        $ echo $PERL_MM_OPT
        INSTALL_BASE=/home/user/perl5
        ```

        The probe reads the defaults of the current user.
        """
        env = {**os.environ, **(self.extra_env or {})}
        install_base = self._INSTALL_BASE_REGEXP.search(env.get("PERL_MM_OPT") or "")
        if install_base:
            return Path(install_base[1].strip("\"'")).expanduser()
        config = self._perl_config
        if config is None:
            return None
        site_lib = Path(config[0])
        if not site_lib.exists() or os.access(site_lib, os.W_OK):
            return None
        root = (env.get("PERL_LOCAL_LIB_ROOT") or "").split(os.pathsep)[0]
        return Path(root) if root else Path.home() / "perl5"

    def _packages_in(self, directory: Path) -> frozenset[str]:
        """Names of the modules with a `.pm` file in the local::lib `directory`.

        Perl reads a local::lib directory through `PERL5LIB`, which also adds the
        version and architecture subdirectories of `lib/perl5`. A file takes its
        name from the deepest of these that holds it, the way `cpan -l` names it
        from its `@INC` entry. No `cpan` command runs. On Omarchy `4.5.0`, the
        first run of CPAN.pm left two modules there:

        ```{code-block} console

        $ find ~/perl5/lib/perl5 -name '*.pm'
        /home/user/perl5/lib/perl5/lib/core/only.pm
        /home/user/perl5/lib/perl5/local/lib.pm
        ```
        """
        base = directory / "lib" / "perl5"
        if not base.is_dir():
            return frozenset()
        roots = [base]
        if self._perl_config is not None:
            _site_lib, version, archname = self._perl_config
            roots = [
                base / version / archname,
                base / version,
                base / archname,
                base,
            ]
        modules = set()
        for path in base.rglob("*.pm"):
            root = next(root for root in roots if path.is_relative_to(root))
            modules.add("::".join(path.relative_to(root).with_suffix("").parts))
        return frozenset(modules)

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
        Drop the second run, with `_symlinked_inc_targets()`, once a fixed `cpan -l`
        reaches the Perl that Debian and Ubuntu ship. Reported upstream as
        [andk/cpanpm#202](https://github.com/andk/cpanpm/issues/202).
        ```
        """
        listed: set[str] = set()
        for package in self.parse_regex_lines(
            self._INSTALLED_REGEXP, self.run_cli("-l", auto_extra_args=True)
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
            auto_extra_args=True,
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

        Where cpan installs to a local::lib directory by default (see
        `_probe_user_install_dir`), `cpan -O` runs with the `lib/perl5` of that
        directory first in `PERL5LIB`, so it reads the versions installed there.
        """
        user_dir = self.user_install_dir
        override_extra_env = None
        if user_dir is not None:
            user_lib = str(user_dir / "lib" / "perl5")
            search_path = os.environ.get("PERL5LIB", "").split(os.pathsep)
            if user_lib not in search_path:
                override_extra_env = {
                    **(self.extra_env or {}),
                    "PERL5LIB": os.pathsep.join(filter(None, [user_lib, *search_path])),
                }

        output = self.run_cli("-O", override_extra_env=override_extra_env)
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

    def _perl(self) -> Path | None:
        """The `perl` that runs the resolved `cpan`, or `None`.

        That binary's `@INC` is the one `cpan -l` walks. The interpreter that the
        shebang of the `cpan` script names comes first, when it is an absolute
        path to a `perl` file. Arch Linux installs `cpan` to `/usr/bin/core_perl`,
        apart from its `perl`:

        ```{code-block} console

        $ head -1 /usr/bin/core_perl/cpan
        #!/usr/bin/perl
        ```

        Else the `perl` beside `cpan`: Perl installs its `cpan` script in the same
        directory as the `perl` binary when `installscript` and `installbin` match,
        as they do on Ubuntu and on macOS. A `#!/usr/bin/env perl` shebang names no
        path, so it takes this branch too.
        """
        if self.cli_path is None:
            return None
        try:
            with self.cli_path.open("rb") as script:
                first_line = script.readline(256)
        except OSError:
            first_line = b""
        shebang = self._SHEBANG_REGEXP.match(first_line)
        if shebang:
            interpreter = Path(os.fsdecode(shebang[1]))
            if (
                interpreter.is_absolute()
                and interpreter.name.startswith("perl")
                and interpreter.is_file()
            ):
                return interpreter
        for name in ("perl", "perl.exe"):
            candidate = self.cli_path.parent / name
            if candidate.is_file():
                return candidate
        return None

    def _symlinked_inc_targets(self) -> tuple[str, ...]:
        """Resolved paths of the `@INC` directories `cpan -l` cannot walk.

        An `@INC` entry that is a symlink to a directory is resolved, unless another
        entry already reaches its target. The result is empty when `_perl()` finds
        no `perl` to ask.

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
        perl = self._perl()
        if perl is None:
            return ()
        output = self.run_cli(
            "-e",
            self._INC_PROBE,
            override_cli_path=perl,
            auto_extra_env=False,
            auto_extra_args=False,
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
