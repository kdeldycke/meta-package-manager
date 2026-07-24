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
"""The package snapshots subcommands: manifest export and replay.

`dump` (TOML manifest or Brewfile) and `restore` (install back the
packages a TOML manifest references, through the shared per-package action
engine).

The `mpm` group itself, and the plumbing shared with the other subcommand
modules, live in {mod}`meta_package_manager.cli`.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path

import tomli_w
from click_extra import File, argument, echo, file_path, option, pass_context
from click_extra.theme import get_current_theme as theme
from extra_platforms import current_platform

from . import __version__
from .brewfile import build_brewfile
from .capabilities import Operations
from .cli import (
    SNAPSHOTS,
    _cli_errors,
    _install_action,
    _package_task,
    _snapshot_installed,
    exit_on_failures,
    guard_existing_output,
    is_stdout,
    mpm,
    overwrite_option,
    package_label,
    prep_path,
    query_exact_option,
    query_option,
)
from .dispatch import collect_from_managers, collect_per_package
from .package import packages_asdict
from .pool import pool
from .specifier import VERSION_SEP, Specifier
from .sudo import prime_sudo
from .summary import print_summary

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

    from .manager import PackageManager


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
@overwrite_option
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
@query_option
@query_exact_option
@argument(
    "output_path",
    type=file_path(writable=True, resolve_path=True, allow_dash=True),
    default="-",
)
@pass_context
def dump(
    ctx,
    output_format,
    overwrite,
    include_header,
    merge,
    update_version,
    query,
    exact,
    output_path,
):
    """Dump installed packages to a TOML manifest or a Brewfile.

    By default emits TOML, one section per manager (one entry per package, keyed
    by package ID, with the installed version as the value). Pass `--brewfile`
    to emit a Brewfile compatible with `brew bundle install`.

    With no [OUTPUT_PATH] argument, writes to stdout. TOML files are readable by
    `mpm restore`.

    With `--query`, restrict the snapshot to installed packages whose ID or name
    matches it (fuzzy by default, verbatim with `--exact`).

    `--merge` and `--update-version` operate on an existing TOML file; both
    require the [OUTPUT_PATH] argument and neither is valid with `--brewfile`.
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
                logging.info("Ignore the --overwrite/--force/--replace option.")
            logging.info(f"Print Brewfile to {sys.stdout.name}")
        else:
            logging.info(f"Dump installed packages as a Brewfile into {output_path}")
            guard_existing_output(ctx, output_path, overwrite=overwrite)
        _dump_brewfile(
            ctx, output_path, include_header=include_header, query=query, exact=exact
        )
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
            logging.info("Ignore the --overwrite/--force/--replace option.")
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
            if merge or update_version:
                # Both modes edit the file in place and clobber nothing, so an
                # --overwrite flag is inert and disclosed as such.
                if overwrite:
                    logging.info("Ignore the --overwrite/--force/--replace option.")
            else:
                guard_existing_output(ctx, output_path, overwrite=overwrite)
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
        query=query,
        exact=exact,
    )


def _dump_toml(
    ctx,
    output_path,
    *,
    include_header: bool,
    merge: bool = False,
    update_version: bool = False,
    query: str | None = None,
    exact: bool = False,
) -> None:
    """Render the installed inventory as a TOML manifest.

    Supports the same three modes the historical `mpm backup` exposed: a
    one-shot dump, `--merge` (add new entries to an existing file), and
    `--update-version` (refresh the version of entries already in the file).
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
            f"# Generated by mpm {__version__}.\n"
            f"# Timestamp: {datetime.now(tz=timezone.utc).isoformat()}.\n\n"
        )

    managers = list(
        ctx.obj.selected_managers(implements_operation=Operations.installed)
    )

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        logging.info("Dumping packages...", extra={"label": manager.id})
        packages = tuple(
            packages_asdict(_snapshot_installed(manager, query, exact=exact), fields)
        )
        return manager.id, {
            "packages": packages,
            "errors": _cli_errors(manager),
        }

    # Query each manager's installed packages concurrently, then assemble the
    # manifest in manager order (see collect_from_managers).
    for manager_id, data in collect_from_managers("Dumping", "Dumped", managers, fetch):
        for pkg in data["packages"]:
            if update_version:
                if pkg["id"] in installed_data.get(manager_id, {}):
                    installed_data[manager_id][pkg["id"]] = str(
                        pkg["installed_version"],
                    )
            else:
                installed_data.setdefault(manager_id, {})[pkg["id"]] = str(
                    pkg["installed_version"],
                )
        if installed_data.get(manager_id):
            installed_data[manager_id] = dict(
                sorted(
                    installed_data[manager_id].items(),
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


def _dump_brewfile(
    ctx,
    output_path,
    *,
    include_header: bool,
    query: str | None = None,
    exact: bool = False,
) -> None:
    """Render the installed inventory as a Brewfile.

    Filters selected managers down to those with a configured
    {attr}`PackageManager.brewfile_entry_type`. Counts packages from skipped
    managers so the header can show what was dropped, and emits a stderr
    warning for any skipped manager that defines {attr}`brewfile_skip_warning`
    (used by `vscodium` to flag the silent-misinstall risk).
    """
    managers = list(
        ctx.obj.selected_managers(implements_operation=Operations.installed)
    )

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        return manager.id, {
            "packages": _snapshot_installed(manager, query, exact=exact),
            "errors": _cli_errors(manager),
        }

    # Query each manager's installed packages concurrently, then build the Brewfile
    # from the gathered data (see collect_from_managers).
    results = collect_from_managers("Reading", "Read", managers, fetch)
    packages_by_manager = {mid: data["packages"] for mid, data in results}
    errored = {mid for mid, data in results if data["errors"]}

    mappable_managers = []
    skipped_counts: Counter[str] = Counter()
    for manager in managers:
        if manager.brewfile_entry_type is None:
            # Drop managers whose CLI failed (installed_or_empty already warned),
            # so they stay out of the header tally as before.
            if manager.id in errored:
                continue
            installed_count = len(packages_by_manager.get(manager.id, ()))
            skipped_counts[manager.id] = installed_count
            if installed_count and manager.brewfile_skip_warning:
                logging.warning(
                    manager.brewfile_skip_warning.format(count=installed_count),
                )
            continue
        mappable_managers.append(manager)

    content = build_brewfile(
        mappable_managers,
        packages_by_manager=packages_by_manager,
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
    # The sections are independent (each ties its packages to one manager), so restore
    # fans out across managers (see collect_per_package). The one ordering need is a
    # not-yet-built feature: install cask's mas binary before the [mas] section runs
    # (use-case: dotfiles). When it lands it must become parallel-within-dependency-
    # levels rather than this flat fan-out.

    # Cast generator to tuple because of reuse across TOML files and the trail.
    selected_managers = tuple(
        ctx.obj.selected_managers(implements_operation=Operations.install),
    )
    prime_sudo(ctx, selected_managers)

    # Collect every package a manager failed to install, to raise a non-zero exit code
    # at the end (matching install, remove and upgrade).
    restore_failures: list[str] = []
    failures_lock = threading.Lock()

    # Gather one task per referenced (package, manager) across all the input files.
    tasks: list[tuple[PackageManager, Callable[[], tuple[bool, str]]]] = []
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

        for manager in selected_managers:
            if manager.id not in doc:
                logging.info(
                    f"No [{theme().invoked_command(manager.id)}] section found.",
                )
                continue
            logging.info("Restore packages...", extra={"label": manager.id})
            for package_id, version in doc[manager.id].items():
                spec = Specifier(
                    raw_spec=f"pkg:{manager.id}/{package_id}{VERSION_SEP}{version}",
                    package_id=package_id,
                    manager_id=manager.id,
                    version=str(version),
                )
                tasks.append((
                    manager,
                    _package_task(
                        manager,
                        spec,
                        failures_lock,
                        action=_install_action,
                        verb="install",
                        past="installed",
                        prep="with",
                        operation=Operations.install.name,
                        record_failure=lambda s: restore_failures.append(
                            package_label(s)
                        ),
                    ),
                ))

    collect_per_package("Restoring", "Restored", tasks)

    # Fail with a non-zero exit code if any referenced package could not be installed.
    exit_on_failures(ctx, "restore", restore_failures)
