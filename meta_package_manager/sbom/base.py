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
"""Format-agnostic SBOM base class and export-format enum.

Kept deliberately free of SPDX or CycloneDX dependencies: instantiating
:py:class:`SBOM` directly is meaningless, but importing the symbols here
is safe even when the optional ``[sbom]`` extra is not installed.
"""

from __future__ import annotations

import logging
import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path


class ExportFormat(StrEnum):
    """A user-friendly version of ``spdx_tools.spdx.formats.FileFormat``.

    Map format to user-friendly IDs.
    """

    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    TAG_VALUE = "tag"
    RDF_XML = "rdf"


class SBOM:
    """Utilities shared by all SBOM classes."""

    bundled_scan: bool = True
    """Whether the scan was a ``--bundled`` enrichment pass.

    Set by :py:meth:`set_scan_completeness` from the CLI. ``True`` means
    the metadata extractors ran and upstream per-package SBOMs were
    merged (the default). ``False`` is the ``--minimal`` mode: bare
    inventory only, no extractor calls. Subclasses use this flag to
    populate completeness markers in their respective standards
    (``incomplete`` vs ``complete`` in CycloneDX, ``EXTRACTED`` license
    handling in SPDX).
    """

    def __init__(
        self,
        export_format: ExportFormat = ExportFormat.JSON,  # type: ignore[assignment]
    ) -> None:
        """Defaults to JSON export format."""
        logging.debug(f"Set export format to {export_format}")
        self.export_format = export_format
        # ``manager_id -> count`` of unique packages the renderer admitted
        # into the document. Populated by :py:meth:`_track_addition` so
        # subclasses' format-specific dedup is reflected here.
        self.packages_per_manager: dict[str, int] = {}
        # ``manager_id -> count`` of admitted packages whose metadata was
        # non-empty (i.e. the manager's extractor produced something).
        self.enriched_per_manager: dict[str, int] = {}
        # Keys used to dedup ``_track_addition`` calls across subclasses
        # that may invoke it more than once per (manager, package) pair.
        self._tracked_additions: set[tuple[str, str]] = set()

    def _track_addition(
        self,
        manager_id: str,
        package_id: str,
        metadata,
    ) -> None:
        """Record that one package entered the document.

        Called by :py:meth:`add_package` subclass implementations after
        their own dedup check so the renderer-level counters reflect
        what actually got serialized, not the number of inbound calls.
        Idempotent on ``(manager_id, package_id)`` to stay robust against
        future refactors that might double-call.
        """
        key = (manager_id, package_id)
        if key in self._tracked_additions:
            return
        self._tracked_additions.add(key)
        self.packages_per_manager[manager_id] = (
            self.packages_per_manager.get(manager_id, 0) + 1
        )
        if metadata is not None and not metadata.is_empty():
            self.enriched_per_manager[manager_id] = (
                self.enriched_per_manager.get(manager_id, 0) + 1
            )

    def stats(self) -> dict[str, object]:
        """Return a summary of what landed in the document.

        Format-agnostic counters live in the base implementation; SPDX and
        CycloneDX subclasses extend the returned dict with their own
        merged-documents, dependency-graph, and any other format-specific
        counts. Surfaced by the CLI as a post-run INFO-level summary and
        usable by tests or programmatic consumers without re-parsing the
        rendered document.
        """
        return {
            "packages_total": sum(self.packages_per_manager.values()),
            "packages_per_manager": dict(self.packages_per_manager),
            "enriched_per_manager": dict(self.enriched_per_manager),
        }

    def set_scan_completeness(self, bundled: bool) -> None:
        """Record whether the run was a bundled enrichment pass.

        Called once by the CLI right after ``init_doc()`` and before
        the first ``add_package()``. The information flows into
        per-format completeness markers in the rendered document.
        """
        self.bundled_scan = bundled

    def finalize(self) -> None:
        """Resolve any deferred state before ``export()``.

        Some constructs cannot be emitted at ``add_package()`` time
        because they reference packages that may not have been added yet:
        a Homebrew formula's runtime dependency on another formula listed
        later in the scan, for example. Subclasses queue those during
        ``add_package`` and flush them here. The base implementation is a
        no-op so subclasses can rely on it being called exactly once.
        """

    @staticmethod
    def autodetect_export_format(file_path: Path) -> ExportFormat | None:
        """Better version of ``spdx_tools.spdx.formats.file_name_to_format`` which is
        based on ``Path`` objects and is case-insensitive.

        .. todo:
            Contribute generic autodetection method to Click Extra?
        """
        suffixes = tuple(s.lower() for s in file_path.suffixes[-2:])
        export_format = None
        if suffixes:
            if suffixes == (".rdf", ".xml") or suffixes[-1] == ".rdf":
                export_format = ExportFormat.RDF_XML
            elif suffixes[-1] == ".json":
                export_format = ExportFormat.JSON
            elif suffixes[-1] == ".xml":
                export_format = ExportFormat.XML
            elif suffixes[-1] in (".yaml", ".yml"):
                export_format = ExportFormat.YAML
            elif suffixes[-1] in (".tag", ".spdx"):
                export_format = ExportFormat.TAG_VALUE
        logging.debug(f"File suffixes {suffixes} resolves to {export_format}.")
        return export_format  # type: ignore[return-value]
