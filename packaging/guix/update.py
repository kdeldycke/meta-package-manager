#!/usr/bin/env python3
"""Update the Guix package definition to the latest PyPI release.

Fetches the latest release version from GitHub, retrieves the sdist SHA256 from
PyPI, converts it to Nix-style base32, and patches the .scm file in-place.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

# Nix uses a custom base32 alphabet (missing e, m, o, t, u).
NIX_BASE32_CHARS = "0123456789abcdfghijklmnpqrsvwxyz"

GITHUB_API = (
    "https://api.github.com/repos/kdeldycke/meta-package-manager/releases/latest"
)
PYPI_API = "https://pypi.org/pypi/meta-package-manager/{version}/json"
SCM_FILE = Path(__file__).parent / "meta-package-manager.scm"


def nix_base32(digest: bytes) -> str:
    """Encode a hash digest as Nix-style base32."""
    hash_size = len(digest)
    out_len = hash_size * 8 // 5 + (1 if hash_size * 8 % 5 > 0 else 0)
    result = []
    for n in range(out_len - 1, -1, -1):
        b = n * 5
        i = b // 8
        j = b % 8
        c = digest[i] >> j
        if i < hash_size - 1:
            c |= digest[i + 1] << (8 - j)
        result.append(NIX_BASE32_CHARS[c & 0x1F])
    return "".join(result)


def hex_to_nix_base32(hex_str: str) -> str:
    """Convert a hex-encoded hash to Nix-style base32."""
    return nix_base32(bytes.fromhex(hex_str))


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch JSON from a URL."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request) as response:
        result: dict[str, Any] = json.loads(response.read())
        return result


def get_latest_version() -> str:
    """Get the latest release version from GitHub."""
    data = fetch_json(GITHUB_API)
    tag_name: str = data["tag_name"]
    return tag_name.lstrip("v")


def get_sdist_sha256(version: str) -> str:
    """Get the SHA256 hash of the sdist from PyPI."""
    data = fetch_json(PYPI_API.format(version=version))
    for url_info in data["urls"]:
        if url_info["packagetype"] == "sdist":
            sha256: str = url_info["digests"]["sha256"]
            return sha256
    msg = f"No sdist found on PyPI for version {version}"
    raise RuntimeError(msg)


def get_current_version(scm_path: Path) -> str:
    """Extract the current version from the .scm file."""
    content = scm_path.read_text()
    match = re.search(r'\(version "([^"]+)"\)', content)
    if not match:
        msg = f"Cannot find version string in {scm_path}"
        raise RuntimeError(msg)
    return match.group(1)


def update_scm(scm_path: Path, version: str, base32_hash: str) -> None:
    """Update the version and hash in the .scm file."""
    content = scm_path.read_text()
    content = re.sub(
        r'\(version "[^"]+"\)',
        f'(version "{version}")',
        content,
    )
    content = re.sub(
        r'\(base32 "[^"]+"\)',
        f'(base32 "{base32_hash}")',
        content,
    )
    scm_path.write_text(content)


def main() -> None:
    """Check for a new release and update the Guix package definition."""
    scm_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SCM_FILE

    latest = get_latest_version()
    current = get_current_version(scm_path)

    if latest == current:
        print(f"Already up to date at {current}.")
        return

    print(f"Updating {current} -> {latest}")

    sha256_hex = get_sdist_sha256(latest)
    base32_hash = hex_to_nix_base32(sha256_hex)
    print(f"SHA256 (hex):    {sha256_hex}")
    print(f"SHA256 (base32): {base32_hash}")

    update_scm(scm_path, latest, base32_hash)
    print(f"Updated {scm_path}")


if __name__ == "__main__":
    main()
