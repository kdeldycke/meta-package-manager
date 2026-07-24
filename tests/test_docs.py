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

import importlib.util
import re
import shutil
from itertools import permutations
from pathlib import Path

import pytest
from extra_platforms import Group, extract_members
from yaml import Loader, load, safe_load

from meta_package_manager.capabilities import Operations
from meta_package_manager.docstring_corpus import literal_blocks
from meta_package_manager.labels import (
    LABELS,
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

    competitors = set(docs_update.BENCHMARK_COMPETITORS)
    for mid, flags in data["managers"].items():
        assert mid == mid.lower()
        assert isinstance(flags, list)
        # Flags are valid competitor names, unique, and sorted in column order.
        assert set(flags).issubset(competitors)
        assert len(flags) == len(set(flags))
        assert flags == sorted(flags, key=docs_update.BENCHMARK_COMPETITORS.index)

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
    table = docs_update.benchmark_managers_table()
    lines = table.splitlines()
    assert len(lines) > 2
    header = lines[0]
    assert header.startswith("| Manager")
    assert "`mpm`" in header
    for competitor in docs_update.BENCHMARK_COMPETITORS:
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
    table = docs_update.binaries_download_table()
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
    table = docs_update.augmentations_table()
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
        assert path.read_text(encoding="utf-8") == docs_update.manager_page_stub(mid)


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
    for _title, func_name in docs_update.MANAGER_SECTIONS:
        output = getattr(docs_update, func_name)(manager.id)
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

    assert manager.homepage_url in docs_update.manager_intro(manager.id)
    # Header, separator, then one row per operation.
    operations = docs_update.manager_operations(manager.id)
    assert len(operations.splitlines()) == 2 + len(Operations)
    selection = docs_update.manager_selection(manager.id)
    assert f"--no-{manager.id}" in selection
    assert f"[mpm.managers.{manager.id}]" in selection


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
        traces = docs_update.manager_traces(mid)
        blocks = literal_blocks(type(manager), ("installed", "outdated", "orphans"))
        assert bool(traces) == bool(blocks), mid
        for _member, _index, block in blocks:
            assert block in traces, mid


def test_managers_index_table_renders():
    """Check the manager index generator still produces a well-formed table
    linking every pool manager to its documentation page.

    The table is rendered live at Sphinx build time by the ``{python:render}``
    block in `docs/managers.md`, so there is no checked-in copy to compare
    against.
    """
    table = docs_update.managers_index_table()
    lines = table.splitlines()
    assert lines[0] == f"`mpm` can drive {len(pool)} package managers:"
    assert lines[2].startswith("| Manager")
    for mid, manager in pool.items():
        assert f"](managers/{mid}.md)" in table
        if manager.deprecated:
            assert f"[⚠️]({manager.deprecation_url})" in table


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
