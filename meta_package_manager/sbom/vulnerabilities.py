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
"""Vulnerability lookup against `OSV.dev <https://osv.dev>`_.

The :py:func:`scan_vulnerabilities` entry point takes the set of purls a
rendered SBOM holds and returns the advisories affecting each, normalized
into the source-agnostic :py:class:`Vulnerability` dataclass. The SBOM
renderers consume that mapping in their ``finalize`` step (CycloneDX into
``Bom.vulnerabilities``, SPDX into per-package security ``externalRefs``).

OSV is the single source for this first iteration because it indexes by
ecosystem coordinates directly, sidestepping the fuzzy package-name to
CPE matching that NVD would require. Coverage is strongest for language
ecosystems (PyPI, npm, crates.io, RubyGems, Packagist); system package
managers like Homebrew are not in OSV, so their packages come back with
no advisories rather than an error.

Two-stage protocol:

1. A batched ``POST /v1/querybatch`` maps each queried coordinate to a
   list of advisory IDs (the batch response carries IDs only).
2. A per-ID ``GET /v1/vulns/{id}`` fetches the full record. These
   records are immutable once published, so they cache effectively
   forever; the batch listings get a finite TTL since new advisories
   can appear.

Network transport, retries, and caching are handled by
:py:class:`meta_package_manager.sbom._network.NetworkClient`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from packageurl import PackageURL

from ._network import NetworkError

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable

    from ._network import NetworkClient


OSV_BASE_URL = "https://api.osv.dev"
"""Base URL of the OSV.dev REST API."""

OSV_BATCH_ENDPOINT = f"{OSV_BASE_URL}/v1/querybatch"
OSV_VULN_ENDPOINT = f"{OSV_BASE_URL}/v1/vulns"

OSV_BATCH_LIMIT = 1000
"""Maximum number of queries OSV accepts in a single ``querybatch`` call."""

VULN_DETAIL_TTL = 30 * 86400
"""Cache TTL for per-advisory detail records (30 days).

OSV advisory records are effectively immutable once published (the
``modified`` field changes rarely), so a long TTL avoids re-fetching the
same record on every scan while still picking up the occasional
correction within a month.
"""

OSV_ECOSYSTEMS: dict[str, str] = {
    # mpm manager id (used as the purl type) -> OSV ecosystem name.
    # Only the managers OSV actually indexes are listed; a purl whose
    # type is absent here is skipped (its package gets no advisories
    # rather than a bogus query). System package managers (brew, cask,
    # macports, mas, ...) are intentionally absent: OSV does not index
    # them, and the distro ecosystems it does index (Debian, Alpine)
    # need a release qualifier mpm does not track.
    "cargo": "crates.io",
    "composer": "Packagist",
    "gem": "RubyGems",
    "npm": "npm",
    "pip": "PyPI",
    "pipx": "PyPI",
    "yarn": "npm",
}
"""Maps mpm manager ids to `OSV ecosystem names
<https://ossf.github.io/osv-schema/#defined-ecosystems>`_."""


@dataclass(frozen=True)
class Vulnerability:
    """Normalized vulnerability record, source-agnostic on its surface.

    Populated from OSV today; the shape deliberately avoids OSV-specific
    fields so a future NVD or GHSA source can fill the same structure.
    """

    id: str
    """Primary advisory identifier (``GHSA-…``, ``CVE-…``, ``OSV-…``)."""

    source: str = "OSV"
    """Origin database. Only ``OSV`` is produced today."""

    summary: str | None = None
    description: str | None = None
    severity: str | None = None
    """Coarse label: ``low`` / ``medium`` / ``high`` / ``critical``, or
    ``None`` when the source provides no rating."""

    cvss_vector: str | None = None
    """Raw CVSS vector string when present (e.g. ``CVSS:3.1/AV:N/...``).

    The numeric base score is intentionally not computed here: deriving
    it requires the full CVSS formula, which is out of scope for this
    first iteration. Consumers that need the number can parse the vector.
    """

    cwe_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    """Cross-references, like the CVE id behind a GHSA advisory."""

    references: tuple[str, ...] = ()
    fixed_versions: tuple[str, ...] = ()
    published_date: datetime | None = None
    modified_date: datetime | None = None

    advisory_url: str = ""
    """Canonical human-facing URL for the advisory."""


@dataclass
class _OSVQuery:
    """One coordinate to look up, paired with the purls it answers for.

    A single ecosystem coordinate (like ``PyPI / django / 1.0.0``) can be
    referenced by more than one purl string when the inventory lists the
    same package twice, so the mapping back to purls is a list.
    """

    ecosystem: str
    name: str
    version: str
    purls: list[str] = field(default_factory=list)

    def as_osv_payload(self) -> dict:
        """Render the OSV ``query`` object for this coordinate."""
        return {
            "package": {"ecosystem": self.ecosystem, "name": self.name},
            "version": self.version,
        }


def _coordinate_key(ecosystem: str, name: str, version: str) -> str:
    """Stable dict key for deduplicating identical coordinates."""
    return f"{ecosystem}\n{name}\n{version}"


def _parse_purls(purls: Iterable[str]) -> dict[str, _OSVQuery]:
    """Turn purl strings into deduplicated OSV queries.

    Purls whose type has no OSV ecosystem mapping, or that lack a
    version, are skipped (logged at debug). Identical coordinates from
    multiple purls collapse into one query that remembers every purl it
    covers, so the batch stays minimal and the results fan back out to
    every referencing purl.
    """
    queries: dict[str, _OSVQuery] = {}
    for purl_str in purls:
        try:
            purl = PackageURL.from_string(purl_str)
        except ValueError:
            logging.debug(f"Skipping unparseable purl: {purl_str!r}")
            continue
        ecosystem = OSV_ECOSYSTEMS.get(purl.type or "")
        if not ecosystem:
            logging.debug(
                f"Skipping purl with no OSV ecosystem mapping: {purl_str!r}",
            )
            continue
        if not purl.version:
            logging.debug(f"Skipping versionless purl: {purl_str!r}")
            continue
        # OSV keys names case-sensitively per ecosystem; the purl name is
        # already normalized by the manager that produced it.
        name = purl.name
        key = _coordinate_key(ecosystem, name, purl.version)
        query = queries.get(key)
        if query is None:
            query = _OSVQuery(
                ecosystem=ecosystem, name=name, version=purl.version
            )
            queries[key] = query
        query.purls.append(purl_str)
    return queries


def _chunked(items: list, size: int):
    """Yield successive ``size``-length slices of ``items``."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _batch_query(
    queries: list[_OSVQuery],
    client: NetworkClient,
) -> dict[int, list[str]]:
    """Run OSV ``querybatch`` over the coordinates, in chunks.

    Returns a mapping from each query's index (into ``queries``) to the
    list of advisory IDs OSV reported for it. OSV preserves query order
    within each batch response, which is how results map back to inputs.
    """
    ids_by_index: dict[int, list[str]] = {}
    for chunk_start, chunk in _enumerate_chunks(queries):
        payload = {"queries": [q.as_osv_payload() for q in chunk]}
        response = client.post(OSV_BATCH_ENDPOINT, payload)
        results = (response or {}).get("results", []) if isinstance(response, dict) else []
        for offset, result in enumerate(results):
            vuln_ids = [
                v["id"]
                for v in (result or {}).get("vulns", []) or []
                if v.get("id")
            ]
            if vuln_ids:
                ids_by_index[chunk_start + offset] = vuln_ids
    return ids_by_index


def _enumerate_chunks(queries: list[_OSVQuery]):
    """Yield ``(absolute_start_index, chunk)`` for each OSV batch slice."""
    index = 0
    for chunk in _chunked(queries, OSV_BATCH_LIMIT):
        yield index, chunk
        index += len(chunk)


def _fetch_detail(vuln_id: str, client: NetworkClient) -> Vulnerability | None:
    """Fetch and normalize one advisory by its OSV id.

    Returns ``None`` (with a debug log) when the record cannot be fetched
    or parsed, so one bad advisory never sinks the whole scan.
    """
    try:
        raw = client.get(f"{OSV_VULN_ENDPOINT}/{vuln_id}", ttl=VULN_DETAIL_TTL)
    except NetworkError as exc:
        logging.debug(f"Could not fetch OSV record {vuln_id}: {exc}")
        return None
    if not isinstance(raw, dict):
        return None
    return _normalize_osv_record(raw)


def _normalize_osv_record(raw: dict) -> Vulnerability:
    """Map a raw OSV advisory dict into a :py:class:`Vulnerability`."""
    vuln_id = raw.get("id", "")

    cvss_vector = None
    for sev in raw.get("severity", []) or []:
        score = sev.get("score")
        if score:
            cvss_vector = score
            # Prefer the highest CVSS version present; OSV lists at most
            # one per type, so the last CVSS_V4/V3 wins over V2.
            if sev.get("type") in ("CVSS_V4", "CVSS_V3"):
                break

    severity_label = _normalize_severity(
        (raw.get("database_specific") or {}).get("severity"),
    )

    cwe_ids = tuple((raw.get("database_specific") or {}).get("cwe_ids", []) or [])

    fixed_versions = _extract_fixed_versions(raw.get("affected", []) or [])

    references = tuple(
        ref["url"]
        for ref in raw.get("references", []) or []
        if ref.get("url")
    )

    return Vulnerability(
        id=vuln_id,
        source="OSV",
        summary=raw.get("summary"),
        description=raw.get("details"),
        severity=severity_label,
        cvss_vector=cvss_vector,
        cwe_ids=cwe_ids,
        aliases=tuple(raw.get("aliases", []) or []),
        references=references,
        fixed_versions=fixed_versions,
        published_date=_parse_timestamp(raw.get("published")),
        modified_date=_parse_timestamp(raw.get("modified")),
        advisory_url=f"https://osv.dev/vulnerability/{vuln_id}",
    )


def _normalize_severity(label: str | None) -> str | None:
    """Collapse GHSA-style severity labels into our coarse vocabulary."""
    if not label:
        return None
    mapping = {
        "LOW": "low",
        "MODERATE": "medium",
        "MEDIUM": "medium",
        "HIGH": "high",
        "CRITICAL": "critical",
    }
    return mapping.get(label.strip().upper())


def _extract_fixed_versions(affected: list) -> tuple[str, ...]:
    """Pull the ``fixed`` events out of an OSV ``affected`` block."""
    fixed: list[str] = []
    for entry in affected:
        for rng in entry.get("ranges", []) or []:
            for event in rng.get("events", []) or []:
                if "fixed" in event:
                    fixed.append(event["fixed"])
    return tuple(dict.fromkeys(fixed))


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an OSV RFC 3339 timestamp, tolerating a trailing ``Z``."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def scan_vulnerabilities(
    purls: Iterable[str],
    client: NetworkClient,
) -> dict[str, tuple[Vulnerability, ...]]:
    """Look up advisories for every supported purl, via OSV.

    Returns a mapping from purl string to the tuple of vulnerabilities
    affecting it. Purls with no advisories (or no OSV coverage) are
    simply absent from the result. A network failure on the batch query
    propagates as :py:class:`NetworkError` for the caller to handle;
    per-advisory detail failures are swallowed so a single bad record
    only drops itself.
    """
    queries = _parse_purls(purls)
    if not queries:
        return {}

    query_list = list(queries.values())
    ids_by_index = _batch_query(query_list, client)
    if not ids_by_index:
        return {}

    # Fetch each unique advisory once, then fan out to the purls.
    detail_cache: dict[str, Vulnerability | None] = {}
    result: dict[str, tuple[Vulnerability, ...]] = {}
    for index, vuln_ids in ids_by_index.items():
        query = query_list[index]
        vulns: list[Vulnerability] = []
        for vuln_id in vuln_ids:
            if vuln_id not in detail_cache:
                detail_cache[vuln_id] = _fetch_detail(vuln_id, client)
            vuln = detail_cache[vuln_id]
            if vuln is not None:
                vulns.append(vuln)
        if vulns:
            frozen = tuple(vulns)
            for purl_str in query.purls:
                result[purl_str] = frozen
    return result
