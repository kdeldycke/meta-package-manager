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
"""The :command:`mpm` command-line interface.

Defines the Click command group and its subcommands. Each operation subcommand
(``installed``, ``outdated``, ``install``, ``upgrade``, ``remove``, ...) selects the
managers from :py:mod:`meta_package_manager.pool` that implement the matching
:py:class:`meta_package_manager.capabilities.Operations` action, runs it across all
of them, and renders the aggregated, multi-manager result.
"""

from __future__ import annotations

import logging
import platform
import re
import sys
from collections import Counter, namedtuple
from collections.abc import Iterable
from configparser import RawConfigParser
from datetime import datetime, timedelta, timezone
from functools import partial
from io import TextIOWrapper
from pathlib import Path
from textwrap import dedent
from typing import ClassVar
from unittest.mock import patch

import tomli_w
from boltons.cacheutils import LRI, cached
from click_extra import (
    STRING,
    Choice,
    EnumChoice,
    File,
    IntRange,
    ParamType,
    Section,
    UsageError,
    argument,
    echo,
    file_path,
    group,
    option,
    option_group,
    pass_context,
)
from click_extra.colorize import HelpKeywords, highlight
from click_extra.table import (
    SERIALIZATION_FORMATS,
    print_data,
    print_sorted_table,
)
from click_extra.theme import get_current_theme as theme
from extra_platforms import current_platform, reduce

from . import __version__, bar_plugin
from .bar_plugin_renderer import BarPluginRenderer
from .brewfile import build_brewfile
from .capabilities import Operations
from .config import (
    MpmConfig,
    apply_manager_overrides_from_context,
    build_manager_overrides_validator,
    dump_manager_overrides,
    print_contribution_hints,
)
from .execution import CLIError, highlight_cli_name
from .inventory import MAIN_PLATFORMS
from .manager import PackageManager
from .package import packages_asdict
from .pool import pool
from .sbom import (
    SBOM,
    SPDX,
    CycloneDX,
    ExportFormat,
    cyclonedx_support,
    spdx_support,
)
from .specifier import VERSION_SEP, Solver, Specifier
from .summary import package_counts, print_summary, sbom_summary
from .version import diff_versions

if sys.version_info >= (3, 11):
    from enum import StrEnum

    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]
    from backports.strenum import StrEnum  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import IO

    from click_extra import Context, Parameter


# Subcommand sections.
EXPLORE = Section("Explore subcommands")
MAINTENANCE = Section("Maintenance subcommands")
SNAPSHOTS = Section("Package snapshots subcommands")
SBOM_SECTION = Section("SBOM subcommands")


OK_GLYPH = "✓"
"""Check-mark glyph for success indicators.

Kept as a raw, unstyled string so the call site can render it under
whichever theme is currently active, via the theme's ``success`` slot:
``theme().success(OK_GLYPH)``.
"""

KO_GLYPH = "✘"
"""Heavy-ballot-X glyph for failure indicators.

Styled at the call site with the active theme's ``error`` slot:
``theme().error(KO_GLYPH)``. See :data:`OK_GLYPH` for why the glyph is
kept unstyled.
"""


class SortableField(StrEnum):
    """Fields IDs allowed to be sorted."""

    MANAGER_ID = "manager_id"
    MANAGER_NAME = "manager_name"
    PACKAGE_ID = "package_id"
    PACKAGE_NAME = "package_name"
    VERSION = "version"


XKCD_MANAGER_ORDER = ("pip", "brew", "npm", "dnf", "apt", "steamcmd")
"""Sequence of package managers as defined by `XKCD #1654: Universal Install Script
<https://xkcd.com/1654/>`_.

See the corresponding :issue:`implementation rationale in issue #10 <10>`.
"""


class Duration(ParamType):
    """Parse a cooldown spec into a :py:class:`datetime.timedelta`.

    Accepts three input shapes:

    - **Friendly duration**: ``7 days``, ``1 week``, ``12h``, ``30m``, ``45s``,
      or a bare number of days like ``7``.
    - **ISO 8601 duration**: ``P7D``, ``PT12H``, ``P1WT6H``. Case-insensitive.
    - **RFC 3339 absolute timestamp**: ``2024-05-01T00:00:00Z`` or with an
      offset like ``+02:00``. Converted at parse time to ``now - timestamp``;
      a timestamp in the future disables the cooldown.

    A zero duration or empty input parses to ``None``, which disables the cooldown
    (handy to override a value set in the configuration file).

    .. note::
       Durations resolve to a fixed number of seconds, assuming a day is 24
       hours. The local time zone, DST transitions, and calendar boundaries are
       ignored. Calendar units (months, years) are rejected for the same
       reason: 28-31 days and 365-366 days make them unsuitable for a precise
       release-age cutoff. Use ``days`` or ``weeks`` instead.
    """

    name = "duration"

    _UNIT_SECONDS: ClassVar[dict[str, int]] = {
        "": 86400,
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hr": 3600,
        "hrs": 3600,
        "hour": 3600,
        "hours": 3600,
        "d": 86400,
        "day": 86400,
        "days": 86400,
        "w": 604800,
        "week": 604800,
        "weeks": 604800,
    }
    """Number of seconds each recognized unit represents (empty unit means days)."""

    _CALENDAR_UNITS = frozenset({
        "mo",
        "mon",
        "month",
        "months",
        "y",
        "yr",
        "yrs",
        "year",
        "years",
    })
    """Calendar units rejected for ambiguity: months span 28-31 days, years 365-366."""

    _FRIENDLY_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-z]*)")
    _ISO8601_PATTERN = re.compile(
        r"P"
        r"(?:(?P<years>\d+(?:\.\d+)?)Y)?"
        r"(?:(?P<months>\d+(?:\.\d+)?)M)?"
        r"(?:(?P<weeks>\d+(?:\.\d+)?)W)?"
        r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
        r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
        r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
        r")?",
    )

    _EXAMPLES = (
        "'7 days', '1 week', '12h', '30m', 'P7D', 'PT12H', "
        "or an RFC 3339 timestamp like '2024-05-01T00:00:00Z'"
    )
    _CALENDAR_REJECT = (
        "calendar units (months, years) are rejected because their length is "
        "ambiguous: months span 28-31 days, years 365-366. Use days or weeks "
        "instead, like '30 days' or '4 weeks'."
    )

    def convert(
        self,
        value: object,
        param: Parameter | None,
        ctx: Context | None,
    ) -> timedelta | None:
        """Coerce ``value`` to a :py:class:`datetime.timedelta` (or ``None``)."""
        if value is None or isinstance(value, timedelta):
            return value
        text = str(value).strip()
        if not text:
            return None
        # RFC 3339 absolute timestamp: starts with a 4-digit year and a dash.
        if len(text) >= 5 and text[:4].isdigit() and text[4] == "-":
            return self._parse_timestamp(text, value, param, ctx)
        # ISO 8601 duration: starts with 'P' (case-insensitive).
        if text[:1] in ("P", "p"):
            return self._parse_iso8601(text.upper(), value, param, ctx)
        # Friendly duration.
        return self._parse_friendly(text.lower(), value, param, ctx)

    def _parse_timestamp(
        self,
        text: str,
        value: object,
        param: Parameter | None,
        ctx: Context | None,
    ) -> timedelta | None:
        normalized = text.upper().replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(normalized)
        except ValueError:
            self.fail(
                f"{value!r} looks like an RFC 3339 timestamp but cannot be "
                f"parsed. Accepted: {self._EXAMPLES}.",
                param,
                ctx,
            )
        if ts.tzinfo is None:
            self.fail(
                f"{value!r} is missing a time zone. Use a fully qualified "
                "RFC 3339 timestamp with 'Z' or an offset like '+00:00'.",
                param,
                ctx,
            )
        delta = datetime.now(tz=timezone.utc) - ts.astimezone(timezone.utc)
        return delta if delta.total_seconds() > 0 else None

    def _parse_iso8601(
        self,
        text: str,
        value: object,
        param: Parameter | None,
        ctx: Context | None,
    ) -> timedelta | None:
        match = self._ISO8601_PATTERN.fullmatch(text)
        if not match or not any(match.groups()):
            self.fail(
                f"{value!r} is not a valid ISO 8601 duration "
                f"(examples: 'P7D', 'PT12H', 'P1WT6H'). Accepted: {self._EXAMPLES}.",
                param,
                ctx,
            )
        groups = match.groupdict()
        if groups["years"] or groups["months"]:
            self.fail(f"{value!r}: {self._CALENDAR_REJECT}", param, ctx)
        seconds = (
            float(groups["weeks"] or 0) * 604800
            + float(groups["days"] or 0) * 86400
            + float(groups["hours"] or 0) * 3600
            + float(groups["minutes"] or 0) * 60
            + float(groups["seconds"] or 0)
        )
        return timedelta(seconds=seconds) if seconds else None

    def _parse_friendly(
        self,
        text: str,
        value: object,
        param: Parameter | None,
        ctx: Context | None,
    ) -> timedelta | None:
        match = self._FRIENDLY_PATTERN.fullmatch(text)
        if match:
            unit = match["unit"]
            if unit in self._CALENDAR_UNITS:
                self.fail(f"{value!r}: {self._CALENDAR_REJECT}", param, ctx)
            if unit in self._UNIT_SECONDS:
                seconds = float(match["value"]) * self._UNIT_SECONDS[unit]
                return timedelta(seconds=seconds) if seconds else None
        self.fail(
            f"{value!r} is not a valid duration (examples: {self._EXAMPLES}).",
            param,
            ctx,
        )


def is_stdout(filepath: Path) -> bool:
    """Check if a file path is set to stdout.

    Prevents the creation of a ``-`` file in the current directory.
    """
    return str(filepath) == "-"


def prep_path(filepath: Path) -> IO | None:
    """Prepare the output file parameter for Click's echo function."""
    if is_stdout(filepath):
        return None
    return filepath.open("w", encoding="UTF-8")


def update_manager_selection(
    ctx: Context, param: Parameter, value: str | Iterable[str] | bool | None
) -> None:
    """Update global selection list of managers in the context.

    Accumulate and merge all manager selectors to form the initial population enforced by the user.
    """
    # Option has not been called.
    if value is None:
        return

    # Use a list to keep the natural order of selection.
    to_add: list[str] = []
    # Use a set because removal takes precedence over addition: we don't care
    # about user's order.
    to_remove: set[str] = set()

    assert param.name

    # Add the value of --manager list.
    if param.name == "manager":
        if value:
            assert isinstance(value, Iterable)
            to_add.extend(value)

    # Add the value of --exclude list.
    elif param.name == "exclude":
        if value:
            assert isinstance(value, Iterable)
            to_remove.update(value)

    # Update the list of managers with the XKCD preset.
    elif param.name == "xkcd":
        if value:
            to_add.extend(XKCD_MANAGER_ORDER)

    # Update selection with single selectors.
    else:
        # Because the parameter's name is transformed into a Python identifier on
        # instantiation, we have to reverse the process to get our value.
        # Example: --apt-mint => apt_mint => apt-mint
        manager_id = param.name.removeprefix("no_").replace("_", "-")
        assert manager_id in pool.all_manager_ids, (
            f"unrecognized single manager selector {param.name!r}"
        )

        # Normalize the value to a boolean.
        if isinstance(value, str):
            value = RawConfigParser.BOOLEAN_STATES.get(value.lower(), value)
        assert value in (
            manager_id,
            True,
            False,
        ), f"unexpected value {value!r} for {param!r}"

        if param.name.startswith("no_") ^ (value is False):
            to_remove.add(manager_id)
        else:
            to_add.append(manager_id)

    logging.debug(f"Managers added by {param}: {to_add}")
    logging.debug(f"Managers removed by {param}: {to_remove}")

    # Initialize the shared context object to accumulate there the selection results.
    if ctx.obj is None:
        ctx.obj = {}
    if to_add:
        ctx.obj.setdefault("managers_to_add", []).extend(to_add)
    if to_remove:
        ctx.obj.setdefault("managers_to_remove", set()).update(to_remove)


def single_manager_selectors():
    """Dynamiccaly creates a dedicated flag selector alias for each manager."""
    single_flags = []
    single_no_flags = []
    for manager_id, manager in pool.items():
        single_flags.append(
            option(
                f"--{manager_id}",
                flag_value=manager_id,
                default=None,
                help=f"Select {manager.name}.",
                deprecated=manager.deprecated,
                expose_value=False,
                callback=update_manager_selection,
            )
        )
        single_no_flags.append(
            option(
                f"--no-{manager_id}",
                flag_value=manager_id,
                default=None,
                help=f"Deselect {manager.name}.",
                deprecated=manager.deprecated,
                expose_value=False,
                callback=update_manager_selection,
            )
        )
    return *single_flags, *single_no_flags


def bar_plugin_path(ctx: Context, param: Parameter, value: str | None):
    """Print the location of the :doc:`Xbar/SwiftBar plugin <bar-plugin>`.

    Returns the normalized path of the standalone `bar_plugin.py
    <https://github.com/kdeldycke/meta-package-manager/blob/main/meta_package_manager/bar_plugin.py>`_
    script that is distributed with this Python module. This
    is made available under the :option:`mpm --bar-plugin-path` option.

    Notice that the fully-qualified home directory get replaced by its
    shorthand (``~``) if applicable:

    - the full ``/home/user/.python/site-packages/mpm/bar_plugin.py`` path is
      simplified to ``~/.python/site-packages/mpm/bar_plugin.py``,
    - but ``/usr/bin/python3.10/mpm/bar_plugin.py`` is returned as-is.
    """
    # Option has not been called.
    if not value:
        return

    # Options is only available when CLI is installed from sources, not CLI is
    # a bundled executable.
    if "__compiled__" in globals():
        logging.debug("CLI running as a binary.")
        logging.critical(
            "Option --bar-plugin-path is only available for CLI installed from "
            "sources.",
        )
        ctx.exit(2)

    bar_path = Path(bar_plugin.__file__).expanduser().resolve()
    home_dir = Path.home()

    if bar_path.is_relative_to(home_dir):
        home_shorthand = Path("~")
        shorten_bar_path = home_shorthand / bar_path.relative_to(home_dir)
        assert shorten_bar_path.expanduser().resolve() == bar_path
        bar_path = shorten_bar_path
    echo(bar_path)
    ctx.exit()


@group(
    # XXX Default verbosity has been changed in Click Extra 4.0.0 from INFO to WARNING.
    context_settings={"default_map": {"verbosity": "INFO"}},
    config_schema=MpmConfig,
    config_validators=(build_manager_overrides_validator(pool),),
    version_fields={
        "env_info": (
            f"Python {platform.python_version()}, "
            f"{platform.system()} {platform.machine()}"
        ),
    },
)
@option_group(
    "Package manager selection",
    # ---------------------- 80 characters reference limit ----------------------- #
    dedent("""\
    \b
    Use these options to restrict the subcommand to a subset of managers.

    \b
    - By default, mpm will evaluate all managers supported on the current platform.
    - Use the --<manager-id> selectors to restrict target to a subset of managers.
    - To remove a manager from the selection, use --no-<manager-id> selectors.
    - Order of the selectors is preserved for priority-sensitive subcommands.
    - Exclusion of a manager always takes precedence over its inclusion.
    \b

    """),
    *single_manager_selectors(),
    option(
        "-a",
        "--all-managers",
        is_flag=True,
        default=False,
        help="Force evaluation of all managers implemented by mpm, including those "
        "not supported by the current platform or deprecated. Still applies filtering "
        "by --<manager-id> / --no-<manager-id> options before calling the subcommand.",
    ),
    option(
        "-x",
        "--xkcd",
        is_flag=True,
        default=None,
        expose_value=False,
        callback=update_manager_selection,
        help="Preset manager selection as defined by XKCD #1654. Equivalent to: "
        "{}.".format(" ".join(f"--{mid}" for mid in XKCD_MANAGER_ORDER)),
    ),
    option(
        "-m",
        "--manager",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        default=None,
        expose_value=False,
        hidden=True,
        callback=update_manager_selection,
        deprecated="Use --<manager-id> single selector instead.",
        help="Select a manager.",
    ),
    option(
        "-e",
        "--exclude",
        type=Choice(pool.all_manager_ids, case_sensitive=False),
        multiple=True,
        default=None,
        expose_value=False,
        hidden=True,
        callback=update_manager_selection,
        deprecated="Use --no-<manager-id> single selector instead.",
        help="Exclude a manager.",
    ),
)
@option_group(
    "Manager options",
    option(
        "--ignore-auto-updates/--include-auto-updates",
        default=True,
        help="Report all outdated packages, including those tagged as "
        "auto-updating. Only applies to outdated and upgrade subcommands.",
    ),
    option(
        "--stop-on-error/--continue-on-error",
        default=False,
        help="Stop right away or continue operations on manager CLI error.",
    ),
    option(
        "-d",
        "--dry-run",
        is_flag=True,
        default=False,
        help="Do not actually perform any action, just simulate CLI calls.",
    ),
    option(
        "-t",
        "--timeout",
        type=IntRange(min=0),
        default=500,
        help="Set maximum duration in seconds for each CLI call.",
    ),
    option(
        "--cooldown",
        type=Duration(),
        default="",
        metavar="DURATION",
        help="Refuse to install or upgrade any package version published more "
        "recently than this duration, as a mitigation against supply-chain "
        "attacks. Accepts a friendly duration ('7 days', '1 week', '12h'), an "
        "ISO 8601 duration ('P7D', 'PT12H'), or an RFC 3339 absolute timestamp "
        "('2024-05-01T00:00:00Z'). Only honored by managers with native "
        "release-age support (uv, npm, pip, pipx); the others are skipped "
        "unless --allow-no-cooldown is set.",
    ),
    option(
        "--allow-no-cooldown",
        is_flag=True,
        default=False,
        help="When --cooldown is set, still run install and upgrade on managers that "
        "cannot enforce it, instead of skipping them. Trades the supply-chain "
        "safeguard for broader manager coverage.",
    ),
)
@option_group(
    "Output options",
    option(
        "--description",
        is_flag=True,
        default=False,
        help="Show package description in results.",
    ),
    option(
        "-s",
        "--sort-by",
        type=EnumChoice(SortableField),
        default=SortableField.MANAGER_ID,
        help="Sort results.",
    ),
    # option('--sort-asc/--sort-desc', default=True)
    option(
        "--summary/--no-summary",
        default=True,
        help=(
            "Print an end-of-run summary on stderr: a count line of "
            "per-manager totals plus any subcommand-specific follow-up "
            "notes (like SBOM enrichment and merge counts). Defaults on; "
            "use --no-summary to silence."
        ),
    ),
    option(
        "--suggest-contribs/--no-suggest-contribs",
        default=True,
        help="Print a contribution invitation when a user override targets a "
        "field that likely indicates an upstream detection bug "
        "(cli_names, cli_search_path, requirement, version_cli_options, "
        "version_regexes).",
    ),
)
@option_group(
    "Xbar/SwiftBar options",
    option(
        "--bar-plugin-path",
        is_flag=True,
        default=False,
        expose_value=False,
        is_eager=True,
        callback=bar_plugin_path,
        help="Print location of the Xbar/SwiftBar plugin.",
    ),
)
@pass_context
def mpm(
    ctx,
    all_managers,
    ignore_auto_updates,
    stop_on_error,
    dry_run,
    timeout,
    cooldown,
    allow_no_cooldown,
    description,
    sort_by,
    summary,
    suggest_contribs,
):
    """CLI options shared by all subcommands."""
    # Silence all log messages for serialization rendering unless in debug mode.
    if (
        ctx.meta["click_extra.table_format"] in SERIALIZATION_FORMATS
        and ctx.meta["click_extra.verbosity"] != "DEBUG"
    ):
        logging.disable()

        def remove_logging_override():
            """Reset the logging override to its default state.

            ``logging.disable()`` mess with the logging module internals at the root
            level. We need to restore the default behavior when the context is closed,
            otherwise the logging module will be stuck in a disabled state.

            See: https://docs.python.org/3/library/logging.html?highlight=logging#logging.disable
            """
            logging.disable(logging.NOTSET)

        ctx.call_on_close(remove_logging_override)

    # Apply per-manager attribute overrides from [mpm.managers.<id>] sections of
    # the config file, before any subcommand observes the pool. Also collects any
    # contribution-hint candidates onto ctx.meta for the close-time callback below.
    apply_manager_overrides_from_context(ctx, pool)
    if suggest_contribs:
        ctx.call_on_close(partial(print_contribution_hints, ctx))

    # Snapshot per-manager error counts so the close-time summary below only
    # reports errors that accumulated during *this* invocation. The pool is a
    # module-level singleton and survives across calls (e.g. in test runs that
    # exercise multiple invocations in the same process), so a naive non-empty
    # check would warn about errors from prior runs.
    initial_error_counts = {mid: len(m.cli_errors) for mid, m in pool.register.items()}

    def summarize_cli_errors():
        """End-of-run hint when underlying CLIs reported errors.

        Captured stderr is logged at DEBUG (see
        :py:func:`CLIExecutor.run_cli`) so a default-verbosity run no longer
        floods the table with gem extension warnings, mas Spotlight chatter,
        etc. This summary preserves the "something went sideways" signal in
        one line, without replicating the noise.

        Skipped at DEBUG verbosity (the stderr already appeared inline) and
        in serialization formats (logging is disabled and ``cli_errors``
        ships in the structured payload anyway).
        """
        if logging.getLogger().getEffectiveLevel() <= logging.DEBUG:
            return
        failed = sorted(
            mid
            for mid, manager in pool.register.items()
            if len(manager.cli_errors) > initial_error_counts.get(mid, 0)
        )
        if not failed:
            return
        ids = ", ".join(map(theme().invoked_command, failed))
        plural = "managers" if len(failed) > 1 else "manager"
        logging.warning(
            f"{len(failed)} {plural} reported errors during this run "
            f"({ids}); re-run with --verbosity DEBUG for details.",
        )

    ctx.call_on_close(summarize_cli_errors)

    # Normalize to None if no manager selectors have been used. This prevent the
    # pool.select_managers() method to iterate over an empty population of managers to
    # choose from.
    user_selection = None
    managers_to_remove = None
    if ctx.obj:
        user_selection = ctx.obj.get("managers_to_add", None)
        managers_to_remove = ctx.obj.get("managers_to_remove", None)

    # Sentinel to print the selection summary on the first call only.
    selection_logged = False

    def selected_managers(**kwargs):
        """Select the subset of managers to target, and apply manager-level options.

        The selection summary is logged on the first call only, so subcommands that
        never resolve the pool (like ``--help``) stay silent.

        Callers may pass ``keep=<ids>`` to narrow the selection to a specific
        subset (for example, the managers that implement a given operation).
        When provided it overrides the global ``user_selection`` for that call.
        """
        nonlocal selection_logged
        if not selection_logged:
            if user_selection:
                selected = " > ".join(map(theme().invoked_command, user_selection))
                logging.info(f"Selected managers (by priority): {selected}.")
            else:
                logging.info("Selected managers: platform defaults.")
            if managers_to_remove:
                dropped = ", ".join(
                    map(theme().invoked_command, sorted(managers_to_remove))
                )
                logging.info(f"Dropped managers: {dropped}.")
            else:
                logging.info("Dropped managers: none.")
            selection_logged = True
        keep = kwargs.pop("keep", user_selection)
        return pool.select_managers(
            keep=keep,
            drop=managers_to_remove,
            keep_deprecated=all_managers,
            # Should we include auto-update packages or not?
            ignore_auto_updates=ignore_auto_updates,
            # Does the manager should raise on error or not.
            stop_on_error=stop_on_error,
            dry_run=dry_run,
            timeout=timeout,
            # Minimum release age gate and its fail-open escape hatch.
            cooldown=cooldown,
            allow_no_cooldown=allow_no_cooldown,
            **kwargs,
        )

    # Load up current and new global options to the context for subcommand consumption.
    ctx.obj = namedtuple(
        "GlobalOptions",
        (
            "all_managers",
            "user_selection",
            "user_drops",
            "selected_managers",
            "description",
            "sort_by",
            "summary",
        ),
        defaults=(
            all_managers,
            user_selection,
            managers_to_remove,
            selected_managers,
            description,
            sort_by,
            summary,
        ),
    )()

    # Override ctx.print_table with the upstream sorted variant.
    ctx.print_table = partial(
        print_sorted_table,
        table_format=ctx.meta["click_extra.table_format"],
    )


# Extend --version output with Python and platform metadata.
for _param in mpm.params:
    if _param.name == "version" and hasattr(_param, "message"):
        _param.message = "{prog_name}, version {version}\n{env_info}"
        break

# Highlight placeholder option names that appear in the help text prose.
mpm.extra_keywords = HelpKeywords(  # type: ignore[attr-defined]
    long_options={"--<manager-id>", "--no-<manager-id>"},
)
# "version" is a --sort-by choice but too common a word in help text.
mpm.excluded_keywords = HelpKeywords(choices={"version"})  # type: ignore[attr-defined]


@mpm.command(
    short_help="List every registered package manager and check its presence "
    "on the system.",
    section=EXPLORE,
)
@pass_context
def managers(ctx):
    """List every package manager detected on the system.

    Only reports by default all managers supported on the current platform. To include
    unsupported and deprecated managers in the report, use the :option:`--all-managers`
    flag.

    User's own selection configuration are intentionally ignored, so a manager dropped
    from regular operations is still visible here for troubleshooting. To narrow down the
    report to a subset of managers, pass the same selectors as for other subcommands (e.g.
    :option:`--pip` or :option:`--no-apt`).
    """
    if ctx.obj.user_drops:
        dropped = ", ".join(map(theme().invoked_command, sorted(ctx.obj.user_drops)))
        logging.info(f"Ignoring user exclusion of {dropped}.")
    inventory = partial(
        pool.select_managers,
        keep=ctx.obj.user_selection,
        drop=None,
        keep_deprecated=ctx.obj.all_managers,
        # Keep managers whose CLI was not found, to show how mpm reacts to the
        # local platform.
        drop_not_found=False,
    )

    # Machine-friendly data rendering.
    table_format = ctx.meta["click_extra.table_format"]
    if table_format in SERIALIZATION_FORMATS:
        manager_data = {}
        # Build up the data structure of manager metadata.
        fields = (
            "name",
            "id",
            "supported",
            "cli_path",
            "executable",
            "version",
            "fresh",
            "available",
        )
        for manager in inventory():
            manager_data[manager.id] = {fid: getattr(manager, fid) for fid in fields}
            # Serialize errors at the last minute to gather all we encountered.
            manager_data[manager.id]["errors"] = list(
                {expt.error for expt in manager.cli_errors},
            )

        print_data(
            manager_data,
            table_format,
            root_element="mpm",
            package="meta-package-manager",
        )
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager in inventory():
        # Build up the OS column content.
        os_infos = (
            theme().success(OK_GLYPH) if manager.supported else theme().error(KO_GLYPH)
        )
        if not manager.supported:
            os_infos += " {}".format(
                ", ".join(
                    sorted(p.name for p in reduce(manager.platforms, MAIN_PLATFORMS))
                ),
            )
        if manager.deprecated:
            os_infos += f" {theme().warning('(deprecated)')}"

        # Build up the CLI path column content.
        cli_infos = "{} {}".format(
            theme().success(OK_GLYPH) if manager.cli_path else theme().error(KO_GLYPH),
            highlight_cli_name(manager.cli_path, manager.cli_names)
            if manager.cli_path
            else (
                f"{', '.join(map(theme().invoked_command, manager.cli_names))} not found"
            ),
        )

        # Build up the version column content.
        version_infos = ""
        if manager.executable:
            version_infos = (
                theme().success(OK_GLYPH) if manager.fresh else theme().error(KO_GLYPH)
            )
            if manager.version:
                version_infos += f" {manager.version}"
                if not manager.fresh:
                    version_infos += f" {manager.requirement}"

        table.append(
            (
                getattr(theme(), "success" if manager.fresh else "error")(manager.id),
                manager.name,
                os_infos,
                cli_infos,
                theme().success(OK_GLYPH) if manager.executable else "",
                version_infos,
            ),
        )

    ctx.find_root().print_table(
        (
            ("Manager ID", SortableField.MANAGER_ID),
            ("Name", SortableField.MANAGER_NAME),
            ("Supported", None),
            ("CLI", None),
            ("Executable", None),
            ("Version", SortableField.VERSION),
        ),
        table,
        ctx.obj.sort_by,
    )


@mpm.command(aliases=["list"], short_help="List installed packages.", section=EXPLORE)
@option(
    "-d",
    "--duplicates",
    is_flag=True,
    default=False,
    help="Only list installed packages sharing the same ID. Implies "
    "`--sort-by package_id` to make duplicates easier to compare between themselves.",
)
@pass_context
def installed(ctx, duplicates):
    """List all packages installed on the system by each manager."""
    # Build-up a global dict of installed packages per manager.
    installed_data = {}
    fields = (
        "id",
        "name",
        "installed_version",
    )

    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        try:
            packages = tuple(packages_asdict(manager.installed, fields))
        except CLIError:
            logging.warning(
                f"Could not list installed packages "
                f"from {theme().invoked_command(manager.id)}."
            )
            packages = ()

        installed_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        installed_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors},
        )

    # Filters out non-duplicate packages.
    if duplicates:
        # Re-group packages by their IDs.
        package_sources: dict[str, set[str]] = {}
        for manager_id, installed_pkg in installed_data.items():
            for package in installed_pkg["packages"]:
                package_sources.setdefault(package["id"], set()).add(manager_id)
        logging.debug(f"Managers sourcing each package: {package_sources}")

        # Identify package IDs shared by multiple managers.
        duplicates_ids = {
            pid for pid, managers in package_sources.items() if len(managers) > 1
        }
        logging.debug(f"Duplicates: {duplicates_ids}")

        # Remove non-duplicates from results.
        for manager_id, manager_data in installed_data.items():
            duplicate_packages = tuple(
                p for p in manager_data["packages"] if p["id"] in duplicates_ids
            )
            manager_data["packages"] = duplicate_packages

    # Machine-friendly data rendering.
    table_format = ctx.meta["click_extra.table_format"]
    if table_format in SERIALIZATION_FORMATS:
        print_data(
            installed_data,
            table_format,
            root_element="mpm",
            package="meta-package-manager",
        )
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager_id, installed_pkg in installed_data.items():
        table += [
            (
                info["id"],
                info["name"],
                manager_id,
                str(info["installed_version"]) if info["installed_version"] else "?",
            )
            for info in installed_pkg["packages"]
        ]

    # Force sorting by package ID in duplicate mode.
    sort_by = ctx.obj.sort_by
    if duplicates:
        logging.info(
            "Force table sorting on package ID because of --duplicates option."
        )
        sort_by = SortableField.PACKAGE_ID

    # Print table.
    ctx.find_root().print_table(
        (
            ("Package ID", SortableField.PACKAGE_ID),
            ("Name", SortableField.PACKAGE_NAME),
            ("Manager", SortableField.MANAGER_ID),
            ("Installed version", SortableField.VERSION),
        ),
        table,
        sort_by,
    )

    if ctx.obj.summary:
        print_summary(package_counts(installed_data))


@mpm.command(short_help="List outdated packages.", section=EXPLORE)
@option(
    "--plugin-output",
    is_flag=True,
    default=False,
    help="Output results for direct consumption by an Xbar/SwiftBar-compatible plugin. "
    "The layout is dynamic and depends on environment variables set by either Xbar "
    "or SwiftBar.",
)
@pass_context
def outdated(ctx, plugin_output):
    """List available package upgrades and their versions for each manager."""
    # Build-up a global list of outdated packages per manager.
    outdated_data = {}
    fields = (
        "id",
        "name",
        "installed_version",
        "latest_version",
    )

    for manager in ctx.obj.selected_managers(implements_operation=Operations.outdated):
        try:
            packages = tuple(packages_asdict(manager.refiltered_outdated, fields))
        except CLIError:
            logging.warning(
                f"Could not list outdated packages "
                f"from {theme().invoked_command(manager.id)}."
            )
            packages = ()

        outdated_data[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        outdated_data[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors},
        )

    # Machine-friendly data rendering.
    table_format = ctx.meta["click_extra.table_format"]
    if table_format in SERIALIZATION_FORMATS:
        print_data(
            outdated_data,
            table_format,
            root_element="mpm",
            package="meta-package-manager",
        )
        ctx.exit()

    # Xbar/SwiftBar-friendly plugin rendering.
    if plugin_output:
        BarPluginRenderer().print(outdated_data)
        ctx.exit()

    # Human-friendly content rendering.
    table = []
    for manager_id, outdated_pkg in outdated_data.items():
        for info in outdated_pkg["packages"]:
            installed_version, latest_version = diff_versions(
                info["installed_version"] if info["installed_version"] else "?",
                info["latest_version"],
            )
            table.append(
                (
                    info["id"],
                    info["name"],
                    manager_id,
                    installed_version,
                    latest_version,
                ),
            )

    # Sort and print table.
    ctx.find_root().print_table(
        (
            ("Package ID", SortableField.PACKAGE_ID),
            ("Name", SortableField.PACKAGE_NAME),
            ("Manager", SortableField.MANAGER_ID),
            ("Installed version", SortableField.VERSION),
            ("Latest version", None),
        ),
        table,
        ctx.obj.sort_by,
    )

    if ctx.obj.summary:
        print_summary(package_counts(outdated_data))


# TODO: make it a --search-strategy=[exact, fuzzy, extended]
# Add details helps => exact: is case-sensitive, and keep all non-alnum chars
# fuzzy: query is case-insensitive, stripped-out of non-alnum chars and
# tokenized (no order sensitive)
# extended, same as fuzzy, but do not limit search to package ID and name.
# extended to description and other metadata depending on manager support.
# Modes:
#  1. strict (--exact, on ID or name)
#  2. substring (regex, no case, no split)
#  3. fuzzy (token-based)
#  4. extended (fuzzy + metadata)
@mpm.command(short_help="Search packages.", section=EXPLORE)
@option(
    "--extended/--id-name-only",
    default=False,
    help="Extend search to description, instead of restricting it to package ID and "
    "name. Implies --description.",
)
@option(
    "--exact/--fuzzy",
    default=False,
    help="Only returns exact matches on package ID or name.",
)
@option(
    "--refilter/--no-refilter",
    default=True,
    help="Let mpm refilters managers' search results.",
)
@argument("query", type=STRING, required=True)
@pass_context
def search(ctx, extended, exact, refilter, query):
    """Search each manager for a package ID, name or description matching the query."""
    # --extended implies --description.
    show_description = ctx.obj.description
    if extended and not ctx.obj.description:
        logging.info("--extended option forces --description option.")
        show_description = True

    # Build-up a global list of package matches per manager.
    matches = {}
    fields = (
        "id",
        "name",
        "latest_version",
        "description",
    )

    search_method = "refiltered_search" if refilter else "search"
    for manager in ctx.obj.selected_managers(implements_operation=Operations.search):
        try:
            packages = tuple(
                packages_asdict(
                    getattr(manager, search_method)(query, extended, exact),
                    fields,
                ),
            )
        except CLIError:
            logging.warning(
                f"Could not search packages from {theme().invoked_command(manager.id)}."
            )
            packages = ()

        matches[manager.id] = {
            "id": manager.id,
            "name": manager.name,
            "packages": packages,
        }

        # Serialize errors at the last minute to gather all we encountered.
        matches[manager.id]["errors"] = list(
            {expt.error for expt in manager.cli_errors},
        )

    # Machine-friendly data rendering.
    table_format = ctx.meta["click_extra.table_format"]
    if table_format in SERIALIZATION_FORMATS:
        print_data(
            matches, table_format, root_element="mpm", package="meta-package-manager"
        )
        ctx.exit()

    # Prepare highlighting helpers.
    query_parts = {query}.union(PackageManager.query_parts(query))
    highlight_query = cached(LRI(max_size=1000))(
        partial(
            highlight,
            patterns=query_parts,
            styling_func=theme().search,
            ignore_case=True,
        ),
    )

    # Human-friendly content rendering.
    table = []
    for manager_id, matching_pkg in matches.items():
        for pkg in matching_pkg["packages"]:
            line = [
                highlight_query(pkg["id"]) if pkg["id"] else "",
                highlight_query(pkg["name"]) if pkg["name"] else "",
                manager_id,
                str(pkg["latest_version"]) if pkg["latest_version"] else "?",
            ]
            if show_description:
                line.append(
                    highlight_query(pkg.get("description"))
                    if pkg.get("description")
                    else "",
                )
            table.append(line)

    # Sort and print table.
    headers: list[tuple[str, str | None]] = [
        ("Package ID", SortableField.PACKAGE_ID),
        ("Name", SortableField.PACKAGE_NAME),
        ("Manager", SortableField.MANAGER_ID),
        ("Latest version", SortableField.VERSION),
    ]
    if show_description:
        headers.append(("Description", None))
    ctx.find_root().print_table(headers, table, ctx.obj.sort_by)

    if ctx.obj.summary:
        print_summary(package_counts(matches))


@mpm.command(aliases=["locate"], short_help="Locate CLIs on system.", section=EXPLORE)
@argument("cli_names", type=STRING, nargs=-1, required=True)
@pass_context
def which(ctx, cli_names):
    """Search from the user's environment all CLIs matching the query.

    This is mpm's own version of the `which -a` UNIX command, used internally to locate
    binaries for each manager. It is exposed as a subcommand for convenience and to help
    troubleshoot CLI resolution logic.

    Compared to the venerable `which` command, this will respect the additional path
    configured for each package manager. It will ignore files that are empty (0 size).
    On Windows, it additionally suppress the default lookup in the current directory,
    which takes precedence on other paths.
    """
    if ctx.obj.sort_by:
        logging.warning("Ignore --sort-by option for which command.")

    # Machine-friendly data rendering.
    table_format = ctx.meta["click_extra.table_format"]
    if table_format in SERIALIZATION_FORMATS:
        cli_data = [
            {
                "manager_id": manager.id,
                "cli_paths": list(manager.search_all_cli(cli_names)),
            }
            for manager in ctx.obj.selected_managers()
        ]
        print_data(
            cli_data, table_format, root_element="mpm", package="meta-package-manager"
        )
        ctx.exit()

    # Print table.
    table = []
    for manager in ctx.obj.selected_managers():
        for priority, found_cli in enumerate(manager.search_all_cli(cli_names)):
            # Resolve symlinks and highlight the CLI name.
            symlink = ""
            if found_cli.is_symlink():
                # resolve() always returns a Path, so highlight_cli_name won't return None.
                resolved = highlight_cli_name(found_cli.resolve(), cli_names)
                assert resolved is not None
                symlink = f"→ {resolved}"
            table.append(
                (
                    manager.id,
                    str(priority),
                    highlight_cli_name(found_cli, cli_names),
                    symlink,
                ),
            )
    ctx.find_root().print_table(
        (
            ("Manager ID", SortableField.MANAGER_ID),
            ("Priority", None),
            ("CLI path", None),
            ("Symlink destination", None),
        ),
        table,
        ctx.obj.sort_by,
    )


@mpm.command(
    name="config-template",
    short_help="Print per-manager overrides as a TOML config template.",
    section=EXPLORE,
)
@argument(
    "manager_ids",
    type=Choice(pool.all_manager_ids, case_sensitive=False),
    nargs=-1,
)
@pass_context
def config_template(ctx, manager_ids):
    """Print the overridable attributes of one or more managers as a TOML config
    template.

    Each block is a valid ``[mpm.managers.<id>]`` section ready to paste into a
    standalone config file or a ``[tool.mpm]`` ``pyproject.toml`` block. The output
    lists every overridable field with its current value so it doubles as the
    canonical reference for what each manager exposes: prune the rows that don't
    apply and customize the rest.

    With no positional arguments, every maintained (non-deprecated) manager is
    dumped. Pass one or more manager IDs to restrict the output.
    """
    target_ids = manager_ids or pool.maintained_manager_ids
    overrides = {mid: dump_manager_overrides(pool[mid]) for mid in target_ids}
    echo(tomli_w.dumps({"mpm": {"managers": overrides}}), nl=False)


def cooldown_permits(manager: PackageManager) -> bool:
    """Decide whether a release-introducing operation may run on ``manager``.

    Returns ``True`` when no cooldown is active, when the manager can enforce it
    natively, or when the user opted into running unguarded managers with
    ``--allow-no-cooldown``. Returns ``False`` (after logging the skip) when an active
    cooldown cannot be enforced and the user did not opt in, so the caller leaves the
    manager alone rather than letting a freshly-published version slip in.
    """
    if manager.cooldown is None or manager.supports_cooldown:
        return True
    if manager.allow_no_cooldown:
        logging.warning(
            f"{theme().invoked_command(manager.id)} cannot enforce the release-age "
            "cooldown; running it without the supply-chain safeguard.",
        )
        return True
    logging.warning(
        f"Skip {theme().invoked_command(manager.id)}: it cannot enforce the "
        "release-age cooldown. Use --allow-no-cooldown to run it anyway.",
    )
    return False


@mpm.command(short_help="Install a package.", section=MAINTENANCE)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
# TODO: add a --force/--reinstall flag
@pass_context
def install(ctx, packages_specs):
    """Install one or more packages.

    This subcommand is sensible to the order of the package managers selected by the
    user.

    Installation will first proceed for all the packages found to be tied to a specific
    manager. Which is the case for packages provided with precise package specifiers
    (like purl). This will also happens in situations in which a tighter selection of
    managers is provided by the user.

    For packages whose manager is not known, or if multiple managers are candidates for
    the installation, mpm will try to find the best manager to install it with.

    Installation will be attempted with each manager, in the order they were selected.
    If a search for the package ID returns no result from the highest-priority manager,
    we will skip the installation and try the next available managers in the order of
    their priority.
    """
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.install),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)
    logging.info(
        "Installation priority: > "
        f"{' > '.join(map(theme().invoked_command, manager_ids))}",
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    packages_per_managers = solver.resolve_specs_group_by_managers()

    # Install all packages deterministiccaly tied to a specific manager.
    for manager_id, package_specs in packages_per_managers.items():
        if not manager_id:
            continue
        manager = pool.get(manager_id)
        if not cooldown_permits(manager):
            continue
        for spec in package_specs:
            try:
                logging.info(
                    f"Install {spec} package with "
                    f"{theme().invoked_command(manager_id)}...",
                )
                output = manager.install(spec.package_id, version=spec.version)
            except NotImplementedError:
                logging.warning(
                    f"{theme().invoked_command(manager_id)} "
                    "does not implement install operation.",
                )
                continue
            echo(output)

    unmatched_packages = packages_per_managers.get(None, set())
    # Drop managers that cannot honor an active cooldown (once, not per package).
    eligible_managers = selected_managers
    if unmatched_packages:
        eligible_managers = tuple(m for m in selected_managers if cooldown_permits(m))
    for spec in unmatched_packages:
        for manager in eligible_managers:
            logging.info(
                f"Try to install {spec} with {theme().invoked_command(manager.id)}.",
            )

            # Is the package available on this manager?
            matches = None
            try:
                matches = tuple(
                    manager.refiltered_search(
                        extended=False,
                        exact=True,
                        query=spec.package_id,
                    ),
                )
            except NotImplementedError:
                logging.warning(
                    f"{theme().invoked_command(manager.id)} "
                    "does not implement search operation.",
                )
                logging.info(
                    f"{spec.package_id} existence unconfirmed, "
                    "try to directly install it...",
                )
            except CLIError:
                logging.warning(
                    f"Could not search for {spec.package_id} "
                    f"with {theme().invoked_command(manager.id)}.",
                )
                continue
            else:
                if not matches:
                    logging.warning(
                        f"No {spec.package_id} package found "
                        f"on {theme().invoked_command(manager.id)}.",
                    )
                    continue
                # Prevents any incomplete or bad implementation of exact search.
                if len(matches) != 1:
                    msg = "Exact search returned multiple packages."
                    raise ValueError(msg)

            # Allow install subcommand to fail to have the opportunity to catch the
            # CLIError exception and print a comprehensive message.
            with patch.object(manager, "stop_on_error", True):
                try:
                    logging.info(
                        f"Install {spec} package "
                        f"with {theme().invoked_command(manager.id)}...",
                    )
                    output = manager.install(spec.package_id, version=spec.version)
                except NotImplementedError:
                    logging.warning(
                        f"{theme().invoked_command(manager.id)} "
                        "does not implement install operation.",
                    )
                    continue
                except CLIError:
                    logging.warning(
                        f"Could not install {spec} "
                        f"with {theme().invoked_command(manager.id)}.",
                    )
                    continue

            echo(output)
            ctx.exit()


@mpm.command(aliases=["update"], short_help="Upgrade packages.", section=MAINTENANCE)
@option(
    "-A",
    "--all",
    is_flag=True,
    default=False,
    help="Upgrade all outdated packages. "
    "Will make the command ignore package IDs provided as parameters.",
)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@pass_context
def upgrade(ctx, all, packages_specs):
    """Upgrade one or more outdated packages.

    All outdated package will be upgraded by default if no specifiers are provided as
    arguments. I.e. assumes -A/--all option if no [PACKAGES_SPECS]....

    Packages recognized by multiple managers will be upgraded with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped.
    """
    if not all and not packages_specs:
        logging.info("No package provided, assume -A/--all option.")
        all = True

    # Full upgrade.
    if all:
        if packages_specs:
            # Deduplicate and sort specifiers for terseness.
            logging.warning(
                f"Ignore {', '.join(sorted(set(packages_specs)))} specifiers "
                "and proceed to a full upgrade...",
            )
        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.upgrade_all,
        ):
            if not cooldown_permits(manager):
                continue
            logging.info(
                "Upgrade all outdated packages "
                f"from {theme().invoked_command(manager.id)}...",
            )
            output = manager.upgrade()
            if output:
                logging.info(output)
        ctx.exit()

    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.upgrade),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)

    # Get the subset of selected managers that are implementing the installed operation,
    # so we can query it and know if a package has been installed with it.
    sourcing_managers = tuple(
        ctx.obj.selected_managers(
            keep=manager_ids,
            implements_operation=Operations.installed,
        ),
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    for package_id, spec in solver.resolve_package_specs():
        source_manager_ids = set()
        # Use the manager from the spec.
        if spec.manager_id:
            source_manager_ids.add(spec.manager_id)
        # Package is not bound to a manager by the user's specifiers.
        else:
            logging.info(
                f"{spec} not tied to a manager. Search all managers recognizing it.",
            )
            # Find all the managers that have the package installed.
            for manager in sourcing_managers:
                if package_id in manager.installed_ids:
                    logging.info(
                        f"{package_id} has been installed "
                        f"with {theme().invoked_command(manager.id)}.",
                    )
                    source_manager_ids.add(manager.id)

        if not source_manager_ids:
            logging.error(
                f"{package_id} is not recognized by any of the selected manager. "
                "Skip it.",
            )
            continue

        logging.info(
            f"Upgrade {package_id} "
            f"with {', '.join(map(theme().invoked_command, sorted(source_manager_ids)))}",
        )
        for manager_id in source_manager_ids:
            manager = pool.get(manager_id)
            if not cooldown_permits(manager):
                continue
            output = manager.upgrade(package_id, version=spec.version)
            if output:
                logging.info(output)


@mpm.command(aliases=["uninstall"], short_help="Remove a package.", section=MAINTENANCE)
@argument(
    "packages_specs",
    type=STRING,
    nargs=-1,
    required=True,
    help="A mix of plain <package_id>, simple <package_id@version> specifiers or full "
    "<pkg:npm/left-pad> purls.",
)
@pass_context
def remove(ctx, packages_specs):
    """Remove one or more packages.

    Packages recognized by multiple managers will be remove with each of them. You can
    fine-tune this behavior with more precise package specifiers (like purl) and/or
    tighter selection of managers.

    Packages unrecognized by any selected manager will be skipped.
    """
    # Cast generator to tuple because of reuse.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.remove),
    )
    manager_ids = tuple(manager.id for manager in selected_managers)

    # Get the subset of selected managers that are implementing the installed operation,
    # so we can query it and know if a package has been installed with it.
    sourcing_managers = tuple(
        ctx.obj.selected_managers(
            keep=manager_ids,
            implements_operation=Operations.installed,
        ),
    )

    solver = Solver(packages_specs, manager_priority=manager_ids)
    for package_id, spec in solver.resolve_package_specs():
        source_manager_ids = set()
        # Use the manager from the spec.
        if spec.manager_id:
            source_manager_ids.add(spec.manager_id)
        # Package is not bound to a manager by the user's specifiers.
        else:
            logging.info(
                f"{spec} not tied to a manager. Search all managers recognizing it.",
            )
            # Find all the managers that have the package installed.
            for manager in sourcing_managers:
                if package_id in manager.installed_ids:
                    logging.info(
                        f"{package_id} has been installed "
                        f"with {theme().invoked_command(manager.id)}.",
                    )
                    source_manager_ids.add(manager.id)

        if not source_manager_ids:
            logging.error(
                f"{package_id} is not recognized by any of the selected manager. "
                "Skip it.",
            )
            continue

        logging.info(
            f"Remove {package_id} "
            f"with {', '.join(map(theme().invoked_command, sorted(source_manager_ids)))}",
        )
        for manager_id in source_manager_ids:
            manager = pool.get(manager_id)
            output = manager.remove(package_id)
            if output:
                logging.info(output)


@mpm.command(short_help="Sync local package info.", section=MAINTENANCE)
@pass_context
def sync(ctx):
    """Sync local package metadata and info from external sources."""
    for manager in ctx.obj.selected_managers(implements_operation=Operations.sync):
        logging.info(f"Sync {theme().invoked_command(manager.id)} package info...")
        manager.sync()


@mpm.command(short_help="Cleanup local data.", section=MAINTENANCE)
@pass_context
def cleanup(ctx):
    """Cleanup local data, temporary artifacts and removes orphaned dependencies."""
    for manager in ctx.obj.selected_managers(implements_operation=Operations.cleanup):
        logging.info(f"Cleanup {theme().invoked_command(manager.id)}...")
        manager.cleanup()


@mpm.command(
    aliases=["backup", "lock", "freeze", "snapshot"],
    short_help="Snapshot installed packages to a TOML manifest or a Brewfile.",
    section=SNAPSHOTS,
)
@option(
    "--toml",
    "output_format",
    flag_value="toml",
    default=True,
    help="Emit a TOML manifest with one section per manager. Default.",
)
@option(
    "--brewfile",
    "output_format",
    flag_value="brewfile",
    help=(
        "Emit a Brewfile that `brew bundle install` can consume. Only managers "
        "natively supported by brew bundle are included (brew, cask, mas, vscode, "
        "npm, cargo, uv, winget, flatpak). Other managers are tallied in the "
        "header and excluded from the output."
    ),
)
@option(
    "--overwrite",
    "--force",
    "--replace",
    is_flag=True,
    default=False,
    help="Allow the output file to be silently wiped out if it already exists.",
)
@option(
    "--header/--no-header",
    "include_header",
    default=True,
    help="Include a metadata + warning comment block at the top of the output.",
)
@option(
    "--merge",
    is_flag=True,
    default=False,
    help="TOML only. Read the provided file and add each new entry to it. "
    "Requires the [OUTPUT_PATH] argument.",
)
@option(
    "--update-version",
    is_flag=True,
    default=False,
    help="TOML only. Read the provided file and update each existing entry with "
    "the version currently installed on the system. Requires the [OUTPUT_PATH] "
    "argument.",
)
@argument(
    "output_path",
    type=file_path(writable=True, resolve_path=True, allow_dash=True),
    default="-",
)
@pass_context
def dump(
    ctx, output_format, overwrite, include_header, merge, update_version, output_path
):
    """Dump installed packages to a TOML manifest or a Brewfile.

    By default emits TOML, one section per manager (one entry per package, keyed
    by package ID, with the installed version as the value). Pass ``--brewfile``
    to emit a Brewfile compatible with ``brew bundle install``.

    With no [OUTPUT_PATH] argument, writes to stdout. TOML files are readable by
    ``mpm restore``.

    ``--merge`` and ``--update-version`` operate on an existing TOML file; both
    require the [OUTPUT_PATH] argument and neither is valid with ``--brewfile``.
    """
    # --merge / --update-version are TOML-only.
    if output_format == "brewfile" and (merge or update_version):
        logging.critical(
            "--merge / --update-version cannot be combined with --brewfile.",
        )
        ctx.exit(2)
    if merge and update_version:
        logging.critical("--merge and --update-version are mutually exclusive.")
        ctx.exit(2)

    if output_format == "brewfile":
        if is_stdout(output_path):
            if overwrite:
                logging.warning("Ignore the --overwrite/--force/--replace option.")
            logging.info(f"Print Brewfile to {sys.stdout.name}")
        else:
            logging.info(f"Dump installed packages as a Brewfile into {output_path}")
            if output_path.exists():
                if overwrite:
                    logging.warning("Target file exist and will be overwritten.")
                else:
                    logging.critical("Target file exist and will be overwritten.")
                    ctx.exit(2)
        _dump_brewfile(ctx, output_path, include_header=include_header)
        return

    # TOML path: preserve the existing `mpm backup` flag-validation flow so that
    # scripts piping the log lines through INFO-level filtering keep working.
    if is_stdout(output_path):
        if merge:
            logging.critical(
                "--merge requires the [OUTPUT_PATH] argument to point to a file.",
            )
            ctx.exit(2)
        if update_version:
            logging.critical(
                "--update-version requires the [OUTPUT_PATH] argument to point "
                "to a file.",
            )
            ctx.exit(2)
        if overwrite:
            logging.warning("Ignore the --overwrite/--force/--replace option.")
        logging.info(f"Print installed package list to {sys.stdout.name}")
    else:
        if merge:
            logging.info(f"Merge all installed packages into {output_path}")
        elif update_version:
            logging.info(
                f"Update in-place all versions of installed packages "
                f"found in {output_path}",
            )
        else:
            logging.info(f"Dump all installed packages into {output_path}")

        if output_path.exists():
            if overwrite:
                logging.warning("Target file exist and will be overwritten.")
            else:
                if merge or update_version:
                    logging.warning("Ignore the --overwrite/--force/--replace option.")
                else:
                    logging.critical("Target file exist and will be overwritten.")
                    ctx.exit(2)
        elif merge:
            logging.critical("--merge requires an existing file.")
            ctx.exit(2)
        elif update_version:
            logging.critical("--update-version requires an existing file.")
            ctx.exit(2)

        if output_path.suffix.lower() != ".toml":
            logging.critical("Target file is not a TOML file.")
            ctx.exit(2)

    _dump_toml(
        ctx,
        output_path,
        include_header=include_header,
        merge=merge,
        update_version=update_version,
    )


def _dump_toml(
    ctx,
    output_path,
    *,
    include_header: bool,
    merge: bool = False,
    update_version: bool = False,
) -> None:
    """Render the installed inventory as a TOML manifest.

    Supports the same three modes the historical ``mpm backup`` exposed: a
    one-shot dump, ``--merge`` (add new entries to an existing file), and
    ``--update-version`` (refresh the version of entries already in the file).
    Callers are expected to have validated flag combinations and output-path
    constraints upstream.
    """
    installed_data: dict[str, dict[str, str]] = {}
    fields = ("id", "installed_version")

    if merge or update_version:
        installed_data = tomllib.loads(output_path.read_text(encoding="utf-8"))

    content = ""
    if include_header:
        content = (
            f"# Generated by mpm v{__version__}.\n"
            f"# Timestamp: {datetime.now(tz=timezone.utc).isoformat()}.\n\n"
        )

    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        logging.info(
            f"Dumping packages from {theme().invoked_command(manager.id)}...",
        )
        try:
            packages = tuple(packages_asdict(manager.installed, fields))
        except CLIError:
            logging.warning(
                f"Could not list installed packages from "
                f"{theme().invoked_command(manager.id)}.",
            )
            packages = ()
        for pkg in packages:
            if update_version:
                if pkg["id"] in installed_data.get(manager.id, {}):
                    installed_data[manager.id][pkg["id"]] = str(
                        pkg["installed_version"],
                    )
            else:
                installed_data.setdefault(manager.id, {})[pkg["id"]] = str(
                    pkg["installed_version"],
                )
        if installed_data.get(manager.id):
            installed_data[manager.id] = dict(
                sorted(
                    installed_data[manager.id].items(),
                    key=lambda i: (i[0].lower(), i[0]),
                ),
            )

    content += "\n".join(
        tomli_w.dumps({manager_id: packages})
        for manager_id, packages in installed_data.items()
    )

    echo(content, file=prep_path(output_path))

    if ctx.obj.summary:
        print_summary(Counter({k: len(v) for k, v in installed_data.items()}))


def _dump_brewfile(ctx, output_path, *, include_header: bool) -> None:
    """Render the installed inventory as a Brewfile.

    Filters selected managers down to those with a configured
    :py:attr:`PackageManager.brewfile_entry_type`. Counts packages from skipped
    managers so the header can show what was dropped, and emits a stderr
    warning for any skipped manager that defines :py:attr:`brewfile_skip_warning`
    (used by ``vscodium`` to flag the silent-misinstall risk).
    """
    mappable_managers = []
    skipped_counts: Counter[str] = Counter()
    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        if manager.brewfile_entry_type is None:
            try:
                installed_count = sum(1 for _ in manager.installed)
            except CLIError:
                logging.warning(
                    f"Could not list installed packages from "
                    f"{theme().invoked_command(manager.id)}.",
                )
                continue
            skipped_counts[manager.id] = installed_count
            if installed_count and manager.brewfile_skip_warning:
                logging.warning(
                    manager.brewfile_skip_warning.format(count=installed_count),
                )
            continue
        mappable_managers.append(manager)

    content = build_brewfile(
        mappable_managers,
        include_header=include_header,
        skipped_counts=skipped_counts,
        platform=current_platform().name,
    )

    echo(content, file=prep_path(output_path), nl=False)

    if ctx.obj.summary:
        section_counts: Counter[str] = Counter()
        for line in content.splitlines():
            if not line or line.startswith("#"):
                continue
            entry_type = line.split(" ", 1)[0]
            section_counts[entry_type] += 1
        print_summary(section_counts)


@mpm.command(
    short_help="Install packages referenced in TOML files.",
    section=SNAPSHOTS,
)
@argument("toml_files", type=File("r"), required=True, nargs=-1)
@pass_context
def restore(ctx, toml_files):
    """Read TOML files then install or upgrade each package referenced in them."""
    # TODO: add an artificial order for managers, so that the [cask] section can install
    # mas CLI first then have [mas] section work in one-go. Use-case: my dotfiles.
    for toml_input in toml_files:
        is_stdin = isinstance(toml_input, TextIOWrapper)
        if is_stdin:
            toml_input.reconfigure(encoding="utf-8")
            toml_filepath = toml_input.name
            toml_content = toml_input.read()
        else:
            toml_filepath = Path(toml_input.name).resolve()
            toml_content = toml_filepath.read_text(encoding="utf-8")

        logging.info(f"Load package list from {toml_filepath}")
        doc = tomllib.loads(toml_content)

        # List unrecognized sections.
        ignored_sections = [
            f"[{section}]" for section in doc if section not in pool.all_manager_ids
        ]
        if ignored_sections:
            plural = "s" if len(ignored_sections) > 1 else ""
            sections = ", ".join(ignored_sections)
            logging.info(f"Ignore {sections} section{plural}.")

        for manager in ctx.obj.selected_managers(
            implements_operation=Operations.install,
        ):
            if manager.id not in doc:
                logging.warning(
                    f"No [{theme().invoked_command(manager.id)}] section found.",
                )
                continue
            logging.info(f"Restore {theme().invoked_command(manager.id)} packages...")
            for package_id, version in doc[manager.id].items():
                spec = Specifier(
                    raw_spec=f"pkg:{manager.id}:/{package_id}{VERSION_SEP}{package_id}",
                    package_id=package_id,
                    manager_id=manager.id,
                    version=str(version),
                )
                logging.info(f"Install {spec}...")
                output = manager.install(spec.package_id, version=spec.version)
                echo(output)


@mpm.command(
    short_help="Export installed packages to a SBOM document.",
    section=SBOM_SECTION,
)
@option(
    "--spdx/--cyclonedx",
    default=True,
    help="SBOM standard to export to.",
)
@option(
    "--format",
    "export_format",
    type=EnumChoice(ExportFormat),
    help=f"File format of the export. Defaults to JSON for {sys.stdout.name}. If not "
    "provided, will be autodetected from file extension.",
)
@option(
    "--overwrite",
    "--force",
    "--replace",
    is_flag=True,
    default=False,
    help="Allow the target file to be silently wiped out if it already exists.",
)
@option(
    "--bundled/--minimal",
    default=True,
    help=(
        "Bundled mode (the default) queries each manager for richer "
        "metadata (license, supplier, homepage, checksums, declared "
        "dependencies) and merges per-package upstream SBOM documents into "
        "the aggregate when the manager publishes them (like Homebrew's "
        "HOMEBREW_SBOM=1 per-formula files). Minimal mode lists installed "
        "packages with the bare inventory data (name, version, purl) and "
        "skips the metadata extractors entirely. Bundled mode is slower "
        "because it may shell out or read on-disk SBOM files per package; "
        "pick --minimal for fast inventory snapshots."
    ),
)
@argument(
    "export_path",
    type=file_path(writable=True, resolve_path=True, allow_dash=True),
    default="-",
)
@pass_context
def sbom(ctx, spdx, export_format, overwrite, bundled, export_path):
    """Export list of installed packages to a SPDX or CycloneDX file."""
    standard = "SPDX" if spdx else "CycloneDX"

    if is_stdout(export_path):
        if overwrite:
            logging.warning("Ignore the --overwrite/--force/--replace option.")
        logging.info(f"Print {standard} export to {sys.stdout.name}")

    else:
        logging.info(f"Export installed packages in {standard} to {export_path}")
        if export_path.exists():
            msg = "Target file exist and will be overwritten."
            if overwrite:
                logging.warning(msg)
            else:
                logging.critical(msg)
                ctx.exit(2)

    # <stdout> format defaults to JSON.
    if is_stdout(export_path):
        if not export_format:
            export_format = ExportFormat.JSON
    # If no export format has been provided, guess it from file name.
    else:
        guessed_format = SBOM.autodetect_export_format(export_path)
        if not export_format:
            if not guessed_format:
                # On Python 3.10, ``ExportFormat`` extends ``backports.strenum.StrEnum``
                # whose typeshed stub omits ``__iter__``; iteration is provided by the
                # ``EnumMeta`` metaclass at runtime.
                supported = ", ".join(
                    f.value
                    for f in ExportFormat  # type: ignore[attr-defined]
                )
                logging.critical(
                    f"Cannot guess export format from {export_path.name!r}. "
                    f"Use --format to pick one of: {supported}."
                )
                ctx.exit(2)
            export_format = guessed_format
        elif guessed_format and export_format != guessed_format:
            logging.critical(f"Selected {export_format} does not match file extension.")
            ctx.exit(2)

    sbom_class: type[SBOM]
    if spdx:
        if not spdx_support:
            raise UsageError(
                "SPDX SBOM generation requires the [sbom] extra. "
                "Install with: pip install meta-package-manager[sbom]",
            )
        sbom_class = SPDX
    else:
        if not cyclonedx_support:
            raise UsageError(
                "CycloneDX SBOM generation requires the [sbom] extra. "
                "Install with: pip install meta-package-manager[sbom]",
            )
        if export_format not in (ExportFormat.JSON, ExportFormat.XML):
            logging.critical(f"{standard} does not support {export_format} format.")
            ctx.exit(2)
        sbom_class = CycloneDX

    sbom = sbom_class(export_format)
    sbom.init_doc()
    sbom.set_scan_completeness(bundled=bundled)

    for manager in ctx.obj.selected_managers(implements_operation=Operations.installed):
        logging.info(f"Export packages from {theme().invoked_command(manager.id)}...")
        try:
            installed_packages = list(manager.installed)
        except CLIError:
            logging.warning(
                f"Could not export packages from {theme().invoked_command(manager.id)}."
            )
            continue

        if not bundled:
            for package in installed_packages:
                sbom.add_package(manager, package)
            continue

        try:
            enriched = manager.package_metadata_batch(installed_packages)
            for package, metadata in enriched:
                sbom.add_package(manager, package, metadata)
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                f"Falling back to minimal SBOM data for "
                f"{theme().invoked_command(manager.id)}: {exc}"
            )
            for package in installed_packages:
                sbom.add_package(manager, package)

    sbom.finalize()
    if ctx.obj.summary:
        print_summary(*sbom_summary(sbom, bundled))
    echo(sbom.export(), file=prep_path(export_path))
