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
"""The explore subcommands: the read-only queries and inspection tools.

`managers`, `installed`, `outdated`, `orphans`, `search`, `which` and
`config-template`, plus the query plumbing they share: the concurrent
collect prelude, the row builders and the query-match highlighter. Every
command here only reads system state and renders a table (or its serialized
counterpart).

The `mpm` group itself, and the plumbing shared with the other subcommand
modules, live in {mod}`meta_package_manager.cli`.
"""

from __future__ import annotations

import logging
from functools import partial

import tomli_w
from boltons.cacheutils import LRI, cached
from click_extra import (
    STRING,
    Choice,
    argument,
    columns_option,
    echo,
    option,
    pass_context,
)
from click_extra.context import SORT_BY, TABLE_FORMAT
from click_extra.highlight import highlight
from click_extra.table import SERIALIZATION_FORMATS
from click_extra.theme import KO_GLYPH, OK_GLYPH, get_current_theme as theme
from extra_platforms import reduce

from .bar_plugin_renderer import BarPluginRenderer
from .capabilities import Operations
from .cli import (
    EXPLORE,
    _cli_errors,
    _filter_matches,
    _snapshot_installed,
    mpm,
)
from .config import dump_manager_overrides
from .dispatch import collect_from_managers
from .execution import CLIError, highlight_cli_name
from .manager import PackageManager
from .package import Package, packages_asdict
from .platforms import MAIN_PLATFORMS
from .pool import pool
from .summary import package_counts, print_summary
from .tables import (
    INSTALLED_COLUMNS,
    MANAGERS_COLUMNS,
    OUTDATED_COLUMNS,
    SEARCH_COLUMNS,
    WHICH_COLUMNS,
    SortableField,
    column_specs,
    print_projected_table,
    print_serialized_and_exit,
)
from .version import diff_versions

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from click_extra import Context


@mpm.command(
    short_help="List every registered package manager and check its presence "
    "on the system.",
    section=EXPLORE,
)
@columns_option(columns=column_specs(MANAGERS_COLUMNS))
@pass_context
def managers(ctx):
    """List every package manager detected on the system.

    Only reports by default all managers supported on the current platform. To include
    unsupported and deprecated managers in the report, use the `--all-managers`
    flag.

    User's own selection configuration are intentionally ignored, so a manager dropped
    from regular operations is still visible here for troubleshooting. To narrow down the
    report to a subset of managers, pass the same selectors as for other subcommands (e.g.
    `--pip` or `--no-apt`).
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
        # The version probes feeding the table fire lazily at column-render time,
        # after selection: pass the global --timeout so the pool binds it to them,
        # or a wedged binary would hold each row at the read-only default cap.
        timeout=ctx.obj.timeout,
    )

    # Machine-friendly data rendering.
    table_format = ctx.meta[TABLE_FORMAT]
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
            manager_data[manager.id]["errors"] = _cli_errors(manager)

        print_serialized_and_exit(ctx, manager_data)

    # Human-friendly content rendering.
    table: list[dict[str, str | None]] = []
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

        table.append({
            "manager_id": getattr(theme(), "success" if manager.fresh else "error")(
                manager.id
            ),
            "manager_name": manager.name,
            "supported": os_infos,
            "cli": cli_infos,
            "executable": theme().success(OK_GLYPH) if manager.executable else "",
            "version": version_infos,
        })

    print_projected_table(ctx, MANAGERS_COLUMNS, table)


def _manager_result(
    manager: PackageManager, packages: tuple[dict, ...]
) -> tuple[str, dict]:
    """Build the standard `(id, payload)` result for a read-only manager query.

    The payload shape — `id`, `name`, `packages`, `errors` — is shared by
    the `installed`, `outdated` and `search` subcommands, their serialized
    output and their table rendering.
    """
    return manager.id, {
        "id": manager.id,
        "name": manager.name,
        "packages": packages,
        "errors": _cli_errors(manager),
    }


def _safe_packages(
    manager: PackageManager,
    source: Callable[[], Iterable[Package]],
    fields: tuple[str, ...],
    action: str,
) -> tuple[dict, ...]:
    """Materialize `source()` into package dicts, tolerating a CLI failure.

    On {class}`meta_package_manager.execution.CLIError` (the manager's query
    subprocess failed), log a one-line ``"Could not {action} from {manager}"``
    warning and return no packages, so one broken manager never aborts the batch.
    """
    try:
        return tuple(packages_asdict(source(), fields))
    except CLIError:
        logging.warning(f"Could not {action}.", extra={"label": manager.id})
        return ()


def _collect_manager_data(
    ctx: Context,
    operation: Operations,
    running: str,
    done: str,
    fetch: Callable[[PackageManager], tuple[str, dict]],
) -> dict[str, dict]:
    """Select the managers implementing `operation` and fan `fetch` out.

    The shared prelude of every read query (`installed`, `outdated`,
    `orphans`, `search`): resolve the selection, run `fetch` concurrently
    through {func}`meta_package_manager.dispatch.collect_from_managers` under
    the `running`/`done` spinner labels, and gather the per-manager payloads
    keyed by manager ID, in selection order.
    """
    managers = list(ctx.obj.selected_managers(implements_operation=operation))
    return {
        manager_id: data
        for manager_id, data in collect_from_managers(running, done, managers, fetch)
    }


def _inventory_rows(
    data: dict[str, dict],
    highlight_query: Callable[[str], str],
) -> list[dict[str, str | None]]:
    """Build the table rows of an inventory-shaped query result.

    The row shape of {data}`meta_package_manager.tables.INSTALLED_COLUMNS`:
    package ID and name (query matches highlighted), sourcing manager, and the
    installed version with a `?` placeholder when the manager reports none.
    Shared by `installed` and `orphans`, whose tables are identical.
    """
    return [
        {
            "package_id": highlight_query(info["id"]) if info["id"] else "",
            "package_name": highlight_query(info["name"]) if info["name"] else "",
            "manager_id": manager_id,
            "installed_version": str(info["installed_version"])
            if info["installed_version"]
            else "?",
        }
        for manager_id, payload in data.items()
        for info in payload["packages"]
    ]


def _query_highlighter(query: str | None) -> Callable[[str], str]:
    """Build a highlighter that emphasizes `query` matches in table cells.

    Returns a cached, case-insensitive callable that wraps each occurrence of the
    query (and its alphanumeric parts) in the active theme's `search` style, so
    the matched substring stands out in the rendered table. When no query was
    given, returns an identity function instead, leaving cells untouched. Shared by
    the `search`, `installed` and `outdated` renderers.
    """
    if not query:
        return lambda value: value
    patterns = {query}.union(Package.query_parts(query))
    highlighter: Callable[[str], str] = cached(LRI(max_size=1000))(
        partial(
            highlight,
            patterns=patterns,
            styling_func=theme().search,
            ignore_case=True,
        ),
    )
    return highlighter


# Options shared by several subcommands. Each application of a decorator below
# instantiates its own Option, so one definition can safely serve many commands.

exact_match_option = option(
    "--exact/--fuzzy",
    default=False,
    help="With a QUERY, only keep packages whose ID or name matches it exactly, "
    "instead of the default case-insensitive, tokenized (fuzzy) match. No effect "
    "without a QUERY.",
)
"""`--exact` refinement of the optional positional `QUERY` of `installed` and
`outdated`."""


@mpm.command(aliases=["list"], short_help="List installed packages.", section=EXPLORE)
@exact_match_option
@option(
    "-d",
    "--duplicates",
    is_flag=True,
    default=False,
    help="Only list installed packages sharing the same ID. Implies "
    "`--sort-by package_id` to make duplicates easier to compare between themselves.",
)
@columns_option(columns=column_specs(INSTALLED_COLUMNS))
@argument("query", type=STRING, required=False)
@pass_context
def installed(ctx, exact, duplicates, query):
    """List all packages installed on the system by each manager.

    With an optional `QUERY`, restrict the listing to installed packages whose ID
    or name matches it. The match is fuzzy by default (case-insensitive, tokenized);
    `--exact` requires a verbatim match on the package ID or name.
    """
    # Build-up a global dict of installed packages per manager.
    fields = (
        "id",
        "name",
        "installed_version",
    )

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        packages = tuple(
            packages_asdict(_snapshot_installed(manager, query, exact=exact), fields)
        )
        return _manager_result(manager, packages)

    installed_data = _collect_manager_data(
        ctx, Operations.installed, "Listing", "Listed", fetch
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
    print_serialized_and_exit(ctx, installed_data)

    # Human-friendly content rendering, highlighting the query matches (if any).
    table = _inventory_rows(installed_data, _query_highlighter(query))

    # Force sorting by package ID in duplicate mode.
    if duplicates:
        logging.info(
            "Force table sorting on package ID because of --duplicates option."
        )
        ctx.meta[SORT_BY] = (SortableField.PACKAGE_ID,)

    print_projected_table(ctx, INSTALLED_COLUMNS, table)

    if ctx.obj.summary:
        print_summary(package_counts(installed_data))


@mpm.command(short_help="List outdated packages.", section=EXPLORE)
@exact_match_option
@option(
    "--plugin-output",
    is_flag=True,
    default=False,
    help="Output results for direct consumption by an Xbar/SwiftBar-compatible plugin. "
    "The layout is dynamic and depends on environment variables set by either Xbar "
    "or SwiftBar.",
)
@columns_option(columns=column_specs(OUTDATED_COLUMNS))
@argument("query", type=STRING, required=False)
@pass_context
def outdated(ctx, exact, plugin_output, query):
    """List available package upgrades and their versions for each manager.

    With an optional `QUERY`, restrict the listing to outdated packages whose ID
    or name matches it. The match is fuzzy by default (case-insensitive, tokenized);
    `--exact` requires a verbatim match on the package ID or name.
    """
    # Build-up a global list of outdated packages per manager.
    fields = (
        "id",
        "name",
        "installed_version",
        "latest_version",
    )

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        packages = _safe_packages(
            manager,
            lambda: _filter_matches(manager.refiltered_outdated, query, exact=exact),
            fields,
            "list outdated packages",
        )
        return _manager_result(manager, packages)

    outdated_data = _collect_manager_data(
        ctx, Operations.outdated, "Checking", "Checked", fetch
    )

    # Machine-friendly data rendering.
    print_serialized_and_exit(ctx, outdated_data)

    # Xbar/SwiftBar-friendly plugin rendering.
    if plugin_output:
        BarPluginRenderer().print(outdated_data)
        ctx.exit()

    # Human-friendly content rendering, highlighting the query matches (if any).
    highlight_query = _query_highlighter(query)
    table: list[dict[str, str | None]] = []
    for manager_id, outdated_pkg in outdated_data.items():
        for info in outdated_pkg["packages"]:
            installed_version, latest_version = diff_versions(
                info["installed_version"] if info["installed_version"] else "?",
                info["latest_version"],
            )
            table.append({
                "package_id": highlight_query(info["id"]) if info["id"] else "",
                "package_name": highlight_query(info["name"]) if info["name"] else "",
                "manager_id": manager_id,
                "installed_version": installed_version,
                "latest_version": latest_version,
            })

    print_projected_table(ctx, OUTDATED_COLUMNS, table)

    if ctx.obj.summary:
        print_summary(package_counts(outdated_data))


@mpm.command(short_help="List orphaned packages.", section=EXPLORE)
@exact_match_option
@columns_option(columns=column_specs(INSTALLED_COLUMNS))
@argument("query", type=STRING, required=False)
@pass_context
def orphans(ctx, exact, query):
    """List packages installed as dependencies that no package requires anymore.

    Each manager reports its orphans through its own native read-only query
    (`pacman --query --deps --unrequired`, `brew autoremove --dry-run`,
    `dnf repoquery --unneeded`, ...): `mpm` builds no dependency graph of its
    own. Review the list here, then act on it with `mpm cleanup --orphans`.

    With an optional `QUERY`, restrict the listing to orphaned packages whose ID
    or name matches it. The match is fuzzy by default (case-insensitive, tokenized);
    `--exact` requires a verbatim match on the package ID or name.
    """
    # Build-up a global list of orphaned packages per manager.
    fields = (
        "id",
        "name",
        "installed_version",
    )

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        packages = _safe_packages(
            manager,
            lambda: _filter_matches(manager.orphans, query, exact=exact),
            fields,
            "list orphaned packages",
        )
        return _manager_result(manager, packages)

    orphans_data = _collect_manager_data(
        ctx, Operations.orphans, "Listing", "Listed", fetch
    )

    # Machine-friendly data rendering.
    print_serialized_and_exit(ctx, orphans_data)

    # Human-friendly content rendering, highlighting the query matches (if any).
    table = _inventory_rows(orphans_data, _query_highlighter(query))
    print_projected_table(ctx, INSTALLED_COLUMNS, table)

    if ctx.obj.summary:
        print_summary(package_counts(orphans_data))


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
    help="Only keep packages whose ID or name matches the query exactly, "
    "instead of the default case-insensitive, tokenized (fuzzy) match.",
)
@option(
    "--refilter/--no-refilter",
    default=True,
    help="Let mpm refilters managers' search results.",
)
@columns_option(columns=column_specs(SEARCH_COLUMNS))
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
    fields = (
        "id",
        "name",
        "latest_version",
        "description",
    )

    search_method = "refiltered_search" if refilter else "search"

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        packages = _safe_packages(
            manager,
            lambda: getattr(manager, search_method)(query, extended, exact),
            fields,
            "search packages",
        )
        return _manager_result(manager, packages)

    matches = _collect_manager_data(
        ctx, Operations.search, "Searching", "Searched", fetch
    )

    # Machine-friendly data rendering.
    print_serialized_and_exit(ctx, matches)

    # Human-friendly content rendering, highlighting the query matches. The
    # description cell is always populated so an explicit --columns selection can
    # surface it; the default selection below hides it unless --description.
    highlight_query = _query_highlighter(query)
    table: list[dict[str, str | None]] = []
    for manager_id, matching_pkg in matches.items():
        for pkg in matching_pkg["packages"]:
            table.append({
                "package_id": highlight_query(pkg["id"]) if pkg["id"] else "",
                "package_name": highlight_query(pkg["name"]) if pkg["name"] else "",
                "manager_id": manager_id,
                "latest_version": str(pkg["latest_version"])
                if pkg["latest_version"]
                else "?",
                "description": highlight_query(pkg.get("description"))
                if pkg.get("description")
                else "",
            })

    default_ids = tuple(
        spec.id
        for spec in column_specs(SEARCH_COLUMNS)
        if show_description or spec.id != "description"
    )
    print_projected_table(ctx, SEARCH_COLUMNS, table, default_ids=default_ids)

    if ctx.obj.summary:
        print_summary(package_counts(matches))


@mpm.command(aliases=["locate"], short_help="Locate CLIs on system.", section=EXPLORE)
@columns_option(columns=column_specs(WHICH_COLUMNS))
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
    # Machine-friendly data rendering.
    table_format = ctx.meta[TABLE_FORMAT]
    if table_format in SERIALIZATION_FORMATS:
        cli_data = [
            {
                "manager_id": manager.id,
                "cli_paths": list(manager.search_all_cli(cli_names)),
            }
            for manager in ctx.obj.selected_managers()
        ]
        print_serialized_and_exit(ctx, cli_data)

    # Print table.
    table: list[dict[str, str | None]] = []
    for manager in ctx.obj.selected_managers():
        for priority, found_cli in enumerate(manager.search_all_cli(cli_names)):
            # Resolve symlinks and highlight the CLI name.
            symlink = ""
            if found_cli.is_symlink():
                # resolve() always returns a Path, so highlight_cli_name won't return None.
                resolved = highlight_cli_name(found_cli.resolve(), cli_names)
                assert resolved is not None
                symlink = f"→ {resolved}"
            table.append({
                "manager_id": manager.id,
                "priority": str(priority),
                "cli_path": highlight_cli_name(found_cli, cli_names),
                "symlink": symlink,
            })
    print_projected_table(ctx, WHICH_COLUMNS, table)


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

    Each block is a valid `[mpm.managers.<id>]` section ready to paste into a
    standalone config file or a `[tool.mpm]` `pyproject.toml` block. The output
    lists every overridable field with its current value so it doubles as the
    canonical reference for what each manager exposes: prune the rows that don't
    apply and customize the rest.

    With no positional arguments, every maintained (non-deprecated) manager is
    dumped. Pass one or more manager IDs to restrict the output.
    """
    target_ids = manager_ids or pool.maintained_manager_ids
    overrides = {mid: dump_manager_overrides(pool[mid]) for mid in target_ids}
    echo(tomli_w.dumps({"mpm": {"managers": overrides}}), nl=False)
