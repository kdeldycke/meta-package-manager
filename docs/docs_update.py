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
`pyproject.toml` (the `[project]` keywords, the label registry and the labeller
rules), the operation-matrix platform footnotes spliced into `readme.md`, and the
stub *file set* of `docs/managers/` (one `<id>.md` per pool manager, created and
deleted as managers join or leave the pool).

Everything that renders live at Sphinx build time -- the benchmark, augmentations
and per-manager tables, and the `<!-- matrix ... -->` compatibility blocks -- is
produced by the generators in {mod}`meta_package_manager._docs` and needs no
regeneration step here. The readme's Sankey diagram and operation matrix call
those same generators from `<!-- mirror-src -->` blocks, refreshed by
`click-extra refresh-directives` in the same `update-docs` job.
"""

from __future__ import annotations

import tomlkit

from meta_package_manager._docs import (
    PROJECT_ROOT,
    manager_page_stub,
    operation_matrix,
)
from meta_package_manager.labels import (
    LABELS,
    generate_content_rules,
    generate_file_rules,
)
from meta_package_manager.pool import pool

KEYWORDS_EXTRAS = (
    "alpine linux",
    "anaconda",
    "appimage",
    "atom",
    "chocolatey",
    "chromeos",
    "clear linux",
    "CLI",
    "cli-tools",
    "cyclonedx",
    "cygwin",
    "exherbo",
    "github cli",
    "gnome",
    "gnome-shell",
    "gnome-shell-extension",
    "gnu guix",
    "homebrew",
    "mac app store",
    "macos",
    "mageia",
    "meta-package-manager",
    "netbsd",
    "nixpkgs",
    "node",
    "openbsd",
    "package",
    "package manager",
    "package url",
    "package-manager-cli",
    "packagekit",
    "paludis",
    "php composer",
    "pkgsrc",
    "plugin",
    "portage",
    "powershell",
    "powershell-gallery",
    "psresourceget",
    "purl",
    "pwsh",
    "ruby",
    "ruby-gem",
    "rust",
    "sbom",
    "slackware",
    "slitaz",
    "solaris",
    "source mage",
    "spdx",
    "svr4",
    "swiftbar",
    "swiftbar-plugin",
    "tex live",
    "visual studio code",
    "void linux",
    "xbar",
    "xbar-plugin",
    "zb",
)
"""Curated PyPI keywords beyond the manager IDs themselves.

Ecosystem names, platform names and generic discovery terms. The manager IDs come
for free from the pool: {func}`update_keywords` merges both sets into
`pyproject.toml`. When a new manager brings a well-known ecosystem name that
differs from its ID (like `gh-ext` and `github cli`), add the alias here.
"""


def _string_array(values: tuple[str, ...], multiline: bool = False):
    """Render strings as a `tomlkit` array, one item per line when asked or long.

    Both layouts replicate `pyproject-fmt`'s canonical style: inline arrays
    are padded with spaces inside the brackets, exploded arrays get a 2-space
    indent (`tomlkit`'s own `multiline()` hard-codes 4) and a trailing
    comma. Any deviation is churn: the `format-pyproject` autofix job would
    endlessly rewrite what the `update-docs` job regenerates.
    `test_pyproject_updates_are_pyproject_fmt_fixpoint` guards the match.
    """
    items = [tomlkit.item(value).as_string() for value in values]
    inline = f"[ {', '.join(items)} ]"
    # 78 preserves the historical 76-character budget of the unpadded form.
    if not multiline and len(inline) <= 78:
        return tomlkit.array(inline)
    body = "".join(f"  {item},\n" for item in items)
    return tomlkit.array(f"[\n{body}]")


def _rules_aot(rules: list[tuple[str, tuple[str, ...]]], field: str):
    """Render labeller rules as a `tomlkit` array-of-tables.

    Each rule becomes a ``{label, <field>}`` table. The pattern array switches to
    one-item-per-line when its inline form would run long.
    """
    aot = tomlkit.aot()
    for label, values in rules:
        entry = tomlkit.table()
        entry["label"] = label
        entry[field] = _string_array(values)
        aot.append(entry)
    return aot


def update_labels() -> None:
    """Sync the label registry and labeller rules into `pyproject.toml`.

    Regenerates the three `[tool.repomatic.labels.*]` arrays from
    {mod}`meta_package_manager.labels`: `extra` (from
    {data}`~meta_package_manager.labels.LABELS`), `content-rules` and
    `file-rules` (from the pool-derived rule generators). repomatic's
    `sync-labels` and labeller jobs read these inline definitions at run time.

    ```{note}
    The edit is done with `tomlkit` round-trip so the rest of
    `pyproject.toml` (comments, key order, formatting) is preserved: only
    the three label arrays are regenerated. The per-entry layout matches what
    `pyproject-fmt` emits, so the result survives the autofix formatting
    pass without churn.
    ```
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="UTF-8"))
    labels_table = doc["tool"]["repomatic"]["labels"]

    extra = tomlkit.aot()
    for name, color, description in LABELS:
        entry = tomlkit.table()
        entry["name"] = name
        # labelmaker/repomatic expect the bare hex color, without leading '#'.
        entry["color"] = color.lstrip("#")
        entry["description"] = description
        extra.append(entry)

    arrays = {
        "content-rules": _rules_aot(generate_content_rules(), "patterns"),
        "extra": extra,
        "file-rules": _rules_aot(generate_file_rules(), "any-glob-to-any-file"),
    }
    for key, aot in arrays.items():
        labels_table[key] = aot
        # Separate the last entry from the following table with one blank line.
        last_field = list(aot[-1].keys())[-1]
        aot[-1][last_field].trivia.trail = "\n\n"

    content = tomlkit.dumps(doc)
    for key in arrays:
        # tomlkit prefixes each inserted array-of-tables with two blank lines;
        # collapse the section's leading separator to a single blank line.
        content = content.replace(
            f"\n\n\n[[tool.repomatic.labels.{key}]]",
            f"\n\n[[tool.repomatic.labels.{key}]]",
            1,
        )
    pyproject.write_text(content, encoding="UTF-8")


def update_keywords() -> None:
    """Sync the `[project]` keywords of `pyproject.toml`.

    The keyword set is the pool's manager IDs merged with the curated
    {data}`KEYWORDS_EXTRAS`, so a new manager advertises itself on PyPI without
    a hand edit. Same `tomlkit` round-trip as {func}`update_labels`.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="UTF-8"))

    doc["project"]["keywords"] = _string_array(
        tuple(
            sorted(set(KEYWORDS_EXTRAS) | set(pool.all_manager_ids), key=str.casefold),
        ),
        multiline=True,
    )

    pyproject.write_text(tomlkit.dumps(doc), encoding="UTF-8")


def update_readme_footnotes() -> None:
    """Splice the operation-matrix platform footnotes into `readme.md`.

    The manager Sankey diagram and the operation matrix are `<!-- mirror-src -->`
    blocks refreshed by `click-extra refresh-directives`, so this owns only the
    footnote definitions, which cannot use that mechanism: `mdformat-footnote`
    strips an HTML comment placed on its own line after a footnote definition
    (https://github.com/executablebooks/mdformat-footnote/issues/11), so the
    closing marker is wedged against the tail of the last footnote (no leading
    newline) and the region is spliced by hand.
    """
    readme = PROJECT_ROOT / "readme.md"
    _, footnotes = operation_matrix()

    start_tag = "<!-- operation-footnotes-start -->\n\n"
    end_tag = "<!-- operation-footnotes-end -->\n"
    orig_content = readme.read_text(encoding="UTF-8")
    pre_content, rest = orig_content.split(start_tag, 1)
    _, post_content = rest.split(end_tag, 1)
    readme.write_text(
        f"{pre_content}{start_tag}{footnotes}{end_tag}{post_content}",
        encoding="UTF-8",
    )


def update_manager_stubs() -> None:
    """Sync the committed page stubs of `docs/managers/`.

    The directory is wholly owned by this function: one `<id>.md` stub per
    pool manager, nothing else. A stub is only rewritten when its content
    differs (keeping `update-docs` autofix diffs minimal), and stubs whose
    manager left the pool are deleted. `test_manager_stubs_in_sync` guards
    the contract.
    """
    stub_dir = PROJECT_ROOT / "docs" / "managers"
    stub_dir.mkdir(parents=True, exist_ok=True)

    expected = {mid: manager_page_stub(mid) for mid in pool.all_manager_ids}

    for stub in stub_dir.glob("*.md"):
        if stub.stem not in expected:
            stub.unlink()

    for mid, content in expected.items():
        stub = stub_dir / f"{mid}.md"
        if not stub.exists() or stub.read_text(encoding="UTF-8") != content:
            stub.write_text(content, encoding="UTF-8")


if __name__ == "__main__":
    update_keywords()
    update_labels()
    update_manager_stubs()
    update_readme_footnotes()
