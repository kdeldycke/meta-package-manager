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

"""Regenerate the committed, pool-derived artifacts that Sphinx does not own.

Called by repomatic's `update-docs` job. Writes the pool-derived blocks of
`pyproject.toml` (the `[project]` keywords, the metrics subjects, the label registry
and the labeller rules), and the stub *file set* of `docs/managers/` (one `<id>.md`
per pool manager, created and deleted as managers join or leave the pool).

Everything that renders live at Sphinx build time -- the benchmark, augmentations
and per-manager tables, and the `<!-- matrix ... -->` compatibility blocks -- is
produced by the generators in {mod}`meta_package_manager._docs` and needs no
regeneration step here. The readme's manager roster calls those same generators
from a `<!-- mirror-src -->` block, refreshed by `click-extra refresh-directives`
in the same `update-docs` job.

`--check` reports which artifacts are out of date and exits non-zero without
touching the tree, so `repomatic update-docs --check` can detect drift in CI.
repomatic forwards the flag to this script; a script that silently ignored it
would keep writing and report a clean tree.
"""

from __future__ import annotations

import argparse
import re
import sys
from urllib.parse import urlparse

import tomlrt
from tomlrt import AoT, Table
from wcwidth import wcswidth

from meta_package_manager._docs import PROJECT_ROOT, manager_page_stub
from meta_package_manager.labels import (
    LABEL_RENAMES,
    LABELS,
    generate_content_rules,
    generate_file_rules,
)
from meta_package_manager.pool import pool

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path

COLUMN_WIDTH = 120
"""Line budget `pyproject-fmt` keeps an array inline within.

Its own [`column_width`](https://pyproject-fmt.readthedocs.io/en/latest/#configuration)
default, which this project never overrides. A line measuring past it is exploded
one item per line, so {func}`_string_array` has to reach the same verdict or the
`format-pyproject` and `update-docs` jobs rewrite each other forever.
"""

KEYWORDS_EXTRAS = (
    "appimage",
    "CLI",
    "cli-tools",
    "cyclonedx",
    "gnome",
    "gnome-shell",
    "gnome-shell-extension",
    "lazy.nvim",
    "mac app store",
    "macos",
    "meta-package-manager",
    "neovim",
    "nim",
    "node",
    "package",
    "package manager",
    "package url",
    "package-manager-cli",
    "php composer",
    "plugin",
    "powershell-gallery",
    "purl",
    "pwsh",
    "ruby-gem",
    "sbom",
    "spdx",
    "swiftbar",
    "swiftbar-plugin",
    "xbar",
    "xbar-plugin",
    "zb",
    "zsh",
)
"""Curated PyPI keywords beyond the manager IDs themselves.

Ecosystem names, platform names and generic discovery terms. The manager IDs come
for free from the pool: {func}`update_keywords` merges both sets into
`pyproject.toml`. A term naming one specific manager belongs on that manager's own
`keywords` attribute instead, where it cannot outlive the class it describes.
"""

METRICS_MIRRORS = {
    "emacs": "https://github.com/emacs-mirror/emacs",
}
"""Repositories the metrics sample reads in place of a manager's own.

For a manager whose `repository_url` sits on a host no forge API answers, but whose
history is mirrored on one that does: Savannah serves Emacs through cgit, and the
GitHub mirror carries the same commits.
"""

SAMPLED_FORGES = ("codeberg.org", "github.com", "gitlab.com")
"""Hosts the metrics sampler reads without an entry in its `forges` table.

repomatic's own `FORGE_APIS`. Every other host must be declared under
`[tool.repomatic.metrics] forges`, and a repository elsewhere cannot be sampled.
"""

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
"""A TOML key part that needs no quotes."""


def _toml_string(value: str) -> str:
    """Render *value* as a TOML string, the way `tomlrt` writes it."""
    return tomlrt.dumps({"v": value}).removeprefix("v = ").removesuffix("\n")


def _toml_key(*parts: str) -> str:
    """Render a dotted key, with quotes only on the parts that need them."""
    return ".".join(
        part if _BARE_KEY.fullmatch(part) else _toml_string(part) for part in parts
    )


def _string_array(
    values: tuple[str, ...], key: str = "", multiline: bool = False
) -> str:
    """Render strings as a TOML array, one item per line when asked or long.

    Both layouts replicate `pyproject-fmt`'s canonical style: inline arrays
    are padded with spaces inside the brackets, exploded arrays get a 2-space
    indent and a trailing comma. Any deviation is churn: the `format-pyproject`
    autofix job would endlessly rewrite what the `update-docs` job regenerates.
    `test_pyproject_updates_are_pyproject_fmt_fixpoint` guards the match.
    `tomlrt` has no option for the inner padding, so the array is written as
    text, then given to {func}`_parse_array`.

    The inline-or-exploded choice is `pyproject-fmt`'s own: it explodes an array
    whose whole line passes {data}`COLUMN_WIDTH` *display columns*, so *key* is
    the rendered key text the array is assigned to, without which a long key
    goes unmeasured. Width, not length: every label name here opens on an emoji,
    and `pyproject-fmt` 2.29 began counting a wide glyph as the two columns it
    occupies. `wcswidth` reproduces that count for every glyph class tested,
    where character arithmetic misses the wide ones and `unicodedata` alone
    misjudges variation selectors, ZWJ sequences and keycaps.

    :param key: Rendered key the array is assigned to, measured with it.
    :param multiline: Explode unconditionally, whatever the width.
    :return: The array as TOML text.
    """
    items = [_toml_string(value) for value in values]
    inline = f"[ {', '.join(items)} ]"
    if not multiline and wcswidth(f"{key} = {inline}") <= COLUMN_WIDTH:
        return inline
    body = "".join(f"  {item},\n" for item in items)
    return f"[\n{body}]"


def _parse_array(text: str) -> tomlrt.Array:
    """Parse a TOML array, keeping the layout *text* gives it.

    `tomlrt` copies an array that belongs to another document with its
    formatting, so the array is written in `pyproject.toml` exactly as *text*
    spells it.
    """
    return tomlrt.loads(f"array = {text}\n").array("array")


def _replace_entries(table: Table, entries: dict) -> None:
    """Make the keys of *table* exactly those of *entries*, in their order.

    The table is edited in place, so dotted keys stay dotted and the comments
    of kept keys stay with them. New keys are set before stale keys are
    deleted: `tomlrt` writes a table back as an inline table once it is empty.
    """
    for key, value in entries.items():
        table[key] = value
    for key in table.keys() - entries.keys():
        del table[key]
    order = list(entries)
    table.sort(key=order.index)


def _sync_file(path: Path, content: str, *, check: bool) -> bool:
    """Write *content* to *path*, or only report whether it would change.

    The single write gate of this module: every generator renders its target in
    full, then hands it here, so `--check` cannot drift from what a real run
    would produce.

    :param check: Report only, leaving the file untouched.
    :return: `True` when the file is out of date.
    """
    current = path.read_text(encoding="UTF-8") if path.exists() else None
    if current == content:
        return False
    if not check:
        path.write_text(content, encoding="UTF-8")
    return True


def update_labels(*, check: bool = False) -> bool:
    """Sync the label registry and labeller rules into `pyproject.toml`.

    Regenerates the three `[tool.repomatic.labels.*]` arrays from
    {mod}`meta_package_manager.labels`: `extra` (from
    {data}`~meta_package_manager.labels.LABELS`), `content-rules` and
    `file-rules` (from the pool-derived rule generators). repomatic's
    `sync-labels` and labeller jobs read these inline definitions at run time.

    ```{note}
    The edit is done with a `tomlrt` round-trip so the rest of
    `pyproject.toml` (comments, key order, formatting) is preserved: only
    the three label arrays are regenerated. The per-entry layout matches what
    `pyproject-fmt` emits, so the result survives the autofix formatting
    pass without churn.
    ```

    :param check: Report only, leaving `pyproject.toml` untouched.
    :return: `True` when the label arrays are out of date.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlrt.loads(pyproject.read_text(encoding="UTF-8"))
    labels = doc["tool"]["repomatic"]["labels"]

    # The rule sets are dotted keys on `[tool.repomatic]`, which is what
    # `pyproject-fmt` canonicalizes a table of scalars to. Editing the existing
    # tables in place keeps that form.
    for section, rules in (
        ("content-rules", generate_content_rules()),
        ("file-rules", generate_file_rules()),
    ):
        _replace_entries(
            labels[section],
            {
                label: _parse_array(
                    _string_array(values, key=_toml_key("labels", section, label))
                )
                for label, values in rules
            },
        )

    extra = AoT()
    for name, color, description in LABELS:
        entry = Table.section({
            "name": name,
            # labelmaker/repomatic expect the bare hex color, without leading '#'.
            "color": color.lstrip("#"),
            "description": description,
        })
        # Carry a renamed label's predecessor, so `sync-labels` migrates it in place
        # instead of stranding the issues filed against the old name.
        if renamed_from := LABEL_RENAMES.get(name):
            entry["rename-from"] = _parse_array(
                _string_array(renamed_from, key="rename-from")
            )
        extra.append(entry)
    labels["extra"] = extra

    return _sync_file(pyproject, tomlrt.dumps(doc), check=check)


def update_keywords(*, check: bool = False) -> bool:
    """Sync the `[project]` keywords of `pyproject.toml`.

    The keyword set merges three sources, so a new manager advertises itself on
    PyPI without a hand edit: the pool's manager IDs, each manager's own
    {attr}`~meta_package_manager.manager.PackageManager.keywords` aliases, and the
    curated {data}`KEYWORDS_EXTRAS` for terms belonging to no manager in
    particular. Same `tomlrt` round-trip as {func}`update_labels`.

    :param check: Report only, leaving `pyproject.toml` untouched.
    :return: `True` when the keywords are out of date.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlrt.loads(pyproject.read_text(encoding="UTF-8"))

    manager_keywords = {
        keyword for manager in pool.values() for keyword in manager.keywords
    }

    doc["project"]["keywords"] = _parse_array(
        _string_array(
            tuple(
                sorted(
                    set(KEYWORDS_EXTRAS) | set(pool.all_manager_ids) | manager_keywords,
                    key=str.casefold,
                ),
            ),
            multiline=True,
        )
    )

    return _sync_file(pyproject, tomlrt.dumps(doc), check=check)


def generate_metrics_subjects(forges: dict[str, str]) -> dict[str, str]:
    """Map each manager whose repository can be sampled to the URL to sample.

    A manager's `repository_url`, or its {data}`METRICS_MIRRORS` entry, when that
    URL's host is one the sampler reads: a {data}`SAMPLED_FORGES` host, or one of
    the self-hosted `forges` the configuration declares. A manager with no public
    repository, or one no API answers for, has no subject, and explains why in
    {data}`~meta_package_manager._docs.NO_UPSTREAM`.

    :param forges: The `[tool.repomatic.metrics] forges` table.
    """
    sampled = {*SAMPLED_FORGES, *forges}
    subjects = {}
    for manager_id, manager in pool.items():
        url = METRICS_MIRRORS.get(manager_id, manager.repository_url)
        if url and urlparse(url).netloc in sampled:
            subjects[manager_id] = url
    return subjects


def update_metrics_subjects(*, check: bool = False) -> bool:
    """Sync the manager entries of the `[tool.repomatic.metrics] subjects` table.

    The manager entries come from {func}`generate_metrics_subjects`; the others,
    naming projects that are not managers (`mpm` and its benchmarked peers), are
    kept as written. Same `tomlrt` round-trip as {func}`update_labels`, which keeps
    the one line per subject, sorted by name, that `pyproject-fmt` leaves alone.

    :param check: Report only, leaving `pyproject.toml` untouched.
    :return: `True` when the subjects are out of date.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlrt.loads(pyproject.read_text(encoding="UTF-8"))
    metrics = doc["tool"]["repomatic"]["metrics"]

    subjects = {
        name: url for name, url in metrics["subjects"].items() if name not in pool
    }
    subjects |= generate_metrics_subjects(metrics.get("forges", {}))
    _replace_entries(metrics["subjects"], dict(sorted(subjects.items())))

    return _sync_file(pyproject, tomlrt.dumps(doc), check=check)


def update_manager_stubs(*, check: bool = False) -> bool:
    """Sync the committed page stubs of `docs/managers/`.

    The directory is wholly owned by this function: one `<id>.md` stub per
    pool manager, nothing else. A stub is only rewritten when its content
    differs (keeping `update-docs` autofix diffs minimal), and stubs whose
    manager left the pool are deleted. `test_manager_stubs_in_sync` guards
    the contract.

    :param check: Report only, leaving `docs/managers/` untouched.
    :return: `True` when a stub is missing, stale or orphaned.
    """
    stub_dir = PROJECT_ROOT / "docs" / "managers"
    if not check:
        stub_dir.mkdir(parents=True, exist_ok=True)

    expected = {mid: manager_page_stub(mid) for mid in pool.all_manager_ids}

    stale = False
    for stub in stub_dir.glob("*.md"):
        if stub.stem not in expected:
            stale = True
            if not check:
                stub.unlink()

    for mid, content in expected.items():
        if _sync_file(stub_dir / f"{mid}.md", content, check=check):
            stale = True

    return stale


def main() -> int:
    """Regenerate every artifact, or report which ones are out of date.

    :return: Process exit code, non-zero under `--check` when anything drifted.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report out-of-date artifacts and exit non-zero without writing.",
    )
    args = parser.parse_args()

    # Keywords before labels: both rewrite `pyproject.toml`, and a real run
    # needs the second read to see what the first one wrote.
    updaters = {
        "pyproject.toml [project] keywords": update_keywords,
        "pyproject.toml [tool.repomatic.metrics] subjects": update_metrics_subjects,
        "pyproject.toml [tool.repomatic.labels] arrays": update_labels,
        "docs/managers/ page stubs": update_manager_stubs,
    }
    drifted = [name for name, updater in updaters.items() if updater(check=args.check)]

    if not args.check:
        return 0
    for name in drifted:
        print(f"Out of date: {name}")
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
