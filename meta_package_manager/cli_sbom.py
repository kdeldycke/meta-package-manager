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
"""The SBOM subcommand: export the package inventory as a standard document.

`sbom` renders the installed inventory as a SPDX or CycloneDX file, with
optional metadata enrichment and an opt-in OSV vulnerability scan.

The `mpm` group itself, and the plumbing shared with the other subcommand
modules, live in {mod}`meta_package_manager.cli`.
"""

from __future__ import annotations

import logging
import sys

from click_extra import (
    EnumChoice,
    UsageError,
    argument,
    echo,
    file_path,
    option,
    pass_context,
)

from .capabilities import Operations
from .cli import (
    SBOM_SECTION,
    _cli_errors,
    _snapshot_installed,
    guard_existing_output,
    is_stdout,
    mpm,
    overwrite_option,
    prep_path,
    query_exact_option,
    query_option,
)
from .dispatch import collect_from_managers
from .sbom.base import SBOM, ExportFormat
from .sbom.cyclonedx import CycloneDX, cyclonedx_support
from .sbom.spdx import SPDX, spdx_support
from .summary import print_summary, sbom_summary

TYPE_CHECKING = False
if TYPE_CHECKING:
    from .manager import PackageManager


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
@overwrite_option
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
@query_option
@query_exact_option
@argument(
    "export_path",
    type=file_path(writable=True, resolve_path=True, allow_dash=True),
    default="-",
)
@pass_context
def sbom(ctx, spdx, export_format, overwrite, bundled, query, exact, export_path):
    """Export list of installed packages to a SPDX or CycloneDX file.

    With `--query`, restrict the export to installed packages whose ID or name
    matches it (fuzzy by default, verbatim with `--exact`).
    """
    standard = "SPDX" if spdx else "CycloneDX"

    if is_stdout(export_path):
        if overwrite:
            logging.info("Ignore the --overwrite/--force/--replace option.")
        logging.info(f"Print {standard} export to {sys.stdout.name}")

    else:
        logging.info(f"Export installed packages in {standard} to {export_path}")
        guard_existing_output(ctx, export_path, overwrite=overwrite)

    # <stdout> format defaults to JSON.
    if is_stdout(export_path):
        if not export_format:
            export_format = ExportFormat.JSON
    # If no export format has been provided, guess it from file name.
    else:
        guessed_format = SBOM.autodetect_export_format(export_path)
        if not export_format:
            if not guessed_format:
                # On Python 3.10, `ExportFormat` extends `backports.strenum.StrEnum`
                # whose typeshed stub omits `__iter__`; iteration is provided by the
                # `EnumMeta` metaclass at runtime.
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
                "SPDX SBOM generation requires the [sbom-offline] extra. "
                "Install with: pip install meta-package-manager[sbom-offline]",
            )
        sbom_class = SPDX
    else:
        if not cyclonedx_support:
            raise UsageError(
                "CycloneDX SBOM generation requires the [sbom-offline] extra. "
                "Install with: pip install meta-package-manager[sbom-offline]",
            )
        if export_format not in (ExportFormat.JSON, ExportFormat.XML):
            logging.critical(f"{standard} does not support {export_format} format.")
            ctx.exit(2)
        sbom_class = CycloneDX

    sbom = sbom_class(export_format)
    sbom.init_doc()

    managers = list(
        ctx.obj.selected_managers(implements_operation=Operations.installed)
    )
    by_id = {manager.id: manager for manager in managers}

    def fetch(manager: PackageManager) -> tuple[str, dict]:
        logging.info("Export packages...", extra={"label": manager.id})
        installed_packages = _snapshot_installed(manager, query, exact=exact)
        # In --bundled mode, enrich each package with its metadata here too, so the
        # slow per-manager metadata fetch parallelizes alongside the listing.
        enriched = None
        if bundled and installed_packages:
            try:
                enriched = list(manager.package_metadata_batch(installed_packages))
            except Exception as exc:  # noqa: BLE001
                logging.info(
                    f"Falling back to minimal SBOM data: {exc}",
                    extra={"label": manager.id},
                )
        return manager.id, {
            "packages": installed_packages,
            "enriched": enriched,
            "errors": _cli_errors(manager),
        }

    # Query (and, for --bundled, enrich) each manager concurrently, then add the
    # packages to the document in manager order (see collect_from_managers).
    for manager_id, data in collect_from_managers(
        "Exporting", "Exported", managers, fetch
    ):
        installed_packages = data["packages"]
        if not installed_packages:
            continue
        manager = by_id[manager_id]
        if data["enriched"] is not None:
            for package, metadata in data["enriched"]:
                sbom.add_package(manager, package, metadata)
        else:
            for package in installed_packages:
                sbom.add_package(manager, package)

    if ctx.obj.network:
        _scan_and_attach_vulnerabilities(sbom)

    sbom.finalize()
    if ctx.obj.summary:
        print_summary(*sbom_summary(sbom, bundled))
    echo(sbom.export(), file=prep_path(export_path))


def _scan_and_attach_vulnerabilities(sbom: SBOM) -> None:
    """Query OSV for the SBOM's packages and attach the results.

    Runs only in `--network` mode. Failures degrade gracefully: a
    missing `[sbom-online]` extra or any network error logs a warning
    and leaves the document without vulnerability data rather than
    aborting the export. The heavy network imports are deferred to here
    so the offline path never pays for them.
    """
    from .sbom._network import NetworkClient, NetworkError, network_support
    from .sbom.vulnerabilities import scan_vulnerabilities

    if not network_support:
        logging.warning(
            "Vulnerability scan skipped: the --network option needs the "
            "[sbom-online] extra. Install with: "
            "pip install meta-package-manager[sbom-online]",
        )
        return

    try:
        with NetworkClient() as client:
            vulnerabilities = scan_vulnerabilities(sbom.all_purls(), client)
    except NetworkError as exc:
        logging.warning(
            f"Vulnerability scan failed ({exc}); the SBOM will not include "
            "vulnerability data. Re-run later or drop --network to silence.",
        )
        return

    sbom.attach_vulnerabilities(vulnerabilities)
