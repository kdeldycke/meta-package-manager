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
"""HTTP client and on-disk response cache for the opt-in online SBOM mode.

This is the shared plumbing behind ``mpm --network sbom``. The
:py:class:`NetworkClient` wraps ``httpx`` with a filesystem cache and a
bounded retry/backoff policy, so the higher-level adapters (currently
just :py:mod:`meta_package_manager.sbom.vulnerabilities`, which queries
OSV.dev) stay free of transport concerns.

Heavy imports (``httpx``, ``platformdirs``) are guarded behind a
``try/except`` exactly like the SPDX and CycloneDX writers: a default
install does not pull them, so this module is importable but
:py:data:`network_support` reports ``False`` until the user installs the
``[sbom-online]`` extra.

The cache is mandatory rather than optional. The online mode is only
worth using with a warm cache: vulnerability records are immutable once
published, batch queries are large, and remote services rate-limit. The
cache lives under the OS-appropriate user cache directory (resolved via
``platformdirs``) so repeat runs hit disk instead of the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from typing_extensions import Self

network_support = True
try:
    import httpx
    from platformdirs import user_cache_dir
except ImportError:
    network_support = False
    logging.getLogger("meta_package_manager").debug(
        "Online SBOM support disabled: "
        "install meta-package-manager[sbom-online] to enable it.",
    )

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping


DEFAULT_TTL = 86400
"""Default cache time-to-live in seconds (24 hours).

Vulnerability *listings* (which advisories affect a package) can change
as new advisories are published, so the batch-query responses get this
finite TTL. Immutable per-advisory detail records are cached with a far
longer TTL by their callers.
"""

DEFAULT_TIMEOUT = 30.0
"""Per-request timeout in seconds.

OSV batch queries over a few hundred purls comfortably answer within
this window; the value is generous enough to absorb a slow link without
hanging a scan indefinitely.
"""

MAX_RETRIES = 3
"""Number of retry attempts on transient failures before giving up."""

CACHE_SIZE_CEILING = 1_000_000_000
"""Soft ceiling (1 GB) past which the cache directory is pruned.

The cache is keyed by unique request payloads the user has ever issued,
so in practice it stays tiny (a few MB of JSON). The ceiling is a
runaway backstop, not an expected operating point.
"""


class NetworkError(Exception):
    """Raised when a network operation cannot complete.

    The CLI catches this at the orchestration layer and degrades
    gracefully: the SBOM still renders, just without the data the failed
    call would have contributed.
    """


@dataclass(frozen=True)
class _CacheEntry:
    """One cached HTTP response, persisted as a JSON sidecar file."""

    fetched_at: datetime
    ttl: int
    body: object

    def is_fresh(self, now: datetime) -> bool:
        """``True`` if the entry has not yet exceeded its TTL."""
        age = (now - self.fetched_at).total_seconds()
        return age < self.ttl


class NetworkClient:
    """Caching HTTP client for the online SBOM adapters.

    Construct one per ``mpm sbom`` run and pass it to the adapter
    functions. The same instance reuses a single ``httpx.Client``
    (connection pooling) and one cache directory for the whole run.

    .. warning::

        Instantiating requires the ``[sbom-online]`` extra. Callers must
        check :py:data:`network_support` before constructing, mirroring
        the ``spdx_support`` / ``cyclonedx_support`` guards used by the
        renderers.
    """

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        default_ttl: int = DEFAULT_TTL,
        timeout: float = DEFAULT_TIMEOUT,
        trust_env: bool = True,
    ) -> None:
        """Set up the cache directory and the underlying HTTP client.

        ``cache_dir`` defaults to ``<user-cache>/meta-package-manager/sbom``
        when not supplied. The directory is created if missing.

        ``trust_env`` is forwarded to ``httpx.Client``: left ``True`` so a
        user's ``HTTP(S)_PROXY`` / ``ALL_PROXY`` environment is honored.
        The test suite sets it ``False`` to bypass any ambient proxy.
        """
        if not network_support:
            raise NetworkError(
                "Online SBOM support requires the [sbom-online] extra. "
                "Install with: pip install meta-package-manager[sbom-online]",
            )
        if cache_dir is None:
            cache_dir = Path(user_cache_dir("meta-package-manager")) / "sbom"
        # The cache is an optimization, not a requirement: if the directory
        # cannot be created (read-only home, sandbox, locked-down CI), the
        # client still works, just without persistence. ``cache_dir`` is set
        # to ``None`` in that case and every cache read/write becomes a no-op.
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logging.debug(f"Response cache disabled ({cache_dir}): {exc}")
            cache_dir = None
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        self.timeout = timeout
        self.trust_env = trust_env
        # The httpx.Client is built lazily on the first real fetch. A run
        # whose requests are all served from cache never constructs it,
        # which keeps fully-cached scans free of connection setup (and of
        # any environment-proxy initialization httpx does at construction).
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """The underlying HTTP client, constructed on first access.

        A construction failure (notably a configured SOCKS proxy with no
        ``socksio`` installed) is converted to :py:class:`NetworkError` so
        the caller degrades gracefully rather than surfacing a raw
        ``ImportError`` from deep in httpx.
        """
        if self._client is None:
            try:
                self._client = httpx.Client(
                    timeout=self.timeout,
                    headers={"User-Agent": "meta-package-manager"},
                    follow_redirects=True,
                    trust_env=self.trust_env,
                )
            except Exception as exc:
                raise NetworkError(
                    f"Could not initialize the HTTP client: {exc}",
                ) from exc
        return self._client

    def close(self) -> None:
        """Release the underlying HTTP connection pool, if one was opened."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _cache_path(self, cache_key: str) -> Path | None:
        """Map a cache key to its on-disk JSON sidecar path.

        Returns ``None`` when caching is disabled (no writable directory),
        so callers naturally skip the read/write.
        """
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, cache_key: str) -> object | None:
        """Return the cached body for ``cache_key`` if present and fresh.

        A malformed or unreadable cache file is treated as a miss rather
        than an error: the worst case is a redundant refetch.
        """
        path = self._cache_path(cache_key)
        if path is None or not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entry = _CacheEntry(
                fetched_at=datetime.fromisoformat(raw["fetched_at"]),
                ttl=int(raw["ttl"]),
                body=raw["body"],
            )
        except (ValueError, KeyError, OSError):
            return None
        if not entry.is_fresh(datetime.now(tz=timezone.utc)):
            return None
        return entry.body

    def _write_cache(self, cache_key: str, body: object, ttl: int) -> None:
        """Persist ``body`` under ``cache_key`` with the given TTL.

        Cache write failures are swallowed: an uncacheable response is a
        performance regression, not a correctness problem.
        """
        path = self._cache_path(cache_key)
        if path is None:
            return
        payload = {
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
            "ttl": ttl,
            "body": body,
        }
        try:
            path.write_text(json.dumps(payload), encoding="utf-8")
        except (OSError, TypeError) as exc:
            logging.debug(f"Could not cache response for {cache_key!r}: {exc}")

    def get(self, url: str, *, ttl: int | None = None) -> object:
        """GET ``url``, returning the decoded JSON body (cached)."""
        return self._request("GET", url, None, ttl)

    def post(
        self,
        url: str,
        json_body: Mapping,
        *,
        ttl: int | None = None,
    ) -> object:
        """POST ``json_body`` to ``url``, returning the decoded JSON body (cached)."""
        return self._request("POST", url, json_body, ttl)

    def _request(
        self,
        method: str,
        url: str,
        json_body: Mapping | None,
        ttl: int | None,
    ) -> object:
        """Shared cache-then-fetch path for GET and POST.

        Builds a cache key from the method, URL, and (for POST) a
        canonical serialization of the body. On a cache miss, issues the
        request with bounded exponential backoff, honoring any
        ``Retry-After`` header on 429/503 responses.
        """
        effective_ttl = self.default_ttl if ttl is None else ttl
        cache_key = self._make_cache_key(method, url, json_body)

        cached = self._read_cache(cache_key)
        if cached is not None:
            logging.debug(f"Cache hit for {method} {url}")
            return cached

        logging.debug(f"Cache miss for {method} {url}, fetching.")
        body = self._fetch_with_retries(method, url, json_body)
        self._write_cache(cache_key, body, effective_ttl)
        return body

    @staticmethod
    def _make_cache_key(
        method: str,
        url: str,
        json_body: Mapping | None,
    ) -> str:
        """Build a deterministic cache key from request parameters.

        The body is serialized with sorted keys so two equivalent
        payloads hash to the same key regardless of dict ordering.
        """
        parts = [method.upper(), url]
        if json_body is not None:
            parts.append(json.dumps(json_body, sort_keys=True))
        return "\n".join(parts)

    def _fetch_with_retries(
        self,
        method: str,
        url: str,
        json_body: Mapping | None,
    ) -> object:
        """Issue the HTTP request, retrying transient failures.

        Retries on connection errors and on 429/503 status codes, with
        exponential backoff (1s, 2s, 4s). A ``Retry-After`` header, when
        present, overrides the computed backoff. Raises
        :py:class:`NetworkError` once retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.request(method, url, json=json_body)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._sleep_backoff(attempt, None)
                continue

            if response.status_code in (429, 503):
                last_exc = NetworkError(
                    f"{url} returned {response.status_code}",
                )
                self._sleep_backoff(attempt, response.headers.get("Retry-After"))
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Non-retryable HTTP error (4xx other than 429): fail fast.
                raise NetworkError(f"{url} failed: {exc}") from exc

            try:
                return response.json()
            except ValueError as exc:
                raise NetworkError(f"{url} returned invalid JSON: {exc}") from exc

        raise NetworkError(
            f"{url} failed after {MAX_RETRIES} attempts: {last_exc}",
        )

    @staticmethod
    def _sleep_backoff(attempt: int, retry_after: str | None) -> None:
        """Sleep before the next retry attempt.

        Uses the server-provided ``Retry-After`` delay (in seconds) when
        present and parseable, otherwise exponential backoff keyed on the
        attempt index.
        """
        delay = 2.0**attempt
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                pass
        time.sleep(delay)
