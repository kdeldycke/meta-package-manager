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

`--check` reports which artifacts are out of date and exits non-zero without
touching the tree, so `repomatic update-docs --check` can detect drift in CI.
repomatic forwards the flag to this script; a script that silently ignored it
would keep writing and report a clean tree.
"""

from __future__ import annotations

import argparse
import sys

import tomlkit

from meta_package_manager._docs import (
    PROJECT_ROOT,
    manager_page_stub,
    operation_matrix,
)
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
    "conda-forge",
    "cyclonedx",
    "cygwin",
    "exherbo",
    "github cli",
    "gnome",
    "gnome-shell",
    "gnome-shell-extension",
    "gnu guix",
    "homebrew",
    "hyprland",
    "lazy.nvim",
    "mac app store",
    "macos",
    "mageia",
    "meta-package-manager",
    "neovim",
    "nerd fonts",
    "netbsd",
    "nim",
    "nixpkgs",
    "node",
    "nuget",
    "openbsd",
    "package",
    "package manager",
    "package url",
    "package-manager-cli",
    "packagekit",
    "paludis",
    "php composer",
    "pkg5",
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
    "zsh",
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
    The edit is done with `tomlkit` round-trip so the rest of
    `pyproject.toml` (comments, key order, formatting) is preserved: only
    the three label arrays are regenerated. The per-entry layout matches what
    `pyproject-fmt` emits, so the result survives the autofix formatting
    pass without churn.
    ```

    :param check: Report only, leaving `pyproject.toml` untouched.
    :return: `True` when the label arrays are out of date.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="UTF-8"))
    repomatic_table = doc["tool"]["repomatic"]

    extra = tomlkit.aot()
    for name, color, description in LABELS:
        entry = tomlkit.table()
        entry["name"] = name
        # labelmaker/repomatic expect the bare hex color, without leading '#'.
        entry["color"] = color.lstrip("#")
        entry["description"] = description
        # Carry a renamed label's predecessor, so `sync-labels` migrates it in place
        # instead of stranding the issues filed against the old name.
        if renamed_from := LABEL_RENAMES.get(name):
            entry["rename-from"] = _string_array(renamed_from)
        extra.append(entry)

    # The whole `labels` sub-tree is dropped and rebuilt, rather than assigned
    # over in place: replacing an array-of-tables with a table leaves `tomlkit`'s
    # internal table map holding indices into the section it just removed, and
    # the next assignment to the same container dies on an out-of-range lookup.
    del repomatic_table["labels"]

    # The rule sets go in as dotted keys on `[tool.repomatic]`, which is what
    # `pyproject-fmt` canonicalizes a table of scalars to, and what the rest of
    # this section already reads like (`workflow.paths`, `manpages.script`).
    # `extra` stays an array-of-tables, having no dotted-key form, and therefore
    # has to be written last: TOML closes a table the moment a sub-table header
    # opens, so a dotted key emitted after it would land inside `extra`.
    for section, rules in (
        ("content-rules", generate_content_rules()),
        ("file-rules", generate_file_rules()),
    ):
        for label, values in rules:
            key = tomlkit.key(["labels", section, label])
            repomatic_table[key] = _string_array(values)

    # `append()` rather than item assignment on both lines: assigning a super
    # table over a key the dotted keys above just created discards them and
    # re-roots the array-of-tables at the document top level, as `[[labels.extra]]`.
    labels_table = tomlkit.table(is_super_table=True)
    labels_table.append("extra", extra)
    repomatic_table.append("labels", labels_table)

    # Separate the last `extra` entry from the following table with one blank line.
    last_field = list(extra[-1].keys())[-1]
    extra[-1][last_field].trivia.trail = "\n\n"

    content = tomlkit.dumps(doc)
    # tomlkit prefixes the inserted array-of-tables with two blank lines; collapse
    # the section's leading separator to a single blank line.
    header = "[[tool.repomatic.labels.extra]]"
    content = content.replace(f"\n\n\n{header}", f"\n\n{header}", 1)
    return _sync_file(pyproject, content, check=check)


def update_keywords(*, check: bool = False) -> bool:
    """Sync the `[project]` keywords of `pyproject.toml`.

    The keyword set is the pool's manager IDs merged with the curated
    {data}`KEYWORDS_EXTRAS`, so a new manager advertises itself on PyPI without
    a hand edit. Same `tomlkit` round-trip as {func}`update_labels`.

    :param check: Report only, leaving `pyproject.toml` untouched.
    :return: `True` when the keywords are out of date.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="UTF-8"))

    doc["project"]["keywords"] = _string_array(
        tuple(
            sorted(set(KEYWORDS_EXTRAS) | set(pool.all_manager_ids), key=str.casefold),
        ),
        multiline=True,
    )

    return _sync_file(pyproject, tomlkit.dumps(doc), check=check)


def update_readme_footnotes(*, check: bool = False) -> bool:
    """Splice the operation-matrix platform footnotes into `readme.md`.

    The manager Sankey diagram and the operation matrix are `<!-- mirror-src -->`
    blocks refreshed by `click-extra refresh-directives`, so this owns only the
    footnote definitions, which cannot use that mechanism: `mdformat-footnote`
    strips an HTML comment placed on its own line after a footnote definition
    (https://github.com/executablebooks/mdformat-footnote/issues/11), so the
    closing marker is wedged against the tail of the last footnote (no leading
    newline) and the region is spliced by hand.

    :param check: Report only, leaving `readme.md` untouched.
    :return: `True` when the footnotes are out of date.
    """
    readme = PROJECT_ROOT / "readme.md"
    _, footnotes = operation_matrix()

    start_tag = "<!-- operation-footnotes-start -->\n\n"
    end_tag = "<!-- operation-footnotes-end -->\n"
    orig_content = readme.read_text(encoding="UTF-8")
    pre_content, rest = orig_content.split(start_tag, 1)
    _, post_content = rest.split(end_tag, 1)
    return _sync_file(
        readme,
        f"{pre_content}{start_tag}{footnotes}{end_tag}{post_content}",
        check=check,
    )


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
        "pyproject.toml [tool.repomatic.labels] arrays": update_labels,
        "docs/managers/ page stubs": update_manager_stubs,
        "readme.md operation-matrix footnotes": update_readme_footnotes,
    }
    drifted = [name for name, updater in updaters.items() if updater(check=args.check)]

    if not args.check:
        return 0
    for name in drifted:
        print(f"Out of date: {name}")
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
