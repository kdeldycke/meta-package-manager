#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""Assemble the Debian source trees `mpm`'s Launchpad PPA is built from.

One tree per Ubuntu series, each a `3.0 (native)` source package carrying
`mpm` and its whole Python dependency tree under `vendor/`.

Vendoring is what lets one package serve every live series. Ubuntu ships
neither `click-extra` nor `extra-platforms`, and its `python3-click` and
`python3-deepmerge` are older than `click-extra` accepts on every series up to
and including the current LTS, so a package built against the archive would
reach nobody. Shipping newer copies of those two as PPA packages instead would
upgrade `click` for every Python application on any machine that adds the PPA.

Resolution happens here rather than on the builder: a Launchpad builder has no
network, so the wheels have to be unpacked into the tarball first. Markers are
resolved against `mpm`'s own `requires-python` floor, which pulls in the
`tomli` and `backports-strenum` shims the oldest series needs and which the
newest simply ignores.

Building and uploading the assembled trees:

```shell-session
$ ./packaging/ppa/build-source.py --output ./dist
$ cd ./dist/meta-package-manager-7.6.1ppa1~noble1
$ debuild -S -sa
$ dput ppa:kdeldycke/mpm ../meta-package-manager_7.6.1ppa1~noble1_source.changes
```
"""

from __future__ import annotations

import argparse
import email.utils
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SPEC_DIR = Path(__file__).parent
REPO_DIR = SPEC_DIR.parent.parent

# Every Ubuntu series still receiving updates, plus the development one. The
# `~{series}` suffixes sort in release order because the codenames happen to
# be alphabetical, which is what upgrades a machine moving from one series to
# the next.
SERIES = ("jammy", "noble", "resolute", "stonking")

MAINTAINER = "Kevin Deldycke <kevin@deldycke.com>"


def run(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    """Run a command, echoing it the way the workflows disclose theirs."""
    print(f"$ {' '.join(map(str, args))}", file=sys.stderr)
    return subprocess.run(args, check=True, text=True, encoding="UTF-8", **kwargs)


def require_tools() -> None:
    """Fail early and legibly when `git` or `uv` is missing from `PATH`.

    Both are invoked by name, so a shell that never sourced a login profile
    finds neither, `~/.local/bin` being where the uv installer puts it. That
    otherwise surfaces as a bare `FileNotFoundError` naming no remedy.
    """
    missing = [tool for tool in ("git", "uv") if shutil.which(tool) is None]
    if missing:
        msg = (
            f"Not on PATH: {', '.join(missing)}. A non-login shell often misses "
            "~/.local/bin; add it and run again."
        )
        raise SystemExit(msg)


def newest_tag() -> str:
    """Return the version of the newest `v*` tag, with no `v` prefix."""
    tags = run(
        "git", "-C", str(REPO_DIR), "tag", "--sort=-v:refname", "--list", "v*",
        stdout=subprocess.PIPE,
    ).stdout.split()
    if not tags:
        msg = "No `v*` tag found: a PPA builds a released version."
        raise SystemExit(msg)
    return tags[0].removeprefix("v")


def export_tag_metadata(version: str, workdir: Path) -> Path:
    """Extract `pyproject.toml` and `uv.lock` from the release tag.

    The lockfile of the tag is what pins the dependency set the release was
    tested with, rather than whatever resolves from PyPI on the day the
    package is assembled.
    """
    archive = workdir / "tag.tar"
    with archive.open("wb") as stream:
        run(
            "git", "-C", str(REPO_DIR), "archive", f"v{version}",
            "pyproject.toml", "uv.lock",
            stdout=stream,
        )
    project = workdir / "project"
    project.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(project, filter="data")
    return project


def python_floor(project: Path) -> str:
    """Read `requires-python` and return its bare floor, like `3.10`."""
    content = (project / "pyproject.toml").read_text(encoding="UTF-8")
    match = re.search(r'^requires-python\s*=\s*"[^0-9]*([0-9]+\.[0-9]+)', content, re.MULTILINE)
    if not match:
        msg = "No `requires-python` floor found in the tag's pyproject.toml."
        raise SystemExit(msg)
    return match.group(1)


def build_vendor_tree(version: str, project: Path, target: Path) -> None:
    """Unpack `mpm` and its locked dependency closure into one flat tree."""
    requirements = project / "requirements.txt"
    with requirements.open("w", encoding="UTF-8") as stream:
        run(
            "uv", "export", "--project", str(project), "--frozen", "--no-dev",
            "--no-emit-project", "--no-hashes", "--format", "requirements.txt",
            stdout=stream,
        )
    with requirements.open("a", encoding="UTF-8") as stream:
        stream.write(f"meta-package-manager=={version}\n")

    run(
        "uv", "pip", "install", "--no-progress", "--target", str(target),
        # Resolve markers at the floor, so the tree carries the shims the
        # oldest series needs; a newer interpreter never imports them.
        "--python-version", python_floor(project),
        # `dh_python3` byte-compiles at install time, for the Python the
        # series ships, which is the only version tag that can be right.
        "--no-compile-bytecode",
        "--requirements", str(requirements),
    )

    # uv leaves its own lock behind, and writes console scripts carrying the
    # shebang of the interpreter that ran it. /usr/bin/mpm is mpm-wrapper.py.
    shutil.rmtree(target / "bin", ignore_errors=True)
    (target / ".lock").unlink(missing_ok=True)

    # A library module opening on `#!/usr/bin/env python` asks for an
    # interpreter Debian does not ship, and nothing ever runs it: /usr/bin/mpm
    # is mpm-wrapper.py. An executable module is a different case and keeps its
    # line, `bar_plugin.py` being the script SwiftBar runs directly.
    for module in target.rglob("*.py"):
        if module.stat().st_mode & 0o111:
            continue
        source = module.read_bytes()
        if source.startswith(b"#!"):
            _, _, body = source.partition(b"\n")
            module.write_bytes(body)


def write_changelog(tree: Path, deb_version: str, series: str, version: str) -> None:
    stamp = email.utils.format_datetime(datetime.now(timezone.utc))
    (tree / "debian" / "changelog").write_text(
        f"meta-package-manager ({deb_version}) {series}; urgency=medium\n"
        f"\n"
        f"  * Build mpm {version} for Ubuntu {series}.\n"
        f"\n"
        f" -- {MAINTAINER}  {stamp}\n",
        encoding="UTF-8",
    )


def assemble(version: str, series: str, vendor: Path, output: Path, ppa_rev: int,
             series_rev: int) -> Path:
    deb_version = f"{version}ppa{ppa_rev}~{series}{series_rev}"
    tree = output / f"meta-package-manager-{deb_version}"
    shutil.rmtree(tree, ignore_errors=True)
    tree.mkdir(parents=True)

    shutil.copytree(SPEC_DIR / "debian", tree / "debian")
    shutil.copy2(SPEC_DIR / "mpm-wrapper.py", tree / "mpm-wrapper.py")
    shutil.copytree(vendor, tree / "vendor")
    write_changelog(tree, deb_version, series, version)
    return tree


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--mpm-version",
        help="Released version to package. Defaults to the newest `v*` tag.",
    )
    parser.add_argument(
        "--series", action="append", choices=SERIES,
        help="Ubuntu series to assemble for. Repeatable. Defaults to all of them.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("dist"),
        help="Directory the source trees are written to.",
    )
    parser.add_argument(
        "--ppa-revision", type=int, default=1,
        help="Bumped when a series is rebuilt from the same mpm version.",
    )
    parser.add_argument(
        "--series-revision", type=int, default=1,
        help="Bumped when one series alone is rebuilt.",
    )
    args = parser.parse_args()

    require_tools()
    version = args.mpm_version or newest_tag()
    series_list = args.series or list(SERIES)
    args.output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        project = export_tag_metadata(version, workdir)
        vendor = workdir / "vendor"
        build_vendor_tree(version, project, vendor)
        for series in series_list:
            tree = assemble(
                version, series, vendor, args.output,
                args.ppa_revision, args.series_revision,
            )
            print(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
