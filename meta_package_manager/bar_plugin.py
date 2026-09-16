#!/usr/bin/env python3
# <xbar.title>Meta Package Manager</xbar.title>
# <xbar.version>8.0.0.dev0</xbar.version>
# <xbar.author>Kevin Deldycke</xbar.author>
# <xbar.author.github>kdeldycke</xbar.author.github>
# <xbar.desc>List outdated packages and manage upgrades.</xbar.desc>
# <xbar.dependencies>python,mpm</xbar.dependencies>
# <xbar.image>https://raw.githubusercontent.com/kdeldycke/meta-package-manager/refs/heads/main/docs/assets/xbar-submenu-table-rendering.png</xbar.image>
# <xbar.abouturl>https://mpm.run/bar-plugin/</xbar.abouturl>
# XXX Quotes around default values are required by SwiftBar, and optional in Xbar, which
# strips them. Unquoted, the variable is silently ignored by SwiftBar and never reaches
# its settings UI.
# <xbar.var>boolean(VAR_GROUP_BY_MANAGER="true"): Group each manager's packages into a section of its own.</xbar.var>
# <xbar.var>boolean(VAR_ALIGN_COLUMNS="true"): Centers versions around the arrow and aligns names in a monospaced font.</xbar.var>
# <xbar.var>number(VAR_MAX_VERSION_WIDTH="18"): Widest a version renders in a menu line, in characters. Longer ones are shortened with an ellipsis.</xbar.var>
# <xbar.var>string(VAR_MPM_OPTIONS=""): Extra options for every mpm call the plugin makes, placed before the subcommand.</xbar.var>
# XXX Font options are declared SwiftBar-only, as Xbar truncates a default value at its
# first `=` character. See: https://github.com/matryer/xbar/issues/832
# <swiftbar.var>string(VAR_DEFAULT_FONT=""): Font parameters for regular text.</swiftbar.var>
# <swiftbar.var>string(VAR_MONOSPACE_FONT="font=Menlo size=12"): Font parameters for monospace text. Used for table rendering and error messages.</swiftbar.var>
# XXX Only SwiftBar hides a plugin producing no output, so this is SwiftBar-only too.
# <swiftbar.var>boolean(VAR_ALWAYS_VISIBLE="true"): Keep the menu bar icon while no package is outdated and no manager reports an error.</swiftbar.var>
"""SwiftBar and Xbar plugin for Meta Package Manager (the {command}`mpm` CLI).

Default update cycle should be set to several hours so we have a chance to get
user's attention once a day. Higher frequency might ruin the system as all
checks are quite resource intensive, and Homebrew might hit GitHub's API calls
quota.

- [Xbar automatically bridge plugin options](https://xbarapp.com/docs/2021/03/14/variables-in-xbar.html) between its UI
  and environment variable on script execution.

- SwiftBar bridges them the same way since `2.1.0` added `xbar.var` support
  ([swiftbar/SwiftBar#472](https://github.com/swiftbar/SwiftBar/pull/472)).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from configparser import RawConfigParser
from functools import cached_property
from operator import attrgetter, methodcaller
from pathlib import Path
from shlex import shlex
from shutil import which
from subprocess import run
from textwrap import dedent
from typing import NamedTuple

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator


SWIFTBAR_MIN_VERSION = (2, 1, 0)
"""SwiftBar `2.1.0` fixes an issue with multiple parameters in the font strings.

The fix was first handed out as a `2.1.2`-labelled test build, a number that never
reached a release: the public train renumbered it down to `2.1.0`. Requiring the
build we validated on would lock the plugin out of every released SwiftBar.

See [swiftbar/SwiftBar#445](https://github.com/swiftbar/SwiftBar/issues/445).
"""

MPM_MIN_VERSION = (5, 0, 0)
"""Mpm v5.0.0 was the first version taking care of the complete layout rendering."""

INSTALL_ARGV = ("uv", "tool", "install", "--upgrade", "meta-package-manager")
"""Bootstrap command offered when no runnable `mpm` is found.

A global [`uv tool`](https://docs.astral.sh/uv/concepts/tools/) install, the
primary method of the [installation page](https://mpm.run/install/): it puts
`mpm` on the `PATH` of every shell, where a `pip install` would have buried it in
whichever interpreter happened to run this plugin. `--upgrade` makes the same
command serve the outdated-`mpm` case, so nothing pins the specifier to
{data}`MPM_MIN_VERSION`: the latest release always satisfies it, and Xbar mangles
a quoted `>=` specifier anyway (see
[matryer/xbar#831](https://github.com/matryer/xbar/issues/831)).

The GNOME Shell extension offers the same command from its own missing-`mpm`
menu, and `tests/test_gnome_extension.py` holds the two in sync.
"""

INSTALL_DOCS_URL = "https://mpm.run/install/"
"""Installation page, offered beside {data}`INSTALL_ARGV`.

`uv` may itself be missing, and is not the right answer everywhere: a
distribution package, Homebrew or a standalone binary all install `mpm` too.
"""

PLUGIN_DOCS_URL = "https://mpm.run/bar-plugin/"
"""Documentation of this plugin, linked from the About submenu.

The same address the `<xbar.abouturl>` header hands the host, which only
surfaces it in its own plugin browser and never in the menu.
"""

MPM_TIMEOUT = 60
"""Maximum duration in seconds the plugin lets any single `mpm` call run.

Passed as `--timeout` to every `mpm` invocation so the plugin is never at the
mercy of mpm's own per-operation defaults, which are tuned for interactive CLI use
and far too long for a background menubar refresh (120s for read-only queries, 500s
for state-changing operations like `sync`). A wedged package manager then fails
the whole refresh in a minute instead of freezing the menubar for several.
"""

VERSION_REGEX = re.compile(
    r"""
    .+                      # Any string
    \                       # A space
    version                 # The "version" string
    \                       # A space
    [^\.]*?                 # Any minimal (non-greedy) string without a dot
    (?P<release>
      (?P<version>[0-9]+(?:\.[0-9]+)+) # Version composed of numbers and dots
      [^\s\x1b]*            # Any suffix, stopping short of an ANSI escape
    )
    .*?                     # Any trailing string (ANSI codes, etc.)
    $                       # End of the string
    """,
    re.VERBOSE | re.MULTILINE,
)
"""Both readings of the version `mpm --version` prints, ANSI-colored or not.

`version` is the numeric part, `release` the whole token: a development build
spells `8.0.0.dev0+40ce0879`, and the suffix is what identifies the build.
"""


class Candidate(NamedTuple):
    """One way to run `mpm` found on the system, and what its version probe answered.

    `version` is the tuple compared against {data}`MPM_MIN_VERSION`, `release` the
    token as printed. The GNOME Shell extension's `probeMpm()` answers the same fields.
    """

    args: tuple[str, ...]
    runnable: bool = False
    up_to_date: bool = False
    version: tuple[int, ...] | None = None
    error: str | Exception | None = None
    release: str | None = None

    @property
    def rank(self) -> tuple[bool, bool, tuple[int, ...]]:
        """Sort key of {attr}`MPMPlugin.ranked_mpm`: runnable, then up to date, then
        the newest version.

        `error` and `release` stay out of it. Two exceptions do not compare, nor
        does a missing version against a found one, and either makes the sort raise.
        """
        return self.runnable, self.up_to_date, self.version or ()


class MPMPlugin:
    """Implements the minimal code necessary to locate and call the `mpm` CLI on the
    system.

    Once `mpm` is located, we can rely on it to produce the main output of the plugin.

    The output must supports both [Xbar dialect](https://github.com/matryer/xbar-plugins/blob/main/CONTRIBUTING.md#plugin-api)
    and [SwiftBar dialect](https://github.com/swiftbar/SwiftBar#plugin-api).
    """

    @staticmethod
    def getenv_str(var: str, default: str | None = None) -> str | None:
        """Utility to get environment variables.

        Note that all environment variables are strings. Always returns a lowered-case
        string.
        """
        value = os.environ.get(var, None)
        if value is None:
            return default
        return str(value).lower()

    @staticmethod
    def getenv_bool(var: str, default: bool = False) -> bool:
        """Utility to normalize boolean environment variables.

        Relies on [`configparser.RawConfigParser.BOOLEAN_STATES`](https://github.com/python/cpython/blob/3c298e2e385fc6f462abaada2fd680deb1a2b58e/Lib/configparser.py#L596-L597)
        to translate strings into boolean.
        """
        value = MPMPlugin.getenv_str(var)
        if value is None:
            return default
        return RawConfigParser.BOOLEAN_STATES[value]

    @staticmethod
    def getenv_int(var: str, default: int) -> int:
        """Utility to normalize integer environment variables.

        Falls back to the default on anything that is not a number, so a typo in
        a plugin setting degrades the layout instead of killing the menu.
        """
        value = MPMPlugin.getenv_str(var)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def normalize_params(font_string: str, valid_ids: set[str] | None = None) -> str:
        """Parse a multi-parameters string and return a normalized string.

        The string is expected to be a space-separated list of parameters, each
        parameter being a key/value pair separated by an equal sign.

        Only keeps the parameters that are in the `valid_ids` set and ignores the
        rest. By default, only `color`, `font` and `size` are kept.

        Multiple values for the same parameter will be deduplicated, and the last one
        will be kept.

        Available parameters are documented by both hosts:

        - [SwiftBar](https://github.com/swiftbar/SwiftBar?tab=readme-ov-file#parameters)
        - [Xbar](https://github.com/matryer/xbar-plugins/blob/main/CONTRIBUTING.md#parameters)
        """
        if not valid_ids:
            valid_ids = {"color", "font", "size"}
        params = {}

        # shlex yields `=` as a token of its own, so a value is whatever follows one.
        key = None
        after_separator = False
        for token in shlex(font_string):
            if token == "=":
                after_separator = True
            elif after_separator:
                if key and key in valid_ids:
                    params[key] = token
                after_separator = False
                key = None
            else:
                key = token

        return " ".join(f"{k}={v}" for k, v in params.items())

    @staticmethod
    def str_to_version(version_string: str | None) -> tuple[int, ...]:
        """Transforms a string into a tuple of integers representing a version."""
        if not version_string:
            return ()
        return tuple(map(int, version_string.strip().split(".")))

    @staticmethod
    def version_to_str(version_tuple: tuple[int, ...] | None) -> str:
        """Transforms a tuple of integers representing a version into a string."""
        if not version_tuple:
            return "None"
        return ".".join(map(str, version_tuple))

    @cached_property
    def align_columns(self) -> bool:
        """Centers each version pair around its arrow, and aligns package names.

        Set in a fixed-width font, which is what makes the padding measure
        equally. See
        {meth}`~meta_package_manager.bar_plugin_renderer.BarPluginRenderer.align_rows`
        for why the arrow is the axis.
        """
        return self.getenv_bool("VAR_ALIGN_COLUMNS", True)

    @cached_property
    def plugin_version(self) -> str:
        """Version this script advertises to its host.

        Read back from the `<xbar.version>` header rather than kept in a
        constant beside it: that header is the one place the number is
        written, both hosts parse it out of the source, and `bump-my-version`
        rewrites it on release. A second copy is a second thing to drift.
        """
        try:
            source = Path(__file__).read_text(encoding="UTF-8")
        except OSError:
            return "unknown"
        match = re.search(r"<xbar\.version>(?P<version>[^<]+)</xbar\.version>", source)
        return match.group("version") if match else "unknown"

    @cached_property
    def mpm_options(self) -> tuple[str, ...]:
        """Options spliced into every `mpm` call, after the plugin's own and before
        the subcommand, so a repeated single-value option like `--verbosity`
        takes the user's value.

        The version probe never takes them: a mistyped option then fails `sync`
        with mpm's own usage error, which the menu renders, rather than reading
        as a missing `mpm`. The menu's upgrade actions carry them too, since
        {class}`~meta_package_manager.bar_plugin_renderer.BarPluginRenderer`
        builds those inside the `outdated` call and inherits this environment.

        Read raw rather than through {meth}`getenv_str`, which lower-cases: a
        `--verbosity INFO` level and a path in `--config` both keep their case.
        Sourced from `VAR_MPM_OPTIONS`; the GNOME Shell extension's
        `mpm-options` setting is its mirror.
        """
        lexer = shlex(os.environ.get("VAR_MPM_OPTIONS", ""), posix=True)
        # What `shlex.split()` sets: tokens break on whitespace alone, so
        # `--config=/a/b` and `1:2` stay one argument each.
        lexer.whitespace_split = True
        return tuple(lexer)

    @cached_property
    def always_visible(self) -> bool:
        """Keep the menu bar icon while there is nothing to report.

        SwiftBar hides a plugin whose run produces no output, so rendering
        nothing is how the icon is made to disappear. That forces the plugin to
        tell a deliberate silence from a broken `mpm` call, which is why
        {meth}`print_menu` only tolerates an empty output while this is set.

        Xbar has no such behavior, hence the SwiftBar-only declaration.

        Value is sourced from the `VAR_ALWAYS_VISIBLE` environment variable, and
        named for the GNOME Shell extension's own `always-visible` setting: the
        two carried opposite polarities and unrelated names for one behavior.
        """
        return self.getenv_bool("VAR_ALWAYS_VISIBLE", True)

    @cached_property
    def default_font(self) -> str:
        """Make it easier to change font, sizes and colors of the output."""
        return self.normalize_params(
            self.getenv_str("VAR_DEFAULT_FONT", ""),  # type: ignore
        )

    @cached_property
    def monospace_font(self) -> str:
        """Make it easier to change font, sizes and colors of the output."""
        return self.normalize_params(
            self.getenv_str("VAR_MONOSPACE_FONT", "font=Menlo size=12"),  # type: ignore
        )

    @cached_property
    def error_font(self) -> str:
        """Error font is the monospace font, in red.

        It carries no size of its own. A smaller string is still laid out in a
        row the menu sizes for the larger font, and both hosts leave the
        surplus under the text instead of splitting it: at `size=10`, an error
        line ended up with 15 pixels of space below it where every other row
        leaves 9.
        """
        return self.normalize_params(f"{self.monospace_font} color=red")

    @cached_property
    def is_swiftbar(self) -> bool:
        """SwiftBar is kind enough to tell us about its presence."""
        return self.getenv_bool("SWIFTBAR")

    @staticmethod
    def search_venv(folder: Path) -> tuple[str, ...] | None:
        """The command running `mpm` from the project rooted at `folder`, or `None`.

        A project is told by its lockfile, and the command is the one its tool offers
        to run inside the environment it manages. A command opening on an environment
        assignment is never returned: {meth}`check_mpm` spawns the command without a
        shell, which would take the assignment for the program. A project with
        neither lockfile is reached through the other candidates of
        {meth}`search_mpm`.
        """
        if (folder / "uv.lock").is_file():
            # Frozen, and pinned to the folder the lockfile was found in: a bare
            # `uv run` would bind to the process cwd instead, and re-lock that
            # project (with the user-level uv config folded in) on every launch.
            return ("uv", "run", "--frozen", "--project", str(folder), "mpm")

        if (folder / "poetry.lock").is_file():
            return ("poetry", "run", "--directory", str(folder), "mpm")

        return None

    def search_mpm(self) -> Generator[tuple[str, ...], None, None]:
        """Iterate over possible CLI commands to execute `mpm`.

        Should be able to produce the full spectrum of alternative commands we can use
        to invoke `mpm` over different context.

        The order in which the candidates are returned by this method is conserved by
        the `ranked_mpm()` method below.

        Venv-based findings come first, because the plugin prefers the `mpm` it
        is part of. This file ships inside the package, so walking back up its
        own folders reaches the project that installed it, and that `mpm` is the
        one this plugin was released with, whose dependencies are already
        resolved. Both hosts import the file through a symlink into their own
        plugin folder, hence the resolution below: an unresolved path walks that
        folder and finds nothing, leaving the plugin to drive whichever other
        `mpm` the system answers with.

        The rest are fallbacks, for a plugin that reached the host on its own: a
        system-wide installation, then the module under an interpreter. None of
        them is trusted on sight, `check_mpm()` running each before it is ranked.
        """
        for folder in Path(__file__).resolve().parents:
            # Stop at Home: neither it nor any folder above it is a project of
            # the user's, and scanning on reaches `/` by way of every shared
            # parent a stray lockfile could sit in.
            if folder == Path.home():
                break

            venv_cli = self.search_venv(folder)
            if not venv_cli:
                continue

            yield venv_cli

        mpm_bin = which("mpm")
        if mpm_bin:
            yield (mpm_bin,)

        seen = set()
        for py_path in (sys.executable, which("python3")):
            if not py_path:
                continue
            # Deduplicated on the path as written, never on its target: a venv
            # interpreter is a symlink to the one it was built from, and that
            # target sees none of the venv's packages. Two names for a single
            # interpreter cost one extra probe here, where a resolved key drops
            # a whole environment that holds `mpm`.
            normalized = os.path.normcase(py_path)
            if normalized in seen:
                continue
            seen.add(normalized)
            yield (py_path, "-m", "meta_package_manager")

    def check_mpm(self, mpm_cli_args: tuple[str, ...]) -> Candidate:
        """Run the version probe of one command, and read the answer.

        `--no-color` keeps the answer parseable where Click would detect a terminal.
        A command whose program is missing is a candidate like any other, carrying
        the exception as its error.
        """
        try:
            process = run(
                (*mpm_cli_args, "--no-color", "--version"),
                capture_output=True,
                encoding="utf-8",
                check=False,
            )
        except FileNotFoundError as ex:
            return Candidate(mpm_cli_args, error=ex)
        if process.returncode or process.stderr:
            return Candidate(mpm_cli_args, error=process.stderr)

        match = VERSION_REGEX.search(process.stdout)
        if not match:
            return Candidate(mpm_cli_args, runnable=True, error=process.stderr)
        version = self.str_to_version(match.group("version"))
        return Candidate(
            mpm_cli_args,
            runnable=True,
            up_to_date=version >= MPM_MIN_VERSION,
            version=version,
            error=process.stderr,
            release=match.group("release"),
        )

    @cached_property
    def ranked_mpm(self) -> list[Candidate]:
        """Every `mpm` found on the system, best first.

        Sorted on {attr}`Candidate.rank`. Candidates ranking alike keep the order
        {meth}`search_mpm` produced them in.
        """
        return sorted(
            map(self.check_mpm, self.search_mpm()),
            key=attrgetter("rank"),
            reverse=True,
        )

    @cached_property
    def best_mpm(self) -> Candidate:
        return self.ranked_mpm[0]

    @staticmethod
    def pp(label: str, *args: str | None) -> None:
        """Print one menu-line with the SwiftBar/Xbar dialect.

        First argument is the menu-line label, separated by a pipe to all other non-
        empty parameters, themselves separated by a space.

        Skip printing of the line if label is empty. A `None` parameter renders
        nothing, so a package without an upgrade CLI still gets its label-only
        menu line.
        """
        if label.strip():
            print(
                # Do not strip the label to keep character alignments, especially in
                # table rendering and Python tracebacks.
                label,
                "|",
                *(arg.strip() for arg in args if arg and arg.strip()),
                sep=" ",
            )

    @staticmethod
    def print_error_header() -> None:
        """Generic header for blocking error."""
        MPMPlugin.pp("❗️", "dropdown=false")
        print("---")

    def print_error(self, message: str | Exception, submenu: str = "") -> None:
        """Print a formatted error message line by line.

        A red, fixed-width font is used to preserve traceback and exception layout. For
        compactness, the block message is dedented and empty lines are skipped.

        Message is always casted to a string as we allow passing of exception objects
        and have them rendered.
        """
        for line in map(methodcaller("rstrip"), dedent(str(message)).splitlines()):
            if line:
                self.pp(
                    f"{submenu}{line}",
                    self.error_font,
                    "trim=false",
                    "ansi=false",
                    "emojize=false",
                    "symbolize=false" if self.is_swiftbar else "",
                )

    def print_about(self) -> None:
        """Footer naming both halves of the install and the CLI behind them.

        This script and `mpm` are installed separately and upgraded
        separately: a plugin file copied into the host's folder stays at the
        version it was copied at while `mpm` moves under it, and nothing else
        in the menu shows that drift. The mpm line reports the release as
        printed, suffix included, where the ranking compares numbers alone.

        Kept to a single collapsed row so a menu opened for its packages is
        not pushed down by three lines of provenance.
        """
        host = "SwiftBar" if self.is_swiftbar else "Xbar"
        best = self.best_mpm
        print("---")
        self.pp("About", self.default_font)
        self.pp(
            f"--Meta Package Manager ({host} plugin) {self.plugin_version}",
            self.default_font,
        )
        self.pp(
            f"--mpm {best.release}" if best.runnable else "--mpm not found",
            self.default_font,
        )
        if best.runnable:
            self.pp(f"--{' '.join(best.args)}", self.monospace_font)
        self.pp("--Documentation", f"href={PLUGIN_DOCS_URL}", self.default_font)

    def print_menu(self) -> None:
        """Print the main menu."""
        # Xbar exposes no version to its plugins, so only SwiftBar is gated.
        if self.is_swiftbar:
            swiftbar_version_str = self.getenv_str("SWIFTBAR_VERSION", "")
            swiftbar_version = self.str_to_version(swiftbar_version_str)
            if not swiftbar_version or swiftbar_version < SWIFTBAR_MIN_VERSION:
                self.print_error_header()
                self.print_error(
                    f"SwiftBar v{swiftbar_version_str} found, but "
                    f"v{self.version_to_str(SWIFTBAR_MIN_VERSION)} is required.",
                )
                return

        best = self.best_mpm
        if not best.runnable or not best.up_to_date:
            self.print_error_header()
            if best.error:
                self.print_error(best.error)
                print("---")
            action_msg = "Install" if not best.runnable else "Upgrade"
            min_version_str = self.version_to_str(MPM_MIN_VERSION)
            self.pp(
                f"{action_msg} mpm >= {min_version_str} with uv",
                f"shell={INSTALL_ARGV[0]}",
                *(
                    f"param{index}={arg}"
                    for index, arg in enumerate(INSTALL_ARGV[1:], start=1)
                ),
                self.error_font,
                "refresh=true",
                "terminal=true",
            )
            self.pp(
                "Open mpm installation instructions",
                f"href={INSTALL_DOCS_URL}",
                self.error_font,
            )
            self.print_about()
            return

        # Refresh every manager's index first, best effort.
        run(
            (
                *best.args,
                "--verbosity",
                "ERROR",
                "--timeout",
                str(MPM_TIMEOUT),
                *self.mpm_options,
                "sync",
            ),
            check=False,
        )

        # mpm renders the menu itself. A manager's errors come back inside its
        # section, so only CRITICAL logs are let through.
        process = run(
            (
                *best.args,
                "--verbosity",
                "CRITICAL",
                "--timeout",
                str(MPM_TIMEOUT),
                *self.mpm_options,
                "outdated",
                "--plugin-output",
            ),
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

        # Bail-out immediately on errors related to mpm self-execution or if mpm is
        # not able to produce any output. An empty output is deliberate when the
        # user asked for the icon to vanish while everything is up to date, and is
        # then forwarded as-is for the host to hide the plugin.
        # The exit code tells a failed run apart, never <stderr> alone: a
        # `--verbosity` from `VAR_MPM_OPTIONS` overrides the CRITICAL one above,
        # and a successful run then logs there too.
        if process.returncode or (not process.stdout and self.always_visible):
            self.print_error_header()
            self.print_error(process.stderr)
            self.print_about()
            return

        # print() adds the line return the captured output already ends on.
        if process.stdout:
            print(process.stdout.rstrip())
            self.print_about()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--search-mpm",
        action="store_true",
        help="Locate all mpm on the system and sort them by best candidates.",
    )
    args = parser.parse_args()

    plugin = MPMPlugin()

    if args.search_mpm:
        for candidate in plugin.ranked_mpm:
            print(
                f"{' '.join(candidate.args)} | runnable: {candidate.runnable} | "
                f"up to date: {candidate.up_to_date} | version: {candidate.version} | "
                f"release: {candidate.release} | error: {candidate.error!r}"
            )

    else:
        plugin.print_menu()
