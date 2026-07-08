"""Update the Guix package definition to the latest release.

Fetches the latest release version from GitHub, computes the Guix
``git-fetch`` hash of the tagged checkout, and patches the .scm file in-place.

The hash is the SHA256 of the NAR serialization of the checkout with its
``.git`` directory removed, encoded as Nix-style base32: the same value as
``guix hash --serializer=nar --hash=sha256 --exclude-vcs``. It is reproduced
here in pure Python so the script needs neither ``guix`` nor ``nix`` installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

# Nix uses a custom base32 alphabet (missing e, m, o, t, u).
NIX_BASE32_CHARS = "0123456789abcdfghijklmnpqrsvwxyz"

GITHUB_API = (
    "https://api.github.com/repos/kdeldycke/meta-package-manager/releases/latest"
)
REPO_URL = "https://github.com/kdeldycke/meta-package-manager"
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


def nar_chunk(data: bytes) -> bytes:
    """Serialize a byte string as a NAR chunk: an 8-byte little-endian length,
    the payload, then zero-padding up to the next multiple of 8."""
    return len(data).to_bytes(8, "little") + data + b"\x00" * (-len(data) % 8)


def nar_serialize(path: Path) -> bytes:
    """Serialize a filesystem node into the NAR format Guix hashes.

    Only the node type, the executable bit of regular files, file contents, and
    symlink targets are encoded: timestamps and other permission bits are
    ignored, exactly as Nix archives do. Directory entries are sorted by the
    byte value of their name.
    """
    out = [nar_chunk(b"(")]
    if path.is_symlink():
        out += [
            nar_chunk(b"type"),
            nar_chunk(b"symlink"),
            nar_chunk(b"target"),
            nar_chunk(os.fsencode(os.readlink(path))),
        ]
    elif path.is_dir():
        out += [nar_chunk(b"type"), nar_chunk(b"directory")]
        for name in sorted(os.listdir(path), key=os.fsencode):
            out += [
                nar_chunk(b"entry"),
                nar_chunk(b"("),
                nar_chunk(b"name"),
                nar_chunk(os.fsencode(name)),
                nar_chunk(b"node"),
                nar_serialize(path / name),
                nar_chunk(b")"),
            ]
    else:
        out += [nar_chunk(b"type"), nar_chunk(b"regular")]
        if path.stat().st_mode & 0o111:
            out += [nar_chunk(b"executable"), nar_chunk(b"")]
        out += [nar_chunk(b"contents"), nar_chunk(path.read_bytes())]
    out.append(nar_chunk(b")"))
    return b"".join(out)


def get_git_base32(version: str) -> str:
    """Compute the Guix ``git-fetch`` hash of the ``v{version}`` checkout.

    The tree is materialized from the raw blobs (``core.autocrlf=false``) so no
    working-tree filter can diverge it from the filter-free checkout Guix
    performs with libgit2.
    """
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "checkout"
        subprocess.run(
            (
                "git",
                "-c",
                "core.autocrlf=false",
                "-c",
                "advice.detachedHead=false",
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--branch",
                f"v{version}",
                REPO_URL,
                str(checkout),
            ),
            check=True,
        )
        shutil.rmtree(checkout / ".git")
        nar = nar_chunk(b"nix-archive-1") + nar_serialize(checkout)
    return nix_base32(hashlib.sha256(nar).digest())


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

    base32_hash = get_git_base32(latest)
    print(f"SHA256 (base32): {base32_hash}")

    update_scm(scm_path, latest, base32_hash)
    print(f"Updated {scm_path}")


if __name__ == "__main__":
    main()
