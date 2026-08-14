"""Update a Nix package definition to its upstream's latest GitHub release.

Fetches the latest release version from GitHub, computes the source hash using
nix-prefetch-url, and patches the .nix file in-place. Defaults to package.nix;
pass another definition's path to bump one of the dependency pins instead.

Requires Nix to be installed for hash computation.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_REPOS = {
    "click-extra.nix": "kdeldycke/click-extra",
    "extra-platforms.nix": "kdeldycke/extra-platforms",
    "package.nix": "kdeldycke/meta-package-manager",
}
"""Upstream repository each definition in this directory tracks.

Keyed on file name rather than taken from the caller: a definition and the
releases it is bumped against then cannot be paired by mistake, which is the
one way this script could write a version belonging to another project.
"""

RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_TARBALL = "https://github.com/{repo}/archive/refs/tags/v{version}.tar.gz"
PACKAGE_NIX = Path(__file__).parent / "package.nix"


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch JSON from a URL."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request) as response:
        result: dict[str, Any] = json.loads(response.read())
        return result


def get_upstream_repo(nix_path: Path) -> str:
    """Resolve the upstream repository a definition tracks, or refuse to guess."""
    repo = GITHUB_REPOS.get(nix_path.name)
    if repo is None:
        known = ", ".join(sorted(GITHUB_REPOS))
        msg = f"No upstream repository known for {nix_path.name}. Expected: {known}."
        raise RuntimeError(msg)
    return repo


def get_latest_version(repo: str) -> str:
    """Get the latest release version from GitHub."""
    data = fetch_json(RELEASES_API.format(repo=repo))
    tag_name: str = data["tag_name"]
    return tag_name.removeprefix("v")


def get_current_version(nix_path: Path) -> str:
    """Extract the current version from the .nix file."""
    content = nix_path.read_text(encoding="utf-8")
    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        msg = f"Cannot find version string in {nix_path}"
        raise RuntimeError(msg)
    return match.group(1)


def compute_sri_hash(url: str) -> str:
    """Compute the SRI hash of an unpacked source tarball using Nix tools."""
    if not shutil.which("nix-prefetch-url"):
        msg = "nix-prefetch-url not found. Install Nix to compute hashes."
        raise RuntimeError(msg)

    # Get the NAR hash in Nix base32.
    result = subprocess.run(
        ["nix-prefetch-url", "--unpack", "--type", "sha256", url],
        capture_output=True,
        text=True,
        check=True,
    )
    nix_hash = result.stdout.strip()

    # Convert to SRI format.
    result = subprocess.run(
        ["nix", "hash", "convert", "--to", "sri", f"sha256:{nix_hash}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def update_nix(nix_path: Path, version: str, sri_hash: str) -> None:
    """Update the version and hash in the .nix file."""
    content = nix_path.read_text(encoding="utf-8")
    content = re.sub(
        r'version = "[^"]+"',
        f'version = "{version}"',
        content,
    )
    content = re.sub(
        r'hash = "[^"]+"',
        f'hash = "{sri_hash}"',
        content,
    )
    nix_path.write_text(content, encoding="utf-8")


def main() -> None:
    """Check for a new release and update the Nix package definition."""
    nix_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PACKAGE_NIX
    repo = get_upstream_repo(nix_path)

    latest = get_latest_version(repo)
    current = get_current_version(nix_path)

    if latest == current:
        print(f"Already up to date at {current}.")
        return

    print(f"Updating {repo} {current} -> {latest}")

    tarball_url = GITHUB_TARBALL.format(repo=repo, version=latest)
    sri_hash = compute_sri_hash(tarball_url)
    print(f"SRI hash: {sri_hash}")

    update_nix(nix_path, latest, sri_hash)
    print(f"Updated {nix_path}")


if __name__ == "__main__":
    main()
