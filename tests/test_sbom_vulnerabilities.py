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

"""Tests for the opt-in online SBOM layer: HTTP cache and OSV adapter.

All network traffic is mocked with ``respx``; nothing here touches the
real OSV API. The :py:class:`NetworkClient` is constructed with
``trust_env=False`` so an ambient proxy in the test environment cannot
interfere.
"""

from __future__ import annotations

import json

import pytest

# httpx and respx back the opt-in online SBOM layer (the [sbom-online] extra).
# importorskip skips the whole module when they are absent so a hermetic
# packager build collects it cleanly instead of crashing on the imports below.
pytest.importorskip("httpx")
pytest.importorskip("respx")

import httpx
import respx

from meta_package_manager.sbom._network import (
    NetworkClient,
    NetworkError,
)
from meta_package_manager.sbom.vulnerabilities import (
    OSV_BATCH_ENDPOINT,
    OSV_VULN_ENDPOINT,
    Vulnerability,
    _extract_fixed_versions,
    _normalize_osv_record,
    _normalize_severity,
    _parse_purls,
    scan_vulnerabilities,
)

# A realistic OSV advisory detail record, trimmed to the fields the
# normalizer reads.
SAMPLE_OSV_RECORD = {
    "id": "GHSA-aaaa-bbbb-cccc",
    "summary": "Cross-site scripting in Example",
    "details": "A long description of the flaw.",
    "aliases": ["CVE-2021-99999"],
    "modified": "2021-06-01T00:00:00Z",
    "published": "2021-01-01T00:00:00Z",
    "severity": [
        {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
    ],
    "affected": [
        {
            "package": {"ecosystem": "PyPI", "name": "example"},
            "ranges": [
                {
                    "type": "ECOSYSTEM",
                    "events": [{"introduced": "0"}, {"fixed": "1.0.1"}],
                },
            ],
        },
    ],
    "references": [{"type": "WEB", "url": "https://example.com/advisory"}],
    "database_specific": {"severity": "CRITICAL", "cwe_ids": ["CWE-79"]},
}


@pytest.fixture
def client(tmp_path):
    """A cache-backed NetworkClient isolated to a temp dir, proxy-free."""
    with NetworkClient(cache_dir=tmp_path, trust_env=False) as network_client:
        yield network_client


def test_network_client_caches_responses(client):
    """A second identical request is served from disk, not the network."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        route = mock.post("/v1/querybatch").mock(
            return_value=httpx.Response(200, json={"results": [{}]}),
        )
        payload = {"queries": [{"package": {"ecosystem": "PyPI", "name": "x"}}]}
        first = client.post(OSV_BATCH_ENDPOINT, payload)
        second = client.post(OSV_BATCH_ENDPOINT, payload)
        assert first == second
        assert route.call_count == 1


def test_network_client_retries_then_raises(client):
    """Repeated 503s exhaust retries and surface as NetworkError."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        mock.get("/v1/vulns/GHSA-x").mock(
            return_value=httpx.Response(503),
        )
        # Patch sleep so the backoff does not slow the test.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "meta_package_manager.sbom._network.time.sleep",
                lambda _seconds: None,
            )
            with pytest.raises(NetworkError):
                client.get(f"{OSV_VULN_ENDPOINT}/GHSA-x")


def test_network_client_raises_on_invalid_json(client):
    """A 200 with a non-JSON body is reported as NetworkError."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        mock.get("/v1/vulns/GHSA-x").mock(
            return_value=httpx.Response(200, text="not json"),
        )
        with pytest.raises(NetworkError):
            client.get(f"{OSV_VULN_ENDPOINT}/GHSA-x")


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("LOW", "low"),
        ("MODERATE", "medium"),
        ("MEDIUM", "medium"),
        ("HIGH", "high"),
        ("CRITICAL", "critical"),
        ("critical", "critical"),
        (None, None),
        ("nonsense", None),
    ),
)
def test_normalize_severity(raw, expected):
    assert _normalize_severity(raw) == expected


def test_extract_fixed_versions_dedupes():
    affected = [
        {"ranges": [{"events": [{"introduced": "0"}, {"fixed": "1.0.1"}]}]},
        {"ranges": [{"events": [{"fixed": "1.0.1"}, {"fixed": "2.0.0"}]}]},
    ]
    assert _extract_fixed_versions(affected) == ("1.0.1", "2.0.0")


def test_normalize_osv_record_full():
    vuln = _normalize_osv_record(SAMPLE_OSV_RECORD)
    assert vuln.id == "GHSA-aaaa-bbbb-cccc"
    assert vuln.source == "OSV"
    assert vuln.severity == "critical"
    assert vuln.cvss_vector is not None
    assert vuln.cvss_vector.startswith("CVSS:3.1")
    assert vuln.cwe_ids == ("CWE-79",)
    assert vuln.aliases == ("CVE-2021-99999",)
    assert vuln.fixed_versions == ("1.0.1",)
    assert vuln.references == ("https://example.com/advisory",)
    assert vuln.advisory_url == ("https://osv.dev/vulnerability/GHSA-aaaa-bbbb-cccc")
    assert vuln.published_date is not None
    assert vuln.modified_date is not None


@pytest.mark.parametrize(
    ("purls", "expected_coordinates"),
    (
        # pip maps to PyPI.
        (["pkg:pip/django@1.0.0"], [("PyPI", "django", "1.0.0")]),
        # npm passes through; yarn also maps to npm.
        (
            ["pkg:npm/lodash@4.17.0", "pkg:yarn/left-pad@1.0.0"],
            [("npm", "lodash", "4.17.0"), ("npm", "left-pad", "1.0.0")],
        ),
        # brew has no OSV ecosystem -> skipped.
        (["pkg:brew/curl@8.9.0"], []),
        # Versionless purls are skipped.
        (["pkg:pip/django"], []),
    ),
)
def test_parse_purls_maps_ecosystems(purls, expected_coordinates):
    queries = _parse_purls(purls)
    coords = sorted((q.ecosystem, q.name, q.version) for q in queries.values())
    assert coords == sorted(expected_coordinates)


def test_parse_purls_dedupes_identical_coordinates():
    queries = _parse_purls(["pkg:pip/django@1.0.0", "pkg:pip/django@1.0.0"])
    assert len(queries) == 1
    only = next(iter(queries.values()))
    assert len(only.purls) == 2


def test_scan_vulnerabilities_end_to_end(client):
    """A full batch + detail round-trip, mapping advisories back to purls."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        # The batch reports one advisory for django, none for lodash.
        mock.post("/v1/querybatch").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "GHSA-aaaa-bbbb-cccc"}]},
                        {},
                    ],
                },
            ),
        )
        mock.get("/v1/vulns/GHSA-aaaa-bbbb-cccc").mock(
            return_value=httpx.Response(200, json=SAMPLE_OSV_RECORD),
        )
        result = scan_vulnerabilities(
            ["pkg:pip/django@1.0.0", "pkg:npm/lodash@4.17.0"],
            client,
        )
    assert set(result) == {"pkg:pip/django@1.0.0"}
    (vuln,) = result["pkg:pip/django@1.0.0"]
    assert vuln.id == "GHSA-aaaa-bbbb-cccc"
    assert vuln.severity == "critical"


def test_scan_vulnerabilities_shared_advisory_fans_out(client):
    """One advisory hitting two purls is fetched once, attached twice."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        mock.post("/v1/querybatch").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "GHSA-aaaa-bbbb-cccc"}]},
                        {"vulns": [{"id": "GHSA-aaaa-bbbb-cccc"}]},
                    ],
                },
            ),
        )
        detail = mock.get("/v1/vulns/GHSA-aaaa-bbbb-cccc").mock(
            return_value=httpx.Response(200, json=SAMPLE_OSV_RECORD),
        )
        result = scan_vulnerabilities(
            ["pkg:pip/django@1.0.0", "pkg:pip/flask@2.0.0"],
            client,
        )
    assert set(result) == {"pkg:pip/django@1.0.0", "pkg:pip/flask@2.0.0"}
    # The detail endpoint is hit once despite two affected packages.
    assert detail.call_count == 1


def test_scan_vulnerabilities_no_supported_purls(client):
    """Purls with no OSV ecosystem produce an empty result and no calls."""
    with respx.mock(base_url="https://api.osv.dev", assert_all_called=False) as mock:
        batch = mock.post("/v1/querybatch")
        result = scan_vulnerabilities(["pkg:brew/curl@8.9.0"], client)
    assert result == {}
    assert batch.call_count == 0


def test_scan_vulnerabilities_skips_bad_detail(client):
    """A detail fetch that 404s drops only that advisory, not the scan."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        mock.post("/v1/querybatch").mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"vulns": [{"id": "GHSA-missing"}]}]},
            ),
        )
        mock.get("/v1/vulns/GHSA-missing").mock(
            return_value=httpx.Response(404),
        )
        result = scan_vulnerabilities(["pkg:pip/django@1.0.0"], client)
    # The advisory could not be fetched, so the package ends up with none.
    assert result == {}


def test_vulnerability_dataclass_is_frozen():
    """Vulnerability instances are immutable, safe to share across purls."""
    vuln = Vulnerability(id="GHSA-x")
    with pytest.raises((AttributeError, TypeError)):
        vuln.id = "changed"  # type: ignore[misc]


def test_batch_chunks_beyond_limit(client, monkeypatch):
    """More than OSV_BATCH_LIMIT coordinates split into multiple batches."""
    monkeypatch.setattr("meta_package_manager.sbom.vulnerabilities.OSV_BATCH_LIMIT", 2)
    with respx.mock(base_url="https://api.osv.dev") as mock:
        batch = mock.post("/v1/querybatch").mock(
            return_value=httpx.Response(200, json={"results": [{}, {}]}),
        )
        scan_vulnerabilities(
            [
                "pkg:pip/a@1",
                "pkg:pip/b@1",
                "pkg:pip/c@1",
                "pkg:pip/d@1",
            ],
            client,
        )
        # 4 coordinates / chunk size 2 = 2 batch calls.
        assert batch.call_count == 2


def test_querybatch_request_shape(client):
    """The batch payload uses ecosystem+name+version, not raw purls."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        route = mock.post("/v1/querybatch").mock(
            return_value=httpx.Response(200, json={"results": [{}]}),
        )
        scan_vulnerabilities(["pkg:pip/django@1.0.0"], client)
        sent = json.loads(route.calls[0].request.content)
    assert sent == {
        "queries": [
            {
                "package": {"ecosystem": "PyPI", "name": "django"},
                "version": "1.0.0",
            },
        ],
    }
