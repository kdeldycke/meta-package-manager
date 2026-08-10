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

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
from itertools import permutations
from pathlib import Path

import pytest
from extra_platforms import Group, extract_members
from yaml import Loader, load, safe_load

from meta_package_manager import _docs
from meta_package_manager.capabilities import Operations
from meta_package_manager.docstring_corpus import literal_blocks
from meta_package_manager.labels import (
    LABELS,
    MANAGER_LABEL_COLOR,
    MANAGER_LABELS,
    MANAGER_PREFIX,
    PLATFORM_PREFIX,
    generate_content_rules,
    generate_file_rules,
)
from meta_package_manager.platforms import MAIN_PLATFORMS
from meta_package_manager.pool import pool

from .conftest import PROJECT_ROOT, all_managers, tomllib


def _load_docs_update():
    """Load `docs/docs_update.py` as a module without requiring `docs` to
    be a package.

    The script lives next to the docs but is not part of any importable
    package, so we resolve it by file path.
    """
    spec = importlib.util.spec_from_file_location(
        "docs_update",
        Path(__file__).parent.parent / "docs" / "docs_update.py",
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


docs_update = _load_docs_update()


""" Test all non-code artifacts depending on manager definitions.

Covers:
    * Documentation (sphinx, readme, etc.)
    * CI/CD scripts
    * GitHub project config

These tests are mainly there to remind us keep extra stuff in sync on new
platform or manager addition.
"""


def test_unique_local_group_ids():
    """Check our platform groups have unique identifiers."""
    group_ids = [p.id for p in MAIN_PLATFORMS]
    assert len(group_ids) == len(set(group_ids))


def test_local_groups_no_overlap():
    """Check our platform groups are mutually exclusive."""
    for a, b in permutations(MAIN_PLATFORMS, 2):
        if isinstance(a, Group):
            assert a.isdisjoint(b)


@all_managers
def test_all_platforms_covered_by_local_groups(manager):
    """Check all platforms supported by managers are covered by a local group."""
    leftover_platforms = set(manager.platforms.copy())

    for main_platform in (set(extract_members(i)) for i in MAIN_PLATFORMS):
        leftover_platforms -= main_platform

    assert len(leftover_platforms) == 0
    # At this stage we know all platforms of the manager can be partitioned by a
    # combination of MAIN_PLATFORMS elements, without any overlap or leftover.


def test_project_metadata():
    # Fetch general information about the project from pyproject.toml.
    toml_path = PROJECT_ROOT.joinpath("pyproject.toml").resolve()
    toml_config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    # Check all managers are referenced in Python package keywords.
    assert set(pool.all_manager_ids).issubset(toml_config["project"]["keywords"])


def test_changelog():
    content = PROJECT_ROOT.joinpath("changelog.md").read_text(encoding="utf-8")
    assert content.startswith("# Changelog\n")

    entry_pattern = re.compile(
        r"^- (?:\*\*[A-Za-z]+:\*\* )?\[(?P<category>[a-z0-9,\-]+)\] (?P<entry>.+)"
    )

    allowed_categories = {
        *pool.all_manager_ids,
        *(p.id for p in MAIN_PLATFORMS),
        "mpm",
        "bar-plugin",
        "gnome-shell",
    }

    for line in content.splitlines():
        if line.startswith("-"):
            match = entry_pattern.match(line)
            assert match
            entry = match.groupdict()
            assert entry["category"]
            categories = entry["category"].split(",")
            assert len(categories)
            assert len(categories) == len(set(categories))
            assert categories == sorted(categories)
            assert set(categories).issubset(allowed_categories)


def test_labels():
    for name, color, description in LABELS:
        assert name
        assert color
        assert color.startswith("#")
        assert len(description) <= 100


@pytest.mark.repo_maintenance
def test_new_package_manager_issue_template():
    """Check all platforms groups are referenced in the issue template.

    Repo-maintenance guard: the reference set is regenerated from the installed
    `extra_platforms` release, whose platform groups a downstream packager
    cannot be expected to match, so `conftest` skips it outside a git
    checkout. It also reads `.github/`, absent from a wheel install.
    """
    content = PROJECT_ROOT.joinpath(
        ".github/ISSUE_TEMPLATE/new-package-manager.yml",
    ).read_text(encoding="utf-8")
    assert content

    template_platforms = load(content, Loader=Loader)["body"][3]["attributes"][
        "options"
    ]

    reference_labels = []
    for p_obj in MAIN_PLATFORMS:
        label = f"{p_obj.icon} {p_obj.name}"
        if isinstance(p_obj, Group) and len(p_obj) > 1:
            members = p_obj.members.values()  # type: ignore[attr-defined]
            label += f" ({', '.join(p.name for p in members)})"
        reference_labels.append({"label": label})

    assert template_platforms == reference_labels


def test_extra_labels_in_pyproject():
    """Check the generated `[tool.repomatic.labels.extra]` block in
    `pyproject.toml` is consistent with the `LABELS` registry."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    extra_labels = data["tool"]["repomatic"]["labels"]["extra"]
    assert extra_labels

    names = [lbl["name"] for lbl in extra_labels]
    # Labels are unique.
    assert len(names) == len(set(names))
    canonical_labels = set(names)

    # Contains both manager and platform labels.
    canonical_managers = {
        lbl
        for lbl in canonical_labels
        if lbl.startswith(MANAGER_PREFIX) and "mpm" not in lbl
    }
    assert canonical_managers
    canonical_platforms = {
        lbl for lbl in canonical_labels if lbl.startswith(PLATFORM_PREFIX)
    }
    assert canonical_platforms

    # The block matches the in-memory LABELS registry. Colors are stored
    # without the leading '#', following the labelmaker/repomatic convention.
    registry = {(name, color.lstrip("#"), desc) for name, color, desc in LABELS}
    generated = {
        (lbl["name"], lbl["color"], lbl["description"]) for lbl in extra_labels
    }
    assert generated == registry


def test_label_rules_reference_known_labels():
    """Every file- and content-rule must target a label that exists in the
    generated `[tool.repomatic.labels.extra]` block.

    A rule naming an unknown label silently applies a label the repository does not
    have: the stale `dnf-based` rules left behind when the `labels.py` group was
    renamed `rpm-based`, or per-manager rules (`zypper`, `pacstall`) outliving
    the manager's absorption into an ecosystem group.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    labels_config = data["tool"]["repomatic"]["labels"]
    known = {label["name"] for label in labels_config["extra"]}
    for section in ("content-rules", "file-rules"):
        stale = [
            rule["label"]
            for rule in labels_config[section]
            if rule["label"] not in known
        ]
        assert not stale, f"{section} reference unknown labels: {stale}"


def test_label_rules_in_pyproject():
    """Check the generated `[tool.repomatic.labels.*]` rule blocks in
    `pyproject.toml` match a fresh generation from the pool.

    Drift means a manager was added without running `docs/docs_update.py`
    (repomatic's `update-docs` job self-heals this on the next push).
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    labels_config = data["tool"]["repomatic"]["labels"]

    checked_in_content = [
        (rule["label"], tuple(rule["patterns"]))
        for rule in labels_config["content-rules"]
    ]
    assert checked_in_content == generate_content_rules()

    checked_in_file = [
        (rule["label"], tuple(rule["any-glob-to-any-file"]))
        for rule in labels_config["file-rules"]
    ]
    assert checked_in_file == generate_file_rules()


def test_pyproject_updates_are_pyproject_fmt_fixpoint(monkeypatch, tmp_path):
    """The `pyproject.toml` writers must emit `pyproject-fmt`-canonical style.

    Any deviation makes the `update-docs` and `format-pyproject` autofix
    jobs endlessly rewrite each other's output. The committed file is
    canonicalized first, so the assertion only judges the writers' own output,
    whatever formatting state the working tree is in.
    """
    pyproject_fmt = pytest.importorskip(
        "pyproject_fmt",
        reason="pyproject-fmt is optional; hermetic builds run without it",
    )
    scratch = tmp_path / "pyproject.toml"
    shutil.copyfile(PROJECT_ROOT / "pyproject.toml", scratch)
    pyproject_fmt.run([str(scratch)])

    monkeypatch.setattr(docs_update, "PROJECT_ROOT", tmp_path)
    docs_update.update_labels()
    docs_update.update_keywords()

    assert pyproject_fmt.run(["--check", str(scratch)]) == 0


def test_benchmark_yaml_well_formed():
    """Check `docs/benchmark.yaml` only encodes flags from the known
    competitor set and homepage URLs for non-pool managers."""
    yaml_path = PROJECT_ROOT / "docs" / "benchmark.yaml"
    data = safe_load(yaml_path.read_text(encoding="utf-8"))
    assert set(data) == {"managers", "homepages", "coarse_support", "refused"}

    competitors = set(_docs.BENCHMARK_COMPETITORS)
    for mid, flags in data["managers"].items():
        assert mid == mid.lower()
        assert isinstance(flags, list)
        # Flags are valid competitor names, unique, and sorted in column order.
        assert set(flags).issubset(competitors)
        assert len(flags) == len(set(flags))
        assert flags == sorted(flags, key=_docs.BENCHMARK_COMPETITORS.index)

    # Homepages mapping: lowercase IDs pointing to HTTPS URLs, sorted
    # alphabetically.
    homepages = data["homepages"]
    assert list(homepages) == sorted(homepages), (
        "homepages keys must be sorted alphabetically"
    )
    for mid, url in homepages.items():
        assert mid == mid.lower()
        assert isinstance(url, str)
        assert url.startswith(("http://", "https://"))

    # coarse_support: mapping ``{manager_id: {competitor: url}}``. Every
    # listed (mid, competitor) pair must also exist in managers (you cannot
    # be coarse-only-supported without being supported at all).
    coarse = data["coarse_support"]
    assert list(coarse) == sorted(coarse), (
        "coarse_support keys must be sorted alphabetically"
    )
    for mid, entries in coarse.items():
        assert mid == mid.lower()
        assert isinstance(entries, dict)
        assert entries, f"{mid!r} has an empty coarse_support mapping; omit the row"
        assert list(entries) == sorted(entries), (
            f"coarse_support[{mid!r}] competitor keys must be sorted alphabetically"
        )
        assert set(entries).issubset(competitors)
        # No-orphan invariant: the manager must be supported in the first place.
        assert mid in data["managers"], (
            f"coarse_support[{mid!r}] has no matching entry in managers"
        )
        missing = set(entries) - set(data["managers"][mid])
        assert not missing, (
            f"coarse_support[{mid!r}] flags competitors {sorted(missing)} that "
            f"are not in managers[{mid!r}]"
        )
        for competitor, url in entries.items():
            assert isinstance(url, str)
            assert url.startswith(("http://", "https://")), (
                f"coarse_support[{mid!r}][{competitor!r}] URL must be an http(s) link"
            )

    # refused: mapping ``{manager_id: {competitor: evidence_url}}``. Each
    # (manager_id, competitor) pair must NOT overlap with managers[mid]:
    # a competitor cannot both support and refuse the same manager.
    refused = data["refused"]
    assert list(refused) == sorted(refused), (
        "refused keys must be sorted alphabetically"
    )
    for mid, entries in refused.items():
        assert mid == mid.lower()
        assert isinstance(entries, dict)
        assert entries, f"{mid!r} has an empty refused mapping; omit the row"
        assert list(entries) == sorted(entries), (
            f"refused[{mid!r}] competitor keys must be sorted alphabetically"
        )
        assert set(entries).issubset(competitors)
        # No-conflict invariant: a competitor cannot be listed in both
        # managers (supports) and refused (declined) for the same mid.
        supports = set(data["managers"].get(mid, []))
        conflict = supports & set(entries)
        assert not conflict, (
            f"refused[{mid!r}] lists competitors {sorted(conflict)} that also "
            f"support the manager in managers[{mid!r}]"
        )
        for competitor, url in entries.items():
            assert isinstance(url, str)
            assert url.startswith(("http://", "https://")), (
                f"refused[{mid!r}][{competitor!r}] URL must be an http(s) link"
            )


def test_benchmark_homepages_cover_non_pool_managers():
    """Every non-pool manager listed in `benchmark.yaml` must have a
    matching `homepages` entry so the table can link the identifier.

    Pool-implemented managers are excluded: their URL is sourced from the
    class's `homepage_url` attribute, and a redundant entry in the YAML
    would create two sources of truth.
    """
    yaml_path = PROJECT_ROOT / "docs" / "benchmark.yaml"
    data = safe_load(yaml_path.read_text(encoding="utf-8"))

    pool_ids = set(pool.all_manager_ids)
    yaml_ids = set(data["managers"])
    homepage_ids = set(data["homepages"])

    # Every non-pool YAML manager must have a homepage URL.
    missing = (yaml_ids - pool_ids) - homepage_ids
    assert not missing, f"Missing homepage URLs in benchmark.yaml: {sorted(missing)}"

    # Homepages must not duplicate pool managers (those come from the class).
    overlap = homepage_ids & pool_ids
    assert not overlap, f"Pool managers must not appear in homepages: {sorted(overlap)}"

    # Homepages must not include unknown manager IDs.
    extra = homepage_ids - yaml_ids
    assert not extra, f"Unknown manager IDs in homepages: {sorted(extra)}"


@all_managers
def test_manager_homepage_url(manager):
    """Every pool manager defines a non-empty homepage URL.

    Sourced by the benchmark table generator to link each manager identifier
    to its upstream documentation. An empty or malformed URL breaks the
    rendered table.
    """
    assert manager.homepage_url
    assert isinstance(manager.homepage_url, str)
    assert manager.homepage_url.startswith(("http://", "https://"))


def test_benchmark_table_renders():
    """Check the `Package manager support` table generator still produces a
    well-formed table from the current pool and YAML.

    The table is rendered live at Sphinx build time by the ``{python:render}``
    block in `docs/benchmark.md`, so there is no checked-in copy to compare
    against: this test only guards the generator against crashes and structural
    regressions (a broken YAML entry, a manager without a source file).
    """
    table = _docs.benchmark_managers_table()
    lines = table.splitlines()
    assert len(lines) > 2
    header = lines[0]
    assert header.startswith("| Manager")
    assert "`mpm`" in header
    for competitor in _docs.BENCHMARK_COMPETITORS:
        assert f"`{competitor}`" in header
    # Every pool manager must land one row backed by a source link, its
    # identifier linking to its dedicated documentation page.
    assert sum(line.count("[✅](") for line in lines) == len(pool)
    assert sum(line.count("](managers/") for line in lines) == len(pool)


def test_binaries_download_table_renders():
    """Check the latest-release binaries table generator still produces a
    well-formed table from the binaries catalog.

    The table is rendered live at Sphinx build time by the ``{python:render}``
    block in `docs/install.md`, so there is no checked-in copy to compare
    against: this test only guards the generator against crashes and drift in
    the `docs/assets/binaries.csv` cell markup it parses.
    """
    table = _docs.binaries_download_table()
    lines = table.splitlines()
    assert len(lines) == 5
    assert lines[0].startswith("| Platform")
    for os_label in ("Linux", "macOS", "Windows"):
        assert any(f"**{os_label}**" in line for line in lines)
    # The release pipeline builds one binary per OS/arch pair: every cell
    # must carry a versioned download link.
    assert sum(line.count("releases/download/") for line in lines) == 6
    assert "latest/download" not in table


def test_augmentations_table_renders():
    """Check the augmentations table generator still produces a well-formed
    table from the current pool.

    The table is rendered live at Sphinx build time by the ``{python:render}``
    block in `docs/augmentations.md`, so there is no checked-in copy to compare
    against: this test only guards the generator against crashes and structural
    regressions.
    """
    table = _docs.augmentations_table()
    lines = table.splitlines()
    assert len(lines) > 2
    assert lines[0].startswith("| Manager")
    rows = lines[2:]
    # Only managers gaining at least one backfilled capability are listed.
    assert 0 < len(rows) < len(pool)
    assert all(line.count("✅") >= 1 for line in rows)
    # The one-by-one upgrade fallback backfills pip, the canonical example
    # narrated in the page's prose. Its identifier links to its documentation
    # page.
    assert any(
        line.startswith("| [`pip`](managers/pip.md) ") and "✅" in line for line in rows
    )


def test_manager_logo_assets():
    """Check every vendored brand mark is normalized, safe and accounted for.

    The SVGs are inlined verbatim into the built pages, so this is what keeps a
    hand edit (or a compromised upstream) from smuggling a script or a remote
    reference into the documentation. `docs/logos_update.py` produces
    this shape; the directory holds nothing else.
    """
    manifest = _docs.logo_manifest()
    assert set(manifest) == {"icons", "upstream"}
    assert list(manifest["icons"]) == sorted(manifest["icons"])

    assets = {path.stem for path in _docs.LOGO_DIR.glob("*.svg")}
    assert assets == set(manifest["icons"]), "manifest and assets drifted apart"

    for slug, icon in manifest["icons"].items():
        assert set(icon) == {
            "contrast_on_light",
            "hex",
            "license",
            "managers",
            "source",
            "title",
        }
        assert icon["managers"] == sorted(icon["managers"])
        assert re.fullmatch(r"[0-9A-F]{6}", icon["hex"])
        assert icon["source"].startswith("https://")

        svg = (_docs.LOGO_DIR / f"{slug}.svg").read_text(encoding="utf-8")
        # One line, so the raw HTML block survives its injection into MyST: a
        # blank line would end the block and leak markup into the page.
        assert svg.count("\n") == 1
        assert svg.endswith("\n")
        assert svg.startswith('<svg viewBox="0 0 24 24">')
        assert f"<title>{icon['title']}</title>" in svg
        # No hard-coded color, so the mark inherits the theme's currentColor.
        assert 'fill="' not in svg
        assert not re.search(r"<(script|image|foreignObject)\b|xlink:href|url\(", svg)


def test_manager_logos_resolve():
    """Check the `logo` slug of every manager points at a vendored mark.

    Also enforces the reverse: a mark nobody claims is dead weight, mirroring
    the orphan sweep `update_manager_stubs` performs on `docs/managers/`.
    """
    icons = _docs.logo_manifest()["icons"]
    claimed: dict[str, list[str]] = {}
    for mid, manager in pool.items():
        if manager.logo:
            assert manager.logo in icons, f"{mid} declares an unvendored logo"
            claimed.setdefault(manager.logo, []).append(mid)

    assert claimed, "no manager declares a logo anymore"
    for slug, icon in icons.items():
        assert icon["managers"] == sorted(claimed.get(slug, [])), (
            f"the {slug} mark is credited to the wrong managers"
        )


@all_managers
def test_manager_logo_renders(manager):
    """Check the brand mark of each manager renders as inlinable raw HTML."""
    mark = _docs.manager_logo(manager.id)
    if not manager.logo:
        assert mark == ""
        # A manager with no mark keeps the page's default package glyph.
        assert "manager-logo" not in _docs.manager_intro(manager.id)
        return

    assert mark.startswith('<div class="manager-logo"')
    assert mark.endswith("</div>")
    assert "\n" not in mark
    assert mark in _docs.manager_intro(manager.id)

    # The brand color always rides on a custom property: WCAG exempts logotypes
    # from contrast requirements, so a pale mark keeps its own color rather than
    # being repainted a flat black.
    icon = _docs.logo_manifest()["icons"][manager.logo]
    assert f"--manager-logo-color: #{icon['hex']}" in mark

    # The index table embeds the small variant, as a span: a table cell wraps
    # its content in a paragraph, where a <div> would be invalid markup.
    assert _docs.manager_logo(manager.id, inline=True).startswith(
        '<span class="manager-logo manager-logo-inline"'
    )


@all_managers
def test_manager_card_renders(manager):
    """Check each manager's infobox carries its facts, and its mark when it has one."""
    card = _docs.manager_card(manager.id)
    assert card.startswith("```{card}\n:class-card: manager-card")
    assert card.endswith("```")
    assert card in _docs.manager_intro(manager.id)

    # Every fact is a definition-list row, so it reads as a labelled entry.
    for label in ("ID", "Home page", "Issues and PRs", "Source", "Platforms"):
        assert f"**{label}**\n: " in card
    # The former Platforms and Ecosystem sections now live here.
    assert "**purl types**\n: `pkg:" in card
    assert ("**Brewfile entry**" in card) is bool(manager.brewfile_entry_type)

    # The tracker link and the source file close the box, in that order: a
    # reader after either has read everything else first. Managers sharing an
    # ecosystem share one label, hence one search.
    label_name = MANAGER_LABELS[manager.id]
    assert label_name.startswith(MANAGER_PREFIX)
    url = _docs.manager_label_url(manager.id)
    badge = f"{{bdg-link-secondary}}`{label_name} <{url}>`"
    assert f"**Issues and PRs**\n: {badge}\n\n**Source**\n: " in card
    assert "**" not in card.partition("**Source**\n: ")[2]

    # Only the ASCII specials are escaped, the way GitHub's own label links are.
    quoted = label_name.replace(" ", "%20").replace(":", "%3A")
    assert url == f"{_docs.GITHUB_ISSUES_URL}?q=label%3A%22{quoted}%22"

    # How mpm invokes the tool, the whole of what used to be a section of its own.
    cli_row = "CLI names (lookup order)" if len(manager.cli_names) > 1 else "CLI name"
    assert f"**{cli_row}**\n: " in card
    for name in manager.cli_names:
        assert f"`{name}`" in card
    assert ("**Extra search paths**" in card) is bool(manager.cli_search_path)
    assert ("**Forced environment**" in card) is bool(manager.extra_env)
    # A single row states arguments forced before the command, after it, or
    # both, as the shape of every invocation.
    forced = card.partition("**Every call**\n: ")[2].partition("\n")[0]
    assert bool(forced) is bool(manager.pre_args or manager.post_args)
    if forced:
        argv = " ".join((
            manager.cli_names[0],
            *manager.pre_args,
            "<command>",
            *manager.post_args,
        ))
        assert forced == f"`{argv}`"

    # No path leaks the home directory of whoever built the docs.
    assert str(Path.home()) not in card

    # The glue holding a separator to the value before it, and an icon to its
    # label, is a non-breaking space. It survives no formatter that mistakes it
    # for whitespace, so assert it rather than trust it.
    assert _docs.FACT_SEPARATOR.startswith("\u00a0")
    platforms = _docs.manager_platforms(manager.id)
    assert "\u00a0" in platforms or not platforms

    # Every repeated value in the box reads through the same separator. A
    # coverage annotation carries commas of its own (`Mageia, Mandriva Linux
    # only`), so only what sits between entries is checked.
    for row in ("Platforms", "Operations", "purl types"):
        value = card.partition(f"**{row}**\n: ")[2].partition("\n")[0]
        assert ", " not in re.sub(r"\([^)]*\)", "", value), (
            f"{row} must not fall back to commas"
        )
    assert f": `{manager.id}`" in card
    assert manager.homepage_url in card
    if manager.requirement:
        # Unstyled like the readme matrix's own Version column, with both angle
        # brackets escaped: a leading `>` would otherwise open a blockquote and
        # swallow itself, and a `<` would open a tag.
        requirement = (
            _docs
            ._format_requirement(manager.requirement)
            .replace("<", r"\<")
            .replace(">", r"\>")
        )
        assert f"**Version requirement**\n: {requirement}" in card
        assert "\n: >" not in card
        # Spaced out for reading, the same way the readme matrix renders it: no
        # comparison operator stays glued to the version it applies to.
        assert not re.search(r"[<>=!~]\d", requirement)
        assert f": `{manager.requirement}`" not in card
    assert ("**Cooldown**\n: ✓" in card) is bool(manager.supports_cooldown)

    # The mark rides in the card header, above the `^^^` separator.
    header, _, body = card.partition("^^^")
    assert ("manager-logo" in header) is bool(manager.logo)
    assert "manager-logo" not in body


def test_manager_label_badge_color():
    """Check the stylesheet paints the label badge the color GitHub gives it.

    A stylesheet cannot read `labels.py`, so the hex is written twice: here is
    where the copy is caught drifting from
    {data}`~meta_package_manager.labels.MANAGER_LABEL_COLOR`.
    """
    css = (PROJECT_ROOT / "docs" / "_static" / "custom.css").read_text(
        encoding="utf-8",
    )
    rule = css.partition(".manager-card a.sd-badge {")[2].partition("}")[0]
    assert rule.count(MANAGER_LABEL_COLOR) == 2, "background and border color"


def test_manager_logo_credits_renders():
    """Check every vendored mark is credited with its license and source.

    Twelve marks carry an attribution-bearing license, so a missing row is a
    license violation rather than a cosmetic gap.
    """
    credits = _docs.manager_logo_credits()
    assert credits.startswith("Brand marks come from [Simple Icons]")

    rows = [line for line in credits.splitlines() if line.startswith("| [")]
    icons = _docs.logo_manifest()["icons"]
    assert len(rows) == len(icons)
    for icon in icons.values():
        assert f"[{icon['title']}]({icon['source']})" in credits
        for mid in icon["managers"]:
            assert f"[`{mid}`](managers/{mid}.md)" in credits


def test_manager_stubs_in_sync():
    """Check the committed page stubs of `docs/managers/` match a fresh
    generation from the pool.

    The directory is wholly owned by `update_manager_stubs()`: one stub per
    pool manager, nothing else, each byte-identical to its template. Drift
    means a manager was added or removed without running
    `docs/docs_update.py` (repomatic's `update-docs` job self-heals this
    on the next push).
    """
    stub_dir = PROJECT_ROOT / "docs" / "managers"
    stubs = {path.stem: path for path in stub_dir.glob("*.md")}
    assert set(stubs) == set(pool.all_manager_ids)
    for mid, path in stubs.items():
        assert path.read_text(encoding="utf-8") == _docs.manager_page_stub(mid)


@all_managers
def test_manager_page_sections_render(manager):
    """Check every section generator of the per-manager pages produces
    non-empty, heading-free MyST.

    The sections are rendered live at Sphinx build time by the
    ``{python:render}`` blocks of `docs/managers/<id>.md`, so there is no
    checked-in copy to compare against: this test guards the generators
    against crashes and locks the heading-free invariant documented on
    `MANAGER_SECTIONS` (headings belong to the committed stubs).
    """
    heading = re.compile(r"^#{1,6} ", re.MULTILINE)
    fence = re.compile(r"(?ms)^(`{3,}).*?^\1$")
    for _title, func_name in _docs.MANAGER_SECTIONS:
        output = getattr(_docs, func_name)(manager.id)
        # Two sections are omitted for some managers (a section with no output is
        # dropped from the stub by manager_page_stub): reference traces for a
        # manager documenting no literal output samples, and the Rosetta table
        # for one documenting fewer than three harvestable native commands. Every
        # other section renders for every manager.
        if func_name not in ("manager_traces", "manager_rosetta"):
            assert output.strip()
        # Fenced blocks (code samples, eval-rst) cannot produce MyST headings:
        # only the prose between them must stay heading-free.
        assert not heading.search(fence.sub("", output))

    assert manager.homepage_url in _docs.manager_intro(manager.id)
    # Header, separator, then one row per operation.
    operations = _docs.manager_operations(manager.id)
    assert len(operations.splitlines()) == 2 + len(Operations)
    selection = _docs.manager_selection(manager.id)
    assert f"--no-{manager.id}" in selection
    assert f"[mpm.managers.{manager.id}]" in selection


DOCSTRING_FENCE = re.compile(
    r"(?ms)^([ \t]*)(`{3,})(?P<info>[^\n]*)\n.*?^[ \t]*\2[ \t]*$"
)
"""Backtick-fenced block of a docstring, whatever its indentation.

The info string stops at the newline: `.` spans lines under `re.DOTALL`, so a
greedy one would swallow every fence of the docstring into a single match.
"""

PROSE_DIRECTIVES = re.compile(r"\{(?!code-block|literalinclude|eval-rst)")
"""Fence info string of a directive whose body is prose, not code.

An admonition fence (note, warning, caution, seealso, todo) renders its content
as regular MyST, so its links matter as much as the surrounding paragraphs'.
Only a code block escapes the prose rules.
"""

BARE_URL = re.compile(r"(?<!\]\()(?<!\]\(<)(?<!<)https?://[^\s>)\]`,;\'\"]+")
"""A URL that is neither a markdown link target nor an autolink."""


def _strip_code_fences(docstring: str) -> str:
    """Drop the code blocks of a docstring, keeping every prose directive.

    A captured CLI transcript is data and escapes the prose rules; an
    admonition's body does not, so its own fence stays in.
    """
    return DOCSTRING_FENCE.sub(
        lambda match: (
            match.group(0)
            if PROSE_DIRECTIVES.match(match.group("info").strip())
            else ""
        ),
        docstring,
    )


def _prose_docstrings():
    """Yield every docstring of the package, code fences stripped out.

    Covers the four kinds `autodoc` renders: module, class, function and
    attribute docstrings (a bare string expression trailing an assignment).
    """
    for path in sorted((PROJECT_ROOT / "meta_package_manager").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="UTF-8"))
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    yield path, node.body[0].lineno, _strip_code_fences(doc)
            previous = None
            # `body` is a single expression on a lambda or a ternary, not a block.
            body = getattr(node, "body", None)
            for child in body if isinstance(body, list) else ():
                if (
                    isinstance(child, ast.Expr)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)
                    and isinstance(previous, (ast.Assign, ast.AnnAssign))
                ):
                    doc = _strip_code_fences(child.value.value)
                    yield path, child.lineno, doc
                previous = child


def test_docstrings_carry_no_bare_url():
    """Every URL in docstring prose must be a link.

    MyST's `linkify` extension is off, so a bare URL renders as dead plain
    text, both in the API docs and in the manager pages inlining the class
    docstrings. URLs inside a fenced block are captured CLI output (fwupd's
    `See https://…` warnings) and are left alone.
    """
    bare = [
        f"{path.relative_to(PROJECT_ROOT)}:{lineno}: {match.group()}"
        for path, lineno, doc in _prose_docstrings()
        for match in BARE_URL.finditer(doc)
    ]
    assert not bare, "Bare URLs in docstrings:\n" + "\n".join(bare)


def test_manager_traces_render_literal_blocks():
    """A class-based manager's reference traces surface exactly the literal
    installed/outdated/orphans blocks the corpus validates, in terminal-facing
    form.

    `manager_traces` and the corpus round-trip both read
    {func}`~meta_package_manager.docstring_corpus.literal_blocks`, so the
    rendered traces never drift from what the parsers are tested against. TOML
    managers keep their `[samples]` traces, covered by `test_bundled_parsing`.
    """
    for mid, manager in pool.items():
        if getattr(manager, "definition_source", None):
            continue
        traces = _docs.manager_traces(mid)
        blocks = literal_blocks(type(manager), ("installed", "outdated", "orphans"))
        assert bool(traces) == bool(blocks), mid
        for _member, _index, block in blocks:
            assert block in traces, mid


def test_manager_changelog_entries():
    """Check every changelog bullet reaches the manager pages it is scoped to.

    The release-history section is rendered live at Sphinx build time, so there
    is no checked-in copy to compare against: this recounts the (manager, entry)
    pairs straight from `changelog.md` and matches them against the index, which
    catches an entry silently dropped by a scope the parser fails to resolve.

    Every pool manager is asserted to have at least one entry, which makes the
    section double as the lint for a manager shipped without its changelog line.
    """
    index = _docs._changelog_entries()
    assert set(index) == set(pool.all_manager_ids)

    raw = PROJECT_ROOT.joinpath("changelog.md").read_text(encoding="utf-8")
    # The older releases hard-wrap their bullets, so an entry spans several
    # source lines: compare against the same folded copy the index reads.
    changelog = re.sub(r"\n[ \t]+(?![-*+] )(?=\S)", " ", raw)
    heading = re.compile(r"^## \[`([^`]+)` \(([^)]+)\)\]\(([^)]+)\)", re.MULTILINE)
    releases = set(heading.findall(changelog))

    pairs = 0
    for mid, entries in index.items():
        rendered = _docs.manager_changelog(mid)
        # The page opens straight on the newest release that touched it.
        newest = entries[0]
        assert rendered.startswith(
            f"- [`{newest.version}`]({newest.url}) ({newest.date})\n",
        )
        for entry in entries:
            pairs += 1
            assert (entry.version, entry.date, entry.url) in releases
            # Entry text is reproduced verbatim, flag included, under a release
            # linking to the comparison URL of its own changelog heading.
            flag = f"**{entry.flag}:** " if entry.flag else ""
            assert entry.text in changelog
            assert f"  - {flag}{entry.text}" in rendered
            # Every bullet is a full sentence, so an entry stopping short of
            # its period is one whose wrapped tail never made it in.
            assert entry.text.endswith("."), entry.text
            assert f"- [`{entry.version}`]({entry.url}) ({entry.date})" in rendered

    # Independent recount: every bullet scoped to a pool manager lands on that
    # manager's page, exactly once.
    expected = sum(
        1
        for scopes in re.findall(
            r"^- (?:\*\*[A-Za-z]+:\*\* )?\[([a-z0-9,\-]+)\]",
            changelog,
            re.MULTILINE,
        )
        for scope in scopes.split(",")
        if scope in pool
    )
    assert pairs == expected


def test_managers_index_table_renders():
    """Check the manager index generator still produces a well-formed table
    linking every pool manager to its documentation page.

    The table is rendered live at Sphinx build time by the ``{python:render}``
    block in `docs/managers.md`, so there is no checked-in copy to compare
    against.
    """
    table = _docs.managers_index_table()
    lines = table.splitlines()
    assert lines[0] == f"`mpm` can drive {len(pool)} package managers:"
    # The leading column carries the brand marks and is headerless.
    assert re.fullmatch(
        r"\|\s+\| Manager\s+\| ID\s+\|\s+Unmaintained\s+\|\s+Platforms\s+\|",
        lines[2],
    )
    unmaintained = 0
    for mid, manager in pool.items():
        # Both the name and the identifier link to the manager's page.
        assert f"[{manager.name}](managers/{mid}.md)" in table
        assert f"[`{mid}`](managers/{mid}.md)" in table
        if manager.unmaintained:
            unmaintained += 1
        if manager.logo:
            assert _docs.manager_logo(mid, inline=True) in table
    # The marker moved out of the ID cell into a column of its own.
    assert unmaintained
    assert table.count("⚠️") == unmaintained
    assert "⚠️](managers/" not in table
    # Every placeholder was substituted by the artwork it stands for.
    assert "%logo:" not in table


def test_matrix_blocks_in_sync():
    """Check the compatibility matrices embedded in the docs match a fresh
    regeneration from the git tags.

    Drift here means a release changed the Python classifiers or the
    click-extra requirement before repomatic's `update-docs` job refreshed
    the embedded blocks.

    Skipped when click-extra's `[sphinx]` extra (pulled by the `docs`
    dependency group) is missing, as in the hermetic unit-test environment.
    Without the full tag history (shallow clone, sdist build), regeneration
    leaves every block untouched and the test passes vacuously.
    """
    try:
        from click_extra.sphinx import matrix
    except ImportError:
        pytest.skip("needs the docs dependency group (click-extra[sphinx])")
    stale = matrix.update_matrix_blocks(
        (PROJECT_ROOT / "docs", PROJECT_ROOT / "readme.md"),
        check=True,
    )
    assert not stale


def test_mirror_blocks_in_sync():
    """Check the `<!-- mirror-src -->` and `:mirror:` blocks embedded in the docs
    and readme match a fresh regeneration from their generators.

    Drift here means a generator's output changed (a manager joined or left the
    pool, a class moved so the benchmark source-line anchors shifted) before
    repomatic's `update-docs` job refreshed the embedded blocks with
    `click-extra refresh-directives`.

    Skipped when click-extra's `[sphinx]` extra (pulled by the `docs`
    dependency group) is missing, as in the hermetic unit-test environment.
    """
    try:
        from click_extra.sphinx.python import update_mirror_blocks
    except ImportError:
        pytest.skip("needs the docs dependency group (click-extra[sphinx])")
    stale = update_mirror_blocks(
        (PROJECT_ROOT / "docs", PROJECT_ROOT / "readme.md"),
        check=True,
    )
    assert not stale


def test_retraction_table_well_formed():
    """Check the retraction table partitions the pool and travels intact.

    The "Retraction paths by registry" table of `docs/cooldown.md` is
    hand-curated, and `manager_cooldown()` reuses each row on the pages of the
    managers listed in it. Two invariants follow. A manager missing from the
    table silently loses the section on its page and one listed twice would
    resolve to whichever registry comes first, so the mapping must be a
    partition of the pool. And a reused cell renders from `docs/managers/`,
    one directory below `docs/cooldown.md`, so any relative target or same-page
    anchor it carries would resolve against the manager page instead: the
    reused cells must link absolutely or not at all.
    """
    registries: dict[str, list[str]] = {}
    relative = []
    for cells in _docs._cooldown_table("## Retraction paths by registry"):
        for mid in re.findall(r"\[`([^`]+)`\]", cells[1]):
            registries.setdefault(mid, []).append(cells[0])
        # The managers cell (index 1) stays behind on the cooldown page: only
        # the registry, retraction and publish-date cells get reused.
        for cell in (cells[0], cells[2], cells[3]):
            relative += [
                target
                for target in re.findall(r"]\(([^)]+)\)", cell)
                if not target.startswith("https://")
            ]

    assert set(registries) == set(pool.all_manager_ids)
    assert not {mid: rows for mid, rows in registries.items() if len(rows) > 1}
    assert not relative


@all_managers
def test_retraction_status_reuses_table_row(manager):
    """Check each manager's page surfaces its own registry row verbatim.

    A registry documenting neither a retraction path nor a publish date leaves
    the row alone: it renders as a plain line rather than a one-item list.
    """
    row = _docs._retraction_status(manager.id)
    # No row is a legitimate return for an unknown ID, but never for a pool
    # manager: test_retraction_table_well_formed holds the table to a partition.
    assert row, f"No retraction row covers {manager.id}."
    registry, withdrawal, publish_date = row
    section = _docs.manager_cooldown(manager.id)
    cells = [
        cell for cell in (withdrawal, publish_date) if cell not in _docs.EMPTY_CELLS
    ]
    bullet = "- " if cells else ""
    assert f"{bullet}Registry: {registry}" in section
    for label, cell in (("Retraction", withdrawal), ("Publish date", publish_date)):
        line = f"- {label}: {cell}"
        assert (line in section) is (cell not in _docs.EMPTY_CELLS)
