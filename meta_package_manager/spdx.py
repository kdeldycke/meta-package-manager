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

import logging
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import IO

from boltons.ecoutils import get_profile
from click_extra.platforms import CURRENT_OS_LABEL
from spdx_tools.spdx.model import (
    Actor,
    ActorType,
    CreationInfo,
    Document,
    Package,
    PackagePurpose,
    Relationship,
    RelationshipType,
)
from spdx_tools.spdx.model import (
    Package as SPDXPackage,
)
from spdx_tools.spdx.writer.json import json_writer
from spdx_tools.spdx.writer.rdf import rdf_writer
from spdx_tools.spdx.writer.tagvalue import tagvalue_writer
from spdx_tools.spdx.writer.xml import xml_writer
from spdx_tools.spdx.writer.yaml import yaml_writer

from meta_package_manager.base import Package, PackageManager

from . import __version__


class ExportFormat(Enum):
    """A user-friendly version of ``spdx_tools.spdx.formats.FileFormat``."""

    JSON = "json"
    YAML = "yaml"
    XML = "xml"
    TAG_VALUE = "tag"
    RDF_XML = "rdf"
    """Map format to user-friendly IDs."""

    @classmethod
    def from_value(cls, format_id: str | None = None) -> ExportFormat | None:
        if not format_id:
            return None
        matches = tuple(e for e in cls if e.value == format_id)
        assert len(matches) == 1
        return matches[0]

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Returns a ``tuple`` with user-friendly format IDs."""
        return tuple(i.value for i in cls)


DOC_ID = "SPDXRef-DOCUMENT"


def normalize_spdx_id(str: str) -> str:
    """SPDX IDs must only contain letters, numbers, ``.`` and ``-``."""
    return "-".join((s for s in re.split(r"[^a-zA-Z0-9\.]", str) if s))


class SPDX:
    document: Document | None = None

    def __init__(self, export_format: ExportFormat = ExportFormat.JSON) -> None:
        """Defaults to JSON export format."""
        self.export_format = export_format

    @classmethod
    def autodetect_export_format(self, file_path: Path) -> ExportFormat | None:
        """Better version of ``spdx_tools.spdx.formats.file_name_to_format`` which is
        based on ``Path`` objects and is case-insensitive.
        """
        suffixes = tuple(s.lower() for s in file_path.suffixes[-2:])
        export_format = None
        if suffixes == (".rdf", ".xml") or suffixes[-1] == ".rdf":
            export_format = ExportFormat.RDF_XML
        elif suffixes[-1] in (".tag", ".spdx"):
            export_format = ExportFormat.TAG_VALUE
        elif suffixes[-1] == ".json":
            export_format = ExportFormat.JSON
        elif suffixes[-1] == ".xml":
            export_format = ExportFormat.XML
        elif suffixes[-1] in (".yaml", ".yml"):
            export_format = ExportFormat.YAML
        logging.debug(f"File suffixes {suffixes} resolves to {export_format}.")
        return export_format

    def export(self, stream: IO):
        """Similar to ``spdx_tools.spdx.writer.write_anything.write_file`` but write
        directly to provided stream instead of file path.
        """
        writer = None
        if self.export_format == ExportFormat.JSON:
            writer = json_writer.write_document_to_stream
        elif self.export_format == ExportFormat.YAML:
            writer = yaml_writer.write_document_to_stream
        elif self.export_format == ExportFormat.XML:
            writer = xml_writer.write_document_to_stream
        elif self.export_format == ExportFormat.TAG_VALUE:
            writer = tagvalue_writer.write_document_to_stream
        elif self.export_format == ExportFormat.RDF_XML:
            writer = rdf_writer.write_document_to_stream

        if writer:
            logging.debug(f"Export with {writer.__module__}.{writer.__name__}")
            writer(self.document, stream)

    def init_doc(self) -> None:
        profile = get_profile()
        system_id = normalize_spdx_id(
            "-".join((
                CURRENT_OS_LABEL,
                profile["linux_dist_name"],
                profile["linux_dist_version"],
                profile["uname"]["system"],
                profile["uname"]["release"],
                profile["uname"]["machine"],
            ))
        )

        creation_info = CreationInfo(
            spdx_version="SPDX-2.3",
            spdx_id=DOC_ID,
            # Because mpm is a system-wide tool, we choosed to name the document after
            # the host operating system platform it was run on.
            name=system_id,
            # Point directly to the mpm release on GitHub so we can get some additional
            # meaning from an URI that is not supposed to have any meaning. We add a
            # trailing "/<random_unique_id>" to the URI as the namespace is supposed to
            # be unique for each document. See:
            # https://spdx.github.io/spdx-spec/v2.3/document-creation-information/#65-spdx-document-namespace-field
            document_namespace=(
                "https://github.com/kdeldycke/meta-package-manager/releases/tag/"
                f"v{__version__}/{profile['guid']}"
            ),
            creators=[Actor(ActorType.TOOL, f"meta-package-manager-{__version__}")],
            created=datetime.now(),
            data_license="CC0-1.0",
        )

        self.document = Document(creation_info)
        self.document.packages = []
        self.document.relationships = []

    def add_package(self, manager: PackageManager, package: Package) -> None:
        package_docid = normalize_spdx_id(
            f"SPDXRef-Package-{package.manager_id}-{package.id}"
        )
        self.document.packages += [
            SPDXPackage(
                name=package.id,
                spdx_id=package_docid,
                version=str(package.installed_version),
                supplier=Actor(ActorType.ORGANIZATION, manager.name),
                # TODO: Use real URL.
                download_location="https://www.example.com",
                # Current SPDX export is only compiling metadata about packages and their
                # dependencies. So we do not analyze files, as specified in:
                # https://spdx.github.io/spdx-spec/v2.3/package-information/#782-intent
                files_analyzed=False,
                summary=package.name,
                description=package.description,
                primary_package_purpose=PackagePurpose.INSTALL,
            )
        ]

        # A DESCRIBES relationship asserts that the document indeed describes the package.
        self.document.relationships += [
            Relationship(DOC_ID, RelationshipType.DESCRIBES, package_docid)
        ]
