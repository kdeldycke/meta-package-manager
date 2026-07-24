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
"""The {command}`mpm` command-line interface: the group and its shared plumbing.

Defines the Click command group (global options, manager selection, the
`GlobalOptions` state every subcommand reads) and the helpers several
subcommand modules share: the inventory snapshot, the per-package action
engine, the failure gates and the file-output guards.

The subcommands themselves live in one module per help section —
{mod}`meta_package_manager.cli_explore` (the read-only queries),
{mod}`meta_package_manager.cli_maintenance` (the state changers and
diagnostics), {mod}`meta_package_manager.cli_snapshots` (manifest export and
replay) and {mod}`meta_package_manager.cli_sbom` — imported at the bottom of
this module so their `@mpm.command` registrations run. Each subcommand
selects the managers from {mod}`meta_package_manager.pool` that implement the
matching {class}`meta_package_manager.capabilities.Operations` action, runs it
across all of them, and renders the aggregated, multi-manager result.
"""

from __future__ import annotations

import logging
import platform
import threading
from collections.abc import Iterable
from configparser import RawConfigParser
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from textwrap import dedent

from click_extra import (
    STRING,
    Choice,
    Duration,
    IntRange,
    Section,
    VersionOption,
    echo,
    group,
    jobs_option,
    option,
    option_group,
    pass_context,
    search_params,
    sort_by_option,
    zero_exit_option,
)
from click_extra.context import (
    PROGRESS,
    TABLE_FORMAT,
    VERBOSITY_LEVEL,
    ZERO_EXIT,
)
from click_extra.execution import install_interrupt_handler
from click_extra.highlight import HelpKeywords
from click_extra.logging import LogLevel
from click_extra.table import SERIALIZATION_FORMATS
from click_extra.theme import get_current_theme as theme
from extra_platforms import current_architecture, current_platform

from . import bar_plugin
from .config import (
    MpmConfig,
    apply_manager_overrides_from_context,
    build_manager_overrides_validator,
    print_contribution_hints,
    register_config_managers_from_context,
)
from .execution import PLAN_RECORDER, CLIError
from .manager import PackageManager
from .package import Package
from .pool import pool
from .specifier import VERSION_SEP, Specifier
from .tables import SortableField

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import IO

    from click_extra import Context, Parameter


# Subcommand sections.
EXPLORE = Section("Explore subcommands")
MAINTENANCE = Section("Maintenance subcommands")
SNAPSHOTS = Section("Package snapshots subcommands")
SBOM_SECTION = Section("SBOM subcommands")


XKCD_MANAGER_ORDER = ("pip", "brew", "npm", "dnf", "apt", "steamcmd")
"""Sequence of package managers as defined by [XKCD #1654: Universal Install Script](https://xkcd.com/1654/).

See the corresponding [implementation rationale in issue #10](https://github.com/kdeldycke/meta-package-manager/issues/10).
"""


@dataclass(frozen=True)
class GlobalOptions:
    """Global options and selection state every subcommand reads from `ctx.obj`.

    Built once by the `mpm` group body, after the eager option callbacks have
    accumulated the manager selectors into the transient `ctx.obj` dict this
    instance replaces (see {func}`update_manager_selection`).
    """

    all_managers: bool
    """Include unsupported and deprecated managers in the selection."""

    user_selection: list[str] | None
    """Managers explicitly selected by the user, in priority order, or `None`."""

    user_drops: set[str] | None
    """Managers explicitly excluded by the user, or `None`."""

    selected_managers: Callable[..., Iterator[PackageManager]]
    """Resolve the target managers, applying selection and manager-level options."""

    description: bool
    """Show package description in results."""

    summary: bool
    """Print the end-of-run summary on stderr."""

    network: bool
    """Allow network calls during the run."""

    timeout: int | None
    """User-set maximum duration in seconds for each CLI call, or `None`."""


COOLDOWN_SUPPORTED_MANAGERS = tuple(
    sorted(mid for mid, manager in pool.items() if manager.supports_cooldown)
)
"""IDs of the managers that natively enforce a release-age `mpm --cooldown`.

Derived from the pool so the `--cooldown` help text never drifts from the set of
managers that actually carry a {attr}`cooldown_env_var
<meta_package_manager.execution.CLIExecutor.cooldown_env_var>`: adding cooldown
support to a manager surfaces it here automatically.
"""


def is_stdout(filepath: Path) -> bool:
    """Check if a file path is set to stdout.

    Prevents the creation of a `-` file in the current directory.
    """
    return str(filepath) == "-"


def prep_path(filepath: Path) -> IO | None:
    """Prepare the output file parameter for Click's echo function."""
    if is_stdout(filepath):
        return None
    return filepath.open("w", encoding="UTF-8")


def guard_existing_output(ctx: Context, output_path: Path, *, overwrite: bool) -> None:
    """Block clobbering an existing output file unless `overwrite` is set.

    Warns and exits with code 2 when `output_path` already exists and the user
    did not pass `--overwrite`/`--force`/`--replace`. No-op when the file
    is absent. Callers handle the stdout case separately.
    """
    if output_path.exists():
        msg = "Target file exist and will be overwritten."
        if overwrite:
            logging.warning(msg)
        else:
            logging.critical(msg)
            ctx.exit(2)


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
    """Print the location of the {doc}`Xbar/SwiftBar plugin <bar-plugin>`.

    Returns the normalized path of the standalone [bar_plugin.py](https://github.com/kdeldycke/meta-package-manager/blob/main/meta_package_manager/bar_plugin.py)
    script that is distributed with this Python module. This
    is made available under the `mpm --bar-plugin-path` option.

    Notice that the fully-qualified home directory get replaced by its
    shorthand (`~`) if applicable:

    - the full `/home/user/.python/site-packages/mpm/bar_plugin.py` path is
      simplified to `~/.python/site-packages/mpm/bar_plugin.py`,
    - but `/usr/bin/python3.10/mpm/bar_plugin.py` is returned as-is.
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
    # Verbosity stays at click-extra's WARNING default: the ✓/✗ trail and finisher
    # print via echo (not logging) and survive it, so a default run shows just those
    # plus real warnings and critical. Per-operation narration (priority,
    # announcements, skip reasons) sits at INFO, one --verbosity INFO away.
    config_schema=MpmConfig,
    config_validators=(build_manager_overrides_validator(pool),),
    version_fields={
        "env_info": (
            f"Python {platform.python_version()}, "
            f"{current_platform().name} {current_architecture().name}"
        ),
    },
)
# Honored by exit_on_failures(): the action commands' per-package failures then
# report without gating automation on a non-zero exit code.
@zero_exit_option
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
        "--sudo/--no-sudo",
        default=None,
        help="Force running privileged manager operations with (or without) sudo. "
        "Unset by default, letting each manager decide: system managers (apt, dnf, "
        "pacman, ...) escalate, user-level managers do not. When escalation is needed "
        "on a terminal, mpm authenticates once up front instead of prompting mid-run; "
        "off a terminal, managers needing root fail fast rather than stalling.",
    ),
    option(
        "-d",
        "--dry-run",
        is_flag=True,
        default=False,
        help="Do not actually perform any action, just simulate CLI calls.",
    ),
    option(
        "-p",
        "--plan",
        is_flag=True,
        default=False,
        help="Print the exact package-manager commands each state-changing operation "
        "would run, without running them. Read-only queries (installed, outdated, "
        "search) still run, so install, remove and upgrade --all resolve to the "
        "commands they would actually execute against real system state. The plan "
        "prints to stdout, one copy-pasteable command per line.",
    ),
    option(
        "-t",
        "--timeout",
        type=IntRange(min=0),
        default=None,
        help="Maximum duration in seconds for each CLI call. Applies to every "
        "manager and operation. When unset, a per-operation default is used "
        "instead: a short cap for read-only queries (installed, outdated, search) "
        "and a longer one for state-changing operations (install, upgrade, remove, "
        "sync, cleanup).",
    ),
    jobs_option(
        "-j",
        "--jobs",
        help="Maximum number of managers to run concurrently. Defaults to one "
        "less than the CPU count; set 1 to run sequentially. Applies to read-only "
        "queries (installed, outdated, search), maintenance commands (sync, "
        "cleanup, upgrade --all), and the state changers (install, remove, "
        "upgrade, restore), which fan out across managers while running each "
        "manager's own packages one at a time. Installing a package left untied "
        "to a manager stays sequential.",
    ),
    option(
        "--cooldown",
        type=Duration(),
        default="",
        show_default="disabled",
        metavar="DURATION",
        help="Refuse to install or upgrade any package version published more "
        "recently than this duration, as a mitigation against supply-chain "
        "attacks. Accepts a friendly duration ('7 days', '1 week', '12h'), an "
        "ISO 8601 duration ('P7D', 'PT12H'), or an RFC 3339 absolute timestamp "
        "('2024-05-01T00:00:00Z'). Only honored by managers with native "
        "release-age support (" + ", ".join(COOLDOWN_SUPPORTED_MANAGERS) + "); the "
        "others are skipped unless --allow-unsupported-managers is set.",
    ),
    option(
        "--require-cooldown-support/--allow-unsupported-managers",
        default=True,
        help="When --cooldown is set, whether to require each manager to natively "
        "enforce it. The default (--require-cooldown-support) skips managers that "
        "cannot, so nothing slips in unguarded (fail-closed). "
        "--allow-unsupported-managers runs install and upgrade on them anyway, "
        "trading the supply-chain safeguard for broader manager coverage.",
    ),
)
@option_group(
    "Output options",
    option(
        "--description",
        is_flag=True,
        default=False,
        help="Show package description in results. Shorthand for adding the "
        "'description' column to 'mpm search'; an explicit --columns selection "
        "wins.",
    ),
    # Bare field IDs declare a click-extra field vocabulary: the selection is
    # resolved per table at print time, from the fields its headers carry.
    sort_by_option(
        *SortableField,
        param_decls=("-s", "--sort-by"),
        default=(SortableField.MANAGER_ID,),
        help="Sort results by this field. Repeat to add tie-breakers in priority "
        "order, like '-s manager_id -s package_id'.",
    ),
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
        "--network/--no-network",
        default=False,
        help=(
            "Opt into network calls during the run. Today this only "
            "affects 'mpm sbom', which uses the flag to query OSV.dev "
            "for vulnerability data and attach it to the rendered "
            "document. Responses are cached on disk so repeat runs are "
            "fast. Defaults off; the offline path remains the default. "
            "Note: when enabled, this transmits the package inventory "
            "to the queried services."
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
    sudo,
    dry_run,
    plan,
    timeout,
    cooldown,
    require_cooldown_support,
    description,
    summary,
    network,
    suggest_contribs,
):
    """CLI options shared by all subcommands."""
    # Make the first Ctrl+C terminate any in-flight package-manager subprocesses so a
    # concurrent fan-out (upgrade, install, ...) aborts cleanly instead of hanging on
    # worker threads whose children survived the terminal signal. Restored on close.
    # See meta_package_manager.execution for the full rationale.
    install_interrupt_handler(ctx)

    # Plan mode collects the state-changing commands it would run (see
    # CLIExecutor.run) into a process-wide recorder, then prints them to stdout at
    # close, one copy-pasteable line each. Reset first so a previous in-process
    # invocation (the test suite drives the CLI repeatedly) cannot leak into this one.
    if plan:
        PLAN_RECORDER.reset()

        def flush_plan():
            for command in PLAN_RECORDER.render():
                echo(command)

        ctx.call_on_close(flush_plan)

    # Silence all log messages for serialization rendering unless in debug mode.
    if (
        ctx.meta[TABLE_FORMAT] in SERIALIZATION_FORMATS
        and ctx.meta[VERBOSITY_LEVEL] != LogLevel.DEBUG
    ):
        logging.disable()

        def remove_logging_override():
            """Reset the logging override to its default state.

            `logging.disable()` mess with the logging module internals at the root
            level. We need to restore the default behavior when the context is closed,
            otherwise the logging module will be stuck in a disabled state.

            See: https://docs.python.org/3/library/logging.html?highlight=logging#logging.disable
            """
            logging.disable(logging.NOTSET)

        ctx.call_on_close(remove_logging_override)

    # click-extra's default --progress/--no-progress option resolves the user's
    # intent (lowered by --accessible) into ctx.meta[PROGRESS],
    # decoupled from color. mpm layers on its own output-mode gating: no spinner in
    # serialized output or at DEBUG verbosity (where logs already narrate). The TTY
    # and TERM=dumb checks are left to the spinner widget (see _make_spinner).
    show_progress = (
        ctx.meta[PROGRESS]
        and ctx.meta[TABLE_FORMAT] not in SERIALIZATION_FORMATS
        and ctx.meta[VERBOSITY_LEVEL] != LogLevel.DEBUG
    )

    # Register any brand-new managers defined in [mpm.managers.<id>] sections, then
    # apply per-manager attribute overrides, both before any subcommand observes the
    # pool. Registration is the authoritative pass (covers config sources the eager
    # pre-load in __main__ could not reach); overrides also collect contribution-hint
    # candidates onto ctx.meta for the close-time callback below.
    register_config_managers_from_context(ctx, pool)
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
        """End-of-run record when underlying CLIs reported errors.

        Each failed run already relayed its own diagnosis at `WARNING` the
        moment it happened (see the failure gate in
        {meth}`~meta_package_manager.execution.CLIExecutor.run`), so this
        closing line is the aggregated durable record: the one-liner to grep
        in scrollback or CI logs. A successful command's stderr chatter (gem
        extension warnings, mas Spotlight noise) still stays out of the
        default view: only failures relay. The `DEBUG` pointer remains for
        the full transcript (raw streams, timings, environment), which no
        post-hoc excerpt reproduces.

        Skipped at DEBUG verbosity (the raw streams appeared inline) and
        in serialization formats (logging is disabled and `cli_errors`
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
            f"({ids}); full transcript at --verbosity DEBUG.",
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

        The selection summary is logged at `DEBUG` on the first call only. The
        `✓`-trailed spinner from
        {func}`meta_package_manager.dispatch.collect_from_managers` already names every
        manager that ran, so this summary is redundant at default verbosity for
        read-only commands; it is kept for troubleshooting, where it also surfaces
        config-driven drops that never appear in the trail. Logging on the first call
        only keeps subcommands that never resolve the pool (like `--help`) silent.

        Callers may pass `keep=<ids>` to narrow the selection to a specific
        subset (for example, the managers that implement a given operation).
        When provided it overrides the global `user_selection` for that call.
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
            sudo=sudo,
            dry_run=dry_run,
            plan=plan,
            timeout=timeout,
            progress=show_progress,
            # Minimum release age gate and its fail-open escape hatch.
            cooldown=cooldown,
            require_cooldown_support=require_cooldown_support,
            **kwargs,
        )

    # Replace the transient selector-accumulation dict with the frozen options
    # object every subcommand reads.
    ctx.obj = GlobalOptions(
        all_managers=all_managers,
        user_selection=user_selection,
        user_drops=managers_to_remove,
        selected_managers=selected_managers,
        description=description,
        summary=summary,
        network=network,
        timeout=timeout,
    )


# Extend --version output with Python and platform metadata.
version_option = search_params(mpm.params, VersionOption)
if isinstance(version_option, VersionOption):
    version_option.message = "{prog_name}, version {version}\n{env_info}"

# Highlight placeholder option names that appear in the help text prose.
mpm.extra_keywords = HelpKeywords(  # type: ignore[attr-defined]
    long_options={"--<manager-id>", "--no-<manager-id>"},
)
# "version" is a --sort-by choice but too common a word in help text.
mpm.excluded_keywords = HelpKeywords(choices={"version"})  # type: ignore[attr-defined]


def _cli_errors(manager: PackageManager) -> list[str]:
    """Serialize the distinct CLI errors `manager` accumulated so far.

    Collected at the last minute — after the manager's query ran — so the list
    gathers everything the run produced. A non-empty list marks the manager's
    `✗` in the concurrent spinner trail (see
    {func}`meta_package_manager.dispatch.collect_from_managers`) and ships in
    the serialized payloads.
    """
    return list({expt.error for expt in manager.cli_errors})


def _snapshot_installed(
    manager: PackageManager,
    query: str | None,
    *,
    exact: bool,
) -> tuple[Package, ...]:
    """Materialize the manager's installed inventory, filtered by `query`.

    The shared fetch of every inventory consumer (`installed`, `dump`,
    `dump --brewfile`, `sbom`): a best-effort
    {meth}`~meta_package_manager.manager.PackageManager.installed_or_empty`
    snapshot (a broken manager yields no packages instead of aborting the batch),
    post-filtered through {func}`_filter_matches`.
    """
    return tuple(_filter_matches(manager.installed_or_empty(), query, exact=exact))


def _filter_matches(
    packages: Iterable[Package],
    query: str | None,
    *,
    exact: bool,
) -> Iterator[Package]:
    """Yield only the packages matching `query` on their ID or name.

    A transparent pass-through when `query` is `None` (no positional query was
    given). Shared by the `installed` and `outdated` subcommands to post-filter
    the fully-materialized package list each manager returns: unlike `search`,
    these operations already hold the complete inventory, so the query is a local
    refinement rather than a manager-side lookup. Mirrors the fuzzy/`--exact`
    semantics of `search` through
    {meth}`meta_package_manager.package.Package.matches`.
    """
    for package in packages:
        if query is None or package.matches(query, exact=exact):
            yield package


query_option = option(
    "--query",
    type=STRING,
    default=None,
    metavar="QUERY",
    help="Only keep installed packages whose ID or name matches QUERY. Fuzzy "
    "by default (case-insensitive, tokenized); see --exact.",
)
"""`--query` filter of the inventory exporters (`dump`, `sbom`)."""

query_exact_option = option(
    "--exact/--fuzzy",
    default=False,
    help="With --query, require a verbatim match on the package ID or name instead "
    "of the default fuzzy match. No effect without --query.",
)
"""`--exact` refinement of {data}`query_option`."""

overwrite_option = option(
    "--overwrite",
    "--force",
    "--replace",
    is_flag=True,
    default=False,
    help="Allow the target file to be silently wiped out if it already exists.",
)
"""Opt-in clobbering of an existing output file (`dump`, `sbom`); see
{func}`guard_existing_output`."""


def package_label(spec: Specifier) -> str:
    """Render a spec as `package_id` or `package_id@version` for trail output."""
    if spec.version:
        return f"{spec.package_id}{VERSION_SEP}{spec.version}"
    return spec.package_id


def _run_manager_action(
    manager: PackageManager,
    spec: Specifier,
    *,
    action: Callable[[PackageManager, Specifier], str | None],
    verb: str,
    operation: str,
) -> bool:
    """Run `action(manager, spec)` for one package, returning success.

    The shared core of every per-package attempt (`install`, `remove`,
    `upgrade <packages>`, `restore`, and both `install` dispatch paths). The
    action runs under {meth}`~meta_package_manager.execution.CLIExecutor.acting_as`
    with `operation` stamped (resolving the right per-operation timeout and
    watchdog policy, scoped to the attempt) and the manager forced to raise on
    failure, so a botched operation is recorded by the caller rather than
    silently swallowed. Narrates the per-attempt reason at `INFO` and logs the
    CLI output on success. The caller maps the boolean onto its own `✓`/`✗`
    ledger and retry/stop semantics.
    """
    with manager.acting_as(operation, stop_on_error=True):
        try:
            output = action(manager, spec)
        except NotImplementedError:
            logging.info(
                f"Does not implement {verb} operation.",
                extra={"label": manager.id},
            )
            return False
        except CLIError:
            logging.info(
                f"Could not {verb} {package_label(spec)}.",
                extra={"label": manager.id},
            )
            return False
    if output:
        logging.info(output, extra={"label": manager.id})
    return True


def _install_action(manager: PackageManager, spec: Specifier) -> str | None:
    """The canonical install `action`, shared by `install` and `restore`."""
    return manager.install(spec.package_id, version=spec.version)


def _package_task(
    manager: PackageManager,
    spec: Specifier,
    lock: threading.Lock,
    *,
    action: Callable[[PackageManager, Specifier], str | None],
    verb: str,
    past: str,
    prep: str,
    operation: str,
    record_failure: Callable[[Specifier], None],
) -> Callable[[], tuple[bool, str]]:
    """Build one per-package task for {func}`collect_per_package`.

    Runs the attempt through {func}`_run_manager_action` and returns
    `(ok, message)` for the `✓`/`✗` trail. On failure it appends the spec to a
    caller-owned list through `record_failure` (under `lock`, since the list is
    shared across the concurrent lanes) and reports `✗`. Shared by `install`,
    `remove`, `upgrade <packages>` and `restore`, whose tasks differ only in
    the action, the verb forms, and which failure list they feed.

    :param action: performs the manager operation, returning its CLI output (or `None`).
    :param verb: present-tense operation name ("install"), for the `INFO` lines and
        the "failed to {verb}" trail.
    :param past: past participle ("installed"), for the success trail.
    :param prep: preposition joining the package and the manager ("with", "from").
    :param operation: {class}`~meta_package_manager.capabilities.Operations` member
        name stamped on the manager for the duration of the attempt.
    :param record_failure: appends the failed spec's label to a caller-owned list.
    """
    mgr = theme().invoked_command(manager.id)

    def task() -> tuple[bool, str]:
        if _run_manager_action(
            manager, spec, action=action, verb=verb, operation=operation
        ):
            return True, f"{package_label(spec)} {past} {prep} {mgr}"
        with lock:
            record_failure(spec)
        return False, f"{package_label(spec)} failed to {verb} {prep} {mgr}"

    return task


def fail_unless_zero_exit(ctx: Context, message: str) -> None:
    """Print the durable `critical: {message}` record, then exit `1` unless
    `-0`/`--zero-exit` opted out of the gate.

    The shared failure gate of the action commands ({func}`exit_on_failures`)
    and `doctor`: the summary always prints, following the linter convention
    where findings gate automation, and `-0` keeps the exit code at `0` with
    the printed summary staying the durable record. Usage and configuration
    errors are unaffected: they exit `2` regardless, as genuine execution
    failures.
    """
    logging.critical(message)
    if not ctx.meta.get(ZERO_EXIT):
        ctx.exit(1)


def exit_on_failures(ctx: Context, verb: str, failures: Iterable[object]) -> None:
    """Report the per-package `failures` collected this run and exit non-zero.

    A no-op when `failures` is empty. Otherwise routes the deduplicated, sorted
    ``Could not {verb}: ...`` summary through {func}`fail_unless_zero_exit`.
    Shared by every action command (`install`, `remove`, `upgrade <packages>`,
    `restore`).
    """
    items = sorted({str(failure) for failure in failures})
    if not items:
        return
    fail_unless_zero_exit(ctx, f"Could not {verb}: " + ", ".join(items) + ".")


# Register every subcommand module onto the group. Placed at the bottom so the
# `mpm` group and the shared helpers above exist by the time each module's
# `@mpm.command` decorators run; the imports are for their registration
# side effect only.
from . import (
    cli_explore,  # noqa: F401
    cli_maintenance,  # noqa: F401
    cli_sbom,  # noqa: F401
    cli_snapshots,  # noqa: F401
)
