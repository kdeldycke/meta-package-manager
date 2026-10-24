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

All network traffic is mocked with `respx`; nothing here touches the
real OSV API. The `NetworkClient` is constructed with `trust_env=False`
so an ambient proxy in the test environment cannot interfere.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

# httpx and respx back the opt-in online SBOM layer (the [sbom-online] extra).
# importorskip skips the whole module when they are absent so a hermetic
# packager build collects it cleanly instead of crashing on the imports below.
pytest.importorskip("httpx")
pytest.importorskip("respx")

import httpx
import respx

from meta_package_manager.sbom import _network
from meta_package_manager.sbom._network import (
    NetworkClient,
    NetworkError,
)
from meta_package_manager.sbom.vulnerabilities import (
    OSV_BATCH_ENDPOINT,
    OSV_ECOSYSTEMS,
    OSV_VULN_ENDPOINT,
    Vulnerability,
    _extract_fixed_versions,
    _fetch_detail,
    _normalize_osv_record,
    _normalize_severity,
    _parse_purls,
    _parse_timestamp,
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


def test_network_client_needs_the_online_extra(monkeypatch, tmp_path):
    """Without `httpx` and `platformdirs`, the client refuses to start."""
    monkeypatch.setattr(_network, "network_support", False)
    with pytest.raises(NetworkError, match=r"requires the \[sbom-online\] extra"):
        NetworkClient(cache_dir=tmp_path)


def test_network_client_defaults_to_the_user_cache(monkeypatch, tmp_path):
    """With no folder given, the cache goes to the user cache folder of mpm."""
    monkeypatch.setattr(
        _network, "user_cache_dir", lambda appname: str(tmp_path / appname)
    )
    cache_dir = tmp_path / "meta-package-manager" / "sbom"
    with NetworkClient(trust_env=False) as client:
        assert client.cache_dir == cache_dir
    assert cache_dir.is_dir()


def test_network_client_works_without_a_cache(tmp_path):
    """A cache folder that cannot be created turns the cache off, not the client."""
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"")
    with NetworkClient(cache_dir=blocker / "sbom", trust_env=False) as client:
        assert client.cache_dir is None
        with respx.mock(base_url="https://api.osv.dev") as mock:
            route = mock.get("/v1/vulns/GHSA-x").mock(
                return_value=httpx.Response(200, json={"id": "GHSA-x"}),
            )
            assert client.get(f"{OSV_VULN_ENDPOINT}/GHSA-x") == {"id": "GHSA-x"}
            assert client.get(f"{OSV_VULN_ENDPOINT}/GHSA-x") == {"id": "GHSA-x"}
    # Nothing was cached, so both requests reached the network.
    assert route.call_count == 2


def test_network_client_reports_a_client_that_cannot_start(client, monkeypatch):
    """An HTTP client that fails to build, like one behind a SOCKS proxy with no
    `socksio`, fails as `NetworkError` rather than as the raw `ImportError`."""

    def refuse(**kwargs):
        raise ImportError("socksio")

    monkeypatch.setattr(_network.httpx, "Client", refuse)
    with pytest.raises(NetworkError, match="Could not initialize the HTTP client"):
        client.get(f"{OSV_VULN_ENDPOINT}/GHSA-x")


@pytest.mark.parametrize(
    "entry",
    (
        pytest.param("not json", id="corrupt"),
        pytest.param(
            json.dumps({"ttl": 60, "body": {"id": "GHSA-x"}}), id="incomplete"
        ),
        pytest.param(
            json.dumps({
                "fetched_at": "2021-06-01T00:00:00+00:00",
                "ttl": 60,
                "body": {"id": "GHSA-x"},
            }),
            id="stale",
        ),
    ),
)
def test_network_client_refetches_an_unusable_cache_entry(client, entry):
    """A cache entry that does not parse, or that expired, counts as a miss."""
    url = f"{OSV_VULN_ENDPOINT}/GHSA-x"
    cache_file = client._cache_path(client._make_cache_key("GET", url, None))
    cache_file.write_text(entry, encoding="UTF-8")
    with respx.mock(base_url="https://api.osv.dev") as mock:
        route = mock.get("/v1/vulns/GHSA-x").mock(
            return_value=httpx.Response(200, json={"id": "GHSA-x", "fresh": True}),
        )
        assert client.get(url) == {"id": "GHSA-x", "fresh": True}
    assert route.call_count == 1
    # The new answer replaces the unusable entry.
    cached = json.loads(cache_file.read_text(encoding="UTF-8"))
    assert cached["body"] == {"id": "GHSA-x", "fresh": True}


def test_network_client_skips_a_body_it_cannot_cache(client, caplog):
    """A body that JSON cannot encode is not cached, and the write never raises."""
    with caplog.at_level(logging.DEBUG):
        client._write_cache("GET\nkey", {"when": object()}, 60)
    assert "Could not cache response for 'GET\\nkey'" in caplog.text
    assert not list(client.cache_dir.glob("*.json"))


def test_network_client_retries_a_dropped_connection(client, monkeypatch):
    """A connection error is retried after the first backoff delay."""
    sleeps: list[float] = []
    monkeypatch.setattr(_network.time, "sleep", sleeps.append)
    with respx.mock(base_url="https://api.osv.dev") as mock:
        mock.get("/v1/vulns/GHSA-x").mock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                httpx.Response(200, json={"id": "GHSA-x"}),
            ],
        )
        assert client.get(f"{OSV_VULN_ENDPOINT}/GHSA-x") == {"id": "GHSA-x"}
    assert sleeps == [1.0]


@pytest.mark.parametrize(
    ("attempt", "retry_after", "expected"),
    (
        pytest.param(0, None, 1.0, id="first-backoff"),
        pytest.param(2, None, 4.0, id="third-backoff"),
        pytest.param(2, "7", 7.0, id="retry-after-seconds"),
        # RFC 9110 also allows an HTTP date, which the client does not read.
        pytest.param(1, "Fri, 31 Dec 1999 23:59:59 GMT", 2.0, id="retry-after-date"),
    ),
)
def test_sleep_backoff_honors_a_retry_after_in_seconds(
    monkeypatch, attempt, retry_after, expected
):
    sleeps: list[float] = []
    monkeypatch.setattr(_network.time, "sleep", sleeps.append)
    NetworkClient._sleep_backoff(attempt, retry_after)
    assert sleeps == [expected]


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
        # An alias lifted from an upstream document spells its type per
        # the purl spec, not as an mpm manager id: `pypi`, never `pip`.
        (["pkg:pypi/yt-dlp@2026.8.19"], [("PyPI", "yt-dlp", "2026.8.19")]),
        (["pkg:maven/org.example/widget@1.0.0"], [("Maven", "widget", "1.0.0")]),
        (
            ["pkg:nuget/Newtonsoft.Json@13.0.3"],
            [("NuGet", "Newtonsoft.Json", "13.0.3")],
        ),
        # CPAN is the one registry Homebrew resolves that OSV does not
        # index, so it must stay unmapped rather than query a bogus one.
        (["pkg:cpan/DROLSKY/DateTime@1.65"], []),
    ),
)
def test_parse_purls_maps_ecosystems(purls, expected_coordinates):
    queries = _parse_purls(purls)
    coords = sorted((q.ecosystem, q.name, q.version) for q in queries.values())
    assert coords == sorted(expected_coordinates)


def test_osv_ecosystems_cover_every_canonical_alias_type():
    """Homebrew resolves a formula's source to one of ten registries.

    Nine are OSV ecosystems and must be mapped under their canonical purl
    type, or every alias is skipped and the upstream-coordinate route is a
    no-op. CPAN is the tenth and stays out: OSV indexes no such ecosystem.
    """
    assert OSV_ECOSYSTEMS.keys() >= {
        "cargo",
        "cran",
        "gem",
        "hackage",
        "hex",
        "maven",
        "npm",
        "nuget",
        "pypi",
    }
    assert "cpan" not in OSV_ECOSYSTEMS


def test_parse_purls_skips_an_unparsable_purl():
    queries = _parse_purls(["django==1.0.0", "pkg:pip/django@1.0.0"])
    coords = [(q.ecosystem, q.name, q.version) for q in queries.values()]
    assert coords == [("PyPI", "django", "1.0.0")]


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, None),
        ("", None),
        ("2021-06-01T00:00:00Z", datetime(2021, 6, 1, tzinfo=timezone.utc)),
        ("2021-06-01", datetime(2021, 6, 1)),
        ("June 2021", None),
    ),
)
def test_parse_timestamp(value, expected):
    assert _parse_timestamp(value) == expected


def test_fetch_detail_drops_a_record_that_is_not_an_object(client):
    """A detail answer that is not a JSON object yields no advisory."""
    with respx.mock(base_url="https://api.osv.dev") as mock:
        mock.get("/v1/vulns/GHSA-x").mock(
            return_value=httpx.Response(200, json=["GHSA-x"]),
        )
        assert _fetch_detail("GHSA-x", client) is None


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
