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

"""Documentation generators for pool-derived tables, diagrams and manager pages.

Private, docs-build-only helpers imported by the `{python:render}` directives in
`docs/*.md` and the committed `:mirror:` regions of `docs/benchmark.md` and
`docs/augmentations.md`. The leading-underscore name keeps them out of the public
API; shipping them with the package lets the render and `refresh-directives`
machinery import `meta_package_manager._docs` with no `sys.path` juggling. Never
imported from `__init__`, so `import meta_package_manager` stays dependency-light.

The file-writing orchestration (readme, pyproject, the `docs/managers/` stub set)
lives in `docs/docs_update.py`.

```{warning}
The generated Mermaid syntax targets the version bundled with
`sphinxcontrib-mermaid`, currently `11.12.1`. Avoid features introduced later.
```
"""

from __future__ import annotations

import csv
import inspect
import re
import sys
from collections import Counter
from functools import cache
from itertools import groupby
from pathlib import Path
from textwrap import dedent
from typing import NamedTuple
from urllib.parse import quote, urlparse

import yaml
from click_extra.table import TableFormat, render_table
from extra_platforms import Group, extract_members

from meta_package_manager.capabilities import (
    Operations,
    cleanup_orphan_is_synthesized,
    cooldown_is_synthesized,
    exact_search_is_synthesized,
    extended_search_is_synthesized,
    implements,
    implements_method,
    upgrade_all_is_synthesized,
)
from meta_package_manager.dispatch import (
    COMMAND_FAN_OUT,
    FAN_OUT_CONCURRENT,
    FAN_OUT_GROUPED,
    FAN_OUT_SEQUENTIAL,
    SHARED_LOCK_FAMILIES,
    LockFamily,
)
from meta_package_manager.docstring_corpus import (
    block_commands,
    block_language,
    class_display_blocks,
    literal_blocks,
    version_trace,
)
from meta_package_manager.labels import MANAGER_LABELS
from meta_package_manager.platforms import MAIN_PLATFORMS
from meta_package_manager.pool import pool
from meta_package_manager.specifier import PURL_MAP

# Version-gated TOML reader, following the same pattern as `tests/conftest.py`.
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Container, Iterable

PROJECT_ROOT = Path(__file__).parent.parent

BENCHMARK_COMPETITORS = ("topgrade", "upt", "pacaptr", "metapac")
"""Competing tools shown alongside `mpm` in the benchmark page, in column order."""

TOPGRADE_FALLBACK_GLYPH = "🛟"
"""Marker appended to an unsupported manager that `topgrade` still reaches.

`topgrade` is the pool's deliberate sinkhole: it auto-detects and upgrades
whatever it finds on the host, so a tool `mpm` declined to wrap directly stays
reachable through `mpm upgrade --topgrade`. For the majority of the unsupported
table that turns "not supported" into "not wrapped, still upgradable", which is
a different answer to the only question the page exists to settle.

Derived, never hand-written: membership is `topgrade` appearing in the manager's
`docs/benchmark.toml` competitor list, so the marker cannot drift from the data
it summarizes. Deliberately orthogonal to
{data}`UNSUPPORTED_GLYPHS`, since all four combinations occur: a dead upstream
`topgrade` still drives (`antibody`), a live refusal it drives (`zr`), and
either one it does not (`yaourt`, `upt`).
"""

WRAPPED_GLYPHS = {"maintained": "✅", "unmaintained": "⚠️"}
"""Glyph rendered for a manager `mpm` wraps, keyed by its `unmaintained` flag.

The counterpart of {data}`UNSUPPORTED_GLYPHS` on the wrapped side of the scale,
so every glyph literal of the five-state support scale is written once.
"""

QUEUED_GLYPH = "🚧"
"""Glyph for a manager assessed as a wrap candidate but not written yet.

The state a blank cell used to swallow. A manager absent from the pool and
from {data}`UNSUPPORTED_GLYPHS` may be one nobody has looked at, or one
looked at closely and queued behind something: a host the assessing machine
is not, a date a dead-upstream recheck waits on, or the project scope
`mpm` does not implement yet. Only the second kind carries this glyph, and
`docs/benchmark.toml`'s `queued` table is where the blocker is written
down, one line per manager, since the glyph alone cannot say which.

It is deliberately unlinked in a support cell, unlike every other state.
A wrapped manager has a class to point at and a declined one a verdict
section; a queued one has neither yet, and pointing at its home page would
answer a question the reader did not ask.
"""


UNSUPPORTED_GLYPHS = {"archived": "☠️", "excluded": "❌"}
"""Glyph rendered in the `mpm` column for each `unsupported` status.

A skull marks a tool whose upstream is retired: the wrapper is not missing, its
subject is gone. A cross marks a live tool `mpm` declined on its own merits.
Both link to {data}`UNSUPPORTED_DOCS_URL`, whose table carries the reason and
repeats the same glyph in its own status column, followed by
{data}`TOPGRADE_FALLBACK_GLYPH` where it applies.
"""


def unsupported_status(mid: str, status: str, competitors: Iterable[str]) -> str:
    """Status glyphs of an unsupported manager: its verdict, then its fallback.

    Returns the {data}`UNSUPPORTED_GLYPHS` entry for `status`, suffixed with
    {data}`TOPGRADE_FALLBACK_GLYPH` when `topgrade` is among the manager's
    `competitors`. Shared by the benchmark's `mpm` column and the sync test
    guarding `docs/unsupported.md`, so the two can never disagree on what a row
    should show.
    """
    glyph = UNSUPPORTED_GLYPHS[status]
    if "topgrade" in competitors:
        return f"{glyph} {TOPGRADE_FALLBACK_GLYPH}"
    return glyph


UNSUPPORTED_DOCS_URL = "unsupported.md"
"""Link target of the `mpm` cell for managers deliberately left unwrapped.

Relative to `docs/`, so it resolves in the Sphinx build and in the checked-in
mirror rendered on GitHub alike. Held as a single constant because every
manager listed in `benchmark.toml`'s `unsupported` key points at the same
page: retargeting it is then a one-line fix here, instead of an edit per
manager in the TOML. The section anchor comes from
{func}`unsupported_anchors`, so each glyph lands on the verdict that explains
that manager rather than at the top of the page.

```{note}
The fragment is a Sphinx anchor, computed the way `myst_heading_slug_func`
computes it. GitHub slugifies the same heading differently, keeping the spaces
the stripped glyphs leave behind, so the mirrored benchmark table lands a
GitHub reader at the top of the page instead. The published site is the
canonical home of these links, and a whole-page landing is the worst that
happens elsewhere.
```
"""

SUPPORT_SCALE = {
    WRAPPED_GLYPHS["maintained"]: "Active support by `mpm`",
    WRAPPED_GLYPHS["unmaintained"]: "Usable in `mpm`, but upstream is unmaintained",
    QUEUED_GLYPH: "Assessed as a candidate, not wrapped yet",
    TOPGRADE_FALLBACK_GLYPH: "Falls back to `topgrade`",
    UNSUPPORTED_GLYPHS["archived"]: "Unsupported by `mpm` and upstream is unmaintained",
    UNSUPPORTED_GLYPHS["excluded"]: "`mpm` declined support",
}
"""The six states a manager can be in, in the order the manager index shows them.

Keys are the glyphs {func}`_bare_support_glyph` returns, values the label both
{func}`manager_support_legend` and {func}`managers_index_table` render: the
legend as the meaning of a glyph, the index as the title of the group of rows
carrying it. One wording, so the key and its table can never disagree.
Composed from {data}`WRAPPED_GLYPHS`, {data}`QUEUED_GLYPH`,
{data}`TOPGRADE_FALLBACK_GLYPH` and {data}`UNSUPPORTED_GLYPHS` rather than
repeating their glyphs, so the scale cannot drift from the cells it
describes either.

Each label is a caption rather than a sentence: it titles a group of rows, and
a reader scanning six of them wants the state named, not explained. What a
glyph means beyond its name lives where the reason lives, in the manager's own
page or its verdict section.

The key order is a reading order, from best supported to least, and doubles as
the sort of {func}`managers_index_table`: the whole index groups by verdict
rather than running one alphabet from `am` to `zypper`, since the question a
reader brings to it is what became of a tool. Alphabetical order survives
inside each group.
"""


SUPPORT_ANCHORS = {
    **{glyph: f"state-{name}" for name, glyph in WRAPPED_GLYPHS.items()},
    QUEUED_GLYPH: "state-queued",
    TOPGRADE_FALLBACK_GLYPH: "state-topgrade-fallback",
    **{glyph: f"state-{name}" for name, glyph in UNSUPPORTED_GLYPHS.items()},
}
"""In-page anchor of each {data}`SUPPORT_SCALE` state on `docs/managers.md`.

{func}`managers_index_table` stamps one onto each group's title row, and
{func}`manager_support_bar` points the matching region of the bar at it, so a
reader who sees a share can reach the managers behind it in one click.

Named after the state rather than after its caption, which is what makes the
anchor outlive a rewording: four of the six names are the keys of
{data}`WRAPPED_GLYPHS` and {data}`UNSUPPORTED_GLYPHS`, read straight off those
mappings, and only the lifebuoy and the barrier need a literal, each being a
constant of its own rather than an entry in either.
"""


def _heading_slug(title: str) -> str:
    """Slugify a markdown heading the way the Sphinx build does.

    `docs/conf.py` pins `myst_heading_slug_func` to docutils' `make_id`, which
    strips the non-ASCII glyphs off a title, collapses whitespace runs to a
    single hyphen and lowercases the rest. Reimplemented here rather than
    imported: `docutils` reaches this project through the docs dependency
    group alone, and the benchmark table renders under the test group too.
    `test_unsupported_anchors_match_docutils` holds the two in lockstep.

    Markdown syntax is dropped first, since a slug is computed from the
    rendered text: a heading is usually a single linked code span, whose
    anchor then comes out as the bare manager ID.
    """
    plain = re.sub(r"\[`?([^`\]]+)`?\]\([^)]*\)", r"\1", title).replace("`", "")
    ascii_only = plain.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")


DECLINE_STAMP = re.compile(
    r"^Declined in \{mpm-release\}`(?P<version>[^`]+)`\.$",
    re.MULTILINE,
)
"""Line closing every verdict section of `docs/unsupported.md`.

Names the release that first published the verdict, which is what tells a reader
how old the reading behind it is. The page invites a reassessment, and a decision
taken two years ago is a better candidate for one than a decision taken last
week.

The version is all the page states. The link and the release date beside it are
rendered by the `mpm-release` role of `docs/conf.py`, off
{func}`changelog_releases`, and never written down. A checked-in date would age
from the moment it was typed, and every verdict of the release in preparation
would have to be rewritten the day that release ships, in the commit that
freezes it.

Written by hand, where the glyphs beside it are derived from the benchmark data
and the anchor from the title. Nothing holds this fact already: a declined tool
has no manager page, and the changelog announces a batch of declines in one
`[mpm]` bullet naming no ID at all. It cannot drift either, a shipped release
being immutable, where the glyphs move with their upstream.
`test_unsupported_verdicts_cite_a_release` holds each version to a release the
changelog declares, which is what the role needs to resolve it.
"""


class UnsupportedSection(NamedTuple):
    """One verdict section of `docs/unsupported.md`."""

    anchor: str
    """Slug the title renders to, and the target every glyph citing it links to."""

    glyphs: str
    """Verdict the title ends with, as {func}`unsupported_status` renders it."""

    manager_ids: tuple[str, ...]
    """Tools the verdict covers, in the order the section names them."""

    release: str
    """Version the {data}`DECLINE_STAMP` names, or an empty string for a section
    carrying no stamp."""


def unsupported_sections() -> tuple[UnsupportedSection, ...]:
    """Parse `docs/unsupported.md` into its verdict sections, in page order.

    A section covers the managers whose IDs appear as linked code spans in its
    own title; where the title names a family instead of a tool, they are the
    linked code spans of the paragraph opening the section. That fallback is
    what lets a verdict shared word for word be written once: fifteen JetBrains
    IDEs answer to a single section rather than fifteen copies of one
    paragraph.

    A family shares its {data}`DECLINE_STAMP` too, since its members were
    declined together. A tool joining one later is declined into a verdict that
    already stood, so it earns its own section unless the family's release is
    still true of it.

    Only glyph-bearing headings are verdicts. A heading without them is plain
    page structure, like the project-scoped ecosystems closing the page, and is
    skipped.
    """
    text = (PROJECT_ROOT / "docs" / "unsupported.md").read_text(encoding="UTF-8")
    verdict = (
        rf"(?:{'|'.join(UNSUPPORTED_GLYPHS.values())})"
        rf"(?: {TOPGRADE_FALLBACK_GLYPH})?"
    )
    sections = []
    for title, glyphs, body in re.findall(
        rf"^## (.+?) ({verdict})$\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    ):
        ids = re.findall(r"\[`([^`]+)`\]", title)
        if not ids:
            ids = re.findall(r"\[`([^`]+)`\]", body.strip().partition("\n")[0])
        stamp = DECLINE_STAMP.search(body)
        sections.append(
            UnsupportedSection(
                _heading_slug(f"{title} {glyphs}"),
                glyphs,
                tuple(ids),
                stamp["version"] if stamp else "",
            ),
        )
    return tuple(sections)


def unsupported_anchors() -> dict[str, str]:
    """Map each declined manager ID to the anchor of its verdict section.

    Derived from {func}`unsupported_sections`, so `docs/unsupported.md` stays
    the single source of truth for both the reason and where to link for it.
    Several IDs share one anchor wherever a family section covers them.
    """
    return {
        mid: section.anchor
        for section in unsupported_sections()
        for mid in section.manager_ids
    }


DOCS_SITE_URL = "https://mpm.run"
"""Base URL of the published documentation site.

Used by {func}`operation_matrix` to link each manager ID of `readme.md` to its
documentation page: the readme renders on GitHub and PyPI, where relative Sphinx
links cannot resolve, so the links must be absolute.

Duplicates `[project.urls] Documentation` of `pyproject.toml`, which is the
declared source and what `docs/conf.py` reads for `html_baseurl`. The value is
repeated here because runtime code cannot read `pyproject.toml`, which is not
shipped in the wheel; `test_docs_site_url_matches_pyproject` fails if the two
drift apart. Carries no trailing slash, since every consumer appends a rooted
path.
"""


def manager_page_url(manager_id: str) -> str:
    """Absolute URL of a manager's documentation page on the published site.

    Directory-shaped (`/managers/apk/`), the form the `dirhtml` builder set in
    `[tool.repomatic] sphinx.builder` publishes: the page is written as
    `managers/apk/index.html`, and the trailing slash is what keeps the server
    from answering a redirect on the way there. The `.html` URLs this site used
    to publish still resolve, through the stubs `docs/conf.py` writes beside
    every page.

    A function rather than an f-string repeated at each call site: the readme
    matrix and the manager-index prose both build it, and the shape of a
    published URL is exactly the kind of fact that drifts when it lives in two
    places.
    """
    return f"{DOCS_SITE_URL}/managers/{manager_id}/"


EMPTY_CELLS = frozenset({"", "—", "➖"})
"""Hand-curated table cells carrying no reusable content.

The tables of `docs/cooldown.md` are reused verbatim on the per-manager pages
({func}`manager_cooldown`). A cell holding nothing, an em dash or a bare
not-applicable marker has nothing to say there and is dropped rather than
rendered as an empty fact.
"""

LOGO_DIR = PROJECT_ROOT / "docs" / "assets" / "managers"
"""Vendored brand marks and their `logos.yaml` manifest.

Wholly owned by `docs/logos_update.py`, which is run by hand: the artwork
is committed so a docs build stays hermetic and never depends on an upstream icon
set still serving the same files.
"""

MIN_LOGO_CONTRAST = 3.0
"""Contrast ratio below which a brand color reads as pale on the light theme.

Advisory only, reported by `docs/logos_update.py` and never enforced at render
time. Gating on it was tried and dropped: [WCAG 2.2 exempts logotypes from
contrast requirements](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
precisely because a brand's own color is not the author's to correct, and the
guard was repainting recognizable marks (Fedora's blue, Homebrew's amber) a flat
black. Marks keep their color on the light theme whatever this says; the dark
theme still falls back to `currentColor`, which is about legibility against a
near-black background rather than about contrast ratios.
"""

FACT_SEPARATOR = "\u00a0· "
"""Separator between the repeated values of an infobox row.

A middle dot rather than a comma: the values are code spans whose own boxes
already read as separate tokens, and a comma between them adds a mark the eye
has to skip.

The leading space is a non-breaking one, so the dot cannot start a line on its
own. The box is narrow enough to wrap most rows, and a separator orphaned at the
head of a line reads as a bullet for the value that follows it. Breaking after
the dot is fine, hence the ordinary space on that side.
"""

GITHUB_BLOB_URL = "https://github.com/kdeldycke/meta-package-manager/blob/main"
"""Base URL for linking to source files in the benchmark table.

Pinned to the `main` branch so the generated artifact references the same
revision the docs are built from.
"""

GITHUB_ISSUES_URL = "https://github.com/kdeldycke/meta-package-manager/issues"
"""Base URL of the tracker, queried by label from each manager's infobox.

The `issues` endpoint rather than `pulls`: a search there returns issues *and*
pull requests, while `pulls` silently restricts itself to the latter.
"""

MANAGER_SECTIONS: tuple[tuple[str | None, str], ...] = (
    (None, "manager_intro"),
    ("What `mpm` adds to `{manager_id}`", "manager_augments"),
    ("Your `{manager_id}` commands, in `mpm`", "manager_rosetta"),
    ("Operations", "manager_operations"),
    ("Selecting and configuring `{manager_id}`", "manager_selection"),
    ("Recipes", "manager_recipes"),
    ("Privilege escalation", "manager_sudo"),
    ("Concurrency", "manager_concurrency"),
    ("Cooldown", "manager_cooldown"),
    ("Version probe", "manager_version_probe"),
    ("Reference traces", "manager_traces"),
    ("Upstream project", "manager_upstream"),
    ("Changelog", "scope_changelog"),
)
"""Layout of a per-manager documentation page: section title, generator function.

Single source of truth for {func}`manager_page` and the structural tests.
Sections lead with the `mpm` pitch (what it adds to the native tool) and its
usage, then document `mpm`'s preconceptions about the tool (the captured
transcripts backing the version probe and the parsers), and close on the
release history of that support. A section whose generator produces nothing for
a given manager is omitted from its page.

How `mpm` invokes the tool (binary names and lookup paths, the arguments and
environment forced on every call) has no section of its own: those are one-line
facts rather than prose, so they read better as rows of the page's infobox
({func}`manager_card`).

Each title is a `str.format` template receiving the manager ID, so a heading
can name its manager; a title with no replacement field renders unchanged.

Every generator listed here emits heading-free MyST: the headings around them
belong to {func}`manager_page`, the one place a page's layout is written down.
That is what leaves a stub with nothing to say about its own sections, and a
new section costing one edit here rather than a rewrite of `docs/managers/`.
"""

SHIELDS_URL = "https://img.shields.io"
"""Badge service the per-manager upstream readings are rendered by.

Every URL built on it is exempted from `linkcheck` in `docs/conf.py`: a hundred
manager pages carrying a dozen badges each would spend the job's whole budget
confirming a service that answers an image to any query, valid or not.
"""

BADGE_STYLE = "flat-square"
"""Shields.io style shared by the manager pages and the benchmark tables."""


class UpstreamBadge(NamedTuple):
    """One live reading of a manager's upstream repository."""

    group: str
    """Metric family this reading belongs to, named after the benchmark's own
    sections so both pages ask the reader to learn one vocabulary."""

    label: str
    """Alt text of the image, read in place of the badge when it does not load."""

    path: str
    """Shields.io path below the forge family, with `{repo}` standing for the
    repository's `owner/name` path."""

    release_source: str | None = None
    """Sampled `release_source` this reading requires, `None` to always render.

    Gates the badges that only mean something for a project publishing releases
    on its forge. Shields cannot tell an unreleased project from a missing one:
    both answer a red *no releases or repo not found*, which is how `pip` (which
    tags rather than releases) would have earned a broken-looking page. The
    weekly sample already settled that question per manager, so it selects the
    badge here.
    """


UPSTREAM_BADGES: dict[str, tuple[UpstreamBadge, ...]] = {
    "github": (
        UpstreamBadge("Activity", "commit activity", "commit-activity/m/{repo}"),
        UpstreamBadge(
            "Activity", "commits since", "commits-since/{repo}/latest", "release"
        ),
        UpstreamBadge("Activity", "open issues", "issues-raw/{repo}"),
        UpstreamBadge("Activity", "open pull requests", "issues-pr-raw/{repo}"),
        UpstreamBadge("Popularity", "forks", "forks/{repo}"),
        UpstreamBadge("Popularity", "watchers", "watchers/{repo}"),
        UpstreamBadge("Popularity", "contributors", "contributors/{repo}"),
        UpstreamBadge("Metadata", "latest release", "v/release/{repo}", "release"),
        UpstreamBadge("Metadata", "latest tag", "v/tag/{repo}", "tag"),
        UpstreamBadge("Metadata", "release date", "release-date/{repo}", "release"),
        UpstreamBadge("Metadata", "license", "license/{repo}"),
        UpstreamBadge("Metadata", "main language", "languages/top/{repo}"),
    ),
    "gitlab": (
        UpstreamBadge("Activity", "open issues", "issues/open/{repo}"),
        UpstreamBadge("Activity", "open merge requests", "merge-requests/open/{repo}"),
        UpstreamBadge("Popularity", "forks", "forks/{repo}"),
        UpstreamBadge("Popularity", "contributors", "contributors/{repo}"),
        UpstreamBadge("Metadata", "latest tag", "v/tag/{repo}"),
        UpstreamBadge("Metadata", "license", "license/{repo}"),
    ),
    "gitea": (
        UpstreamBadge("Activity", "open issues", "issues/open/{repo}"),
        UpstreamBadge("Activity", "open pull requests", "pull-requests/open/{repo}"),
        UpstreamBadge("Popularity", "forks", "forks/{repo}"),
        UpstreamBadge("Metadata", "latest release", "v/release/{repo}", "release"),
    ),
}
"""Readings each forge family answers, in render order.

Not the same list three times: a badge is listed for a forge only where it was
verified to answer, since shields renders a red error image for an endpoint a
forge cannot serve. GitHub is the deepest catalogue by far, which is also where
109 of the sampled upstreams live; GitLab has no release-date badge at all, and
the Gitea family (Codeberg) tops out at four.

Stars and the newest commit are deliberately absent: both are already stated by
{func}`manager_card` from the weekly sample, and a page that reads its own
figure twice from two sources eventually contradicts itself.
"""

UPSTREAM_FORGES: dict[str, tuple[str, str | None]] = {
    "codeberg.org": ("gitea", "gitea_url"),
    "github.com": ("github", None),
    "gitlab.alpinelinux.org": ("gitlab", "gitlab_url"),
    "gitlab.archlinux.org": ("gitlab", "gitlab_url"),
    "gitlab.com": ("gitlab", None),
    "gitlab.exherbo.org": ("gitlab", "gitlab_url"),
    "salsa.debian.org": ("gitlab", "gitlab_url"),
}
"""Badge family each forge host is read through, and the parameter naming the
instance.

Keyed by host and never guessed from its name, like the sampler's own
`FORGE_APIS`: a host missing here renders no badges rather than a page of red
error images, and `test_upstream_badges_cover_every_forge` names it. The
public instances need no parameter; every self-hosted one is passed its base
URL, which is what lets Alpine's own GitLab and Codeberg's Forgejo answer
through the same service as GitHub.
"""

NO_UPSTREAM = {
    "apt-mint": "Ships in a distribution package with no public repository.",
    "gcloud": "Google publishes the Cloud SDK as a binary; its source is not.",
    "opkg": "Hosted on the Yocto Project's cgit, which serves no API.",
    "pkgit": "Hosted on Symlinx's cgit, which serves no API.",
    "steamcmd": "Valve ships SteamCMD as a proprietary binary.",
    "sun-tools": "Oracle Solaris packaging tools are proprietary.",
    "tazpkg": "Hosted on SliTaz's Mercurial server, which serves no API.",
    "urpmi": "Hosted on Mageia's own git server, which serves no API.",
}
"""Managers whose upstream cannot be measured, and why.

Recorded rather than left implicit: a manager absent from both the metrics
subjects and this map is an oversight a conformance test reports, while one
listed here is a decision. Their popularity and activity cells stay empty on
the manager pages.
"""


def _lock_families() -> tuple[LockFamily, ...]:
    """Order the lock families widest-first, ties broken by backend name.

    Mermaid derives a sankey's node order from its link order, so the widest
    family leads and the two-member ones close the diagram. The same order
    carries the table, keeping the two readings of `docs/concurrency.md` row by
    band.
    """
    return tuple(
        sorted(SHARED_LOCK_FAMILIES, key=lambda f: (-len(f.members), f.backend))
    )


FAN_OUT_GLYPHS: dict[str, str] = {
    FAN_OUT_CONCURRENT: "⇶⇶⇶",
    FAN_OUT_GROUPED: "⇉⇶→",
    FAN_OUT_SEQUENTIAL: "→→→",
}
"""Glyph rendered in the `Concurrency` column for each fan-out mode.

Arrow density stands in for how many managers move at once: three
three-way arrows for a mode that never throttles, three single arrows for
one that never overlaps, and a mix of both for the mode that is either
depending on which managers were selected. Deliberately not ✅/❌, which
these docs reserve for a capability a tool has or lacks: a sequential
command is working as designed rather than missing something.

{data}`~meta_package_manager.dispatch.FAN_OUT_NONE` has no glyph on purpose.
Those subcommands are absent from the table rather than shown as a blank row,
their `mpm --jobs` answer being that the question does not arise.
"""


def concurrency_table() -> str:
    """Produce the per-subcommand table of the concurrency page.

    One row per {data}`~meta_package_manager.dispatch.COMMAND_FAN_OUT` entry
    that spreads work over managers at all, glyphed through
    {data}`FAN_OUT_GLYPHS` and ordered as the catalog declares them.
    """
    table = [
        [f"`mpm {entry.invocation}`", FAN_OUT_GLYPHS[entry.mode]]
        for entry in COMMAND_FAN_OUT
        if entry.mode in FAN_OUT_GLYPHS
    ]
    return render_table(
        table,
        headers=["Command", "Concurrency"],
        table_format=TableFormat.GITHUB,
        colalign=("left", "center"),
        disable_numparse=True,
    )


def lock_families_sankey() -> str:
    """Produce a sankey diagram of the managers `mpm` refuses to overlap.

    Three levels: the serialized population, the backend each family contends
    for, then the managers queueing on it. Rendered on `docs/concurrency.md`,
    where the prose above it accounts for the rest of the pool.

    ```{note}
    Only the families are drawn, and the diagram is rooted at them rather than
    at `mpm`. Managers sharing no backend are the large majority, so a band for
    them would take most of the canvas and squeeze all seven families into what
    is left, to answer a question the sentence above the diagram answers
    better. This is what replaced the flat fan-out of one band per manager the
    readme used to carry, which had grown to a hundred-odd bands of equal
    width: a picture of the pool's size rather than of its structure, and slow
    to lay out for it.
    ```

    ```{warning}
    Output must stay compatible with the Mermaid version bundled in
    `sphinxcontrib-mermaid`. See module docstring for details.
    ```
    """
    families = _lock_families()
    root = "Serialized managers"
    links = [f"{root},{family.backend},{len(family.members)}" for family in families]
    links.extend(
        f"{family.backend},{mid},1"
        for family in families
        for mid in sorted(family.members)
    )

    output = dedent("""\
        ```mermaid
        ---
        config: {"sankey": {"showValues": false, "width": 800, "height": 600}}
        ---
        sankey-beta\n
        """)
    output += "\n".join(links)
    output += "\n```"
    return output


def lock_families_table() -> str:
    """Produce the shared-backend table of the concurrency page.

    One row per {class}`~meta_package_manager.dispatch.LockFamily`: the backend
    its members queue on, those members linked to their own pages, and the
    family's `contention` sentence.

    That sentence is a fragment by design, written to complete *"`mpm` never
    runs X at the same time as Y: …"* on each member's page. It is reused here
    verbatim under a *Why?* heading, which is a frame a lowercase fragment
    reads naturally in, rather than recased into a standalone sentence: one
    wording, one place to fix it.
    """
    table = [
        [
            family.backend,
            ", ".join(
                f"[`{mid}`](managers/{mid}.md)" for mid in sorted(family.members)
            ),
            family.contention,
        ]
        for family in _lock_families()
    ]
    return render_table(
        table,
        headers=["Shared backend", "Managers", "Why?"],
        table_format=TableFormat.GITHUB,
        disable_numparse=True,
    )


def operation_matrix() -> tuple[str, str]:
    """Produce a table of managers' metadata and supported operations.

    Each manager ID links to its dedicated documentation page (absolute URL:
    the readme renders on GitHub and PyPI, where relative Sphinx links cannot
    resolve). Home pages are listed on the manager pages themselves.
    """
    # Build up the column titles.
    headers = [
        "Package manager",
        "Version",
        "Cooldown",
    ]

    # Footnotes are used to details the OSes covered by each platform group.
    footnotes = []

    # One platform column, with the legend its cells need set below the table: a
    # column per platform labelled each icon, a single one cannot. The footnote
    # naming a group's members hangs off the icon it belongs to, which is also
    # what keeps those definitions referenced instead of orphaned.
    legend = []
    for p_obj in MAIN_PLATFORMS:
        entry = f"{p_obj.icon} {p_obj.name}"
        # Add footnote for groups with more than one platform.
        if isinstance(p_obj, Group) and len(p_obj) > 1:
            footnote_tag = f"[^{p_obj.id}]"
            entry += footnote_tag
            platforms_string = ", ".join(
                sorted(
                    (
                        p.name
                        for p in p_obj.members.values()  # type: ignore[attr-defined]
                    ),
                    key=str.casefold,
                ),
            )
            footnotes.append(f"{footnote_tag}: {p_obj.name}: {platforms_string}.")
        legend.append(entry)
    headers.append("Platforms")

    headers.extend(f"`{op.name}`" for op in Operations)

    table = []
    for mid, m in sorted(pool.items()):
        line = [
            f"[`{mid}`]({manager_page_url(mid)})"
            + ("" if not m.unmaintained else f" [⚠️]({manager_page_url(mid)})"),
            _format_requirement(m.requirement or ""),
            "✓" if m.supports_cooldown else "",
        ]
        line.append(
            " ".join(
                p_obj.icon
                for p_obj in MAIN_PLATFORMS
                if m.platforms.issuperset(extract_members(p_obj))
            ),
        )
        line.extend("✓" if implements(m, op) else "" for op in Operations)
        table.append(line)

    # Set each column alignment.
    alignments = ["left", "left", "center", "center"]
    alignments.extend(["center"] * len(Operations))

    rendered_table = render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=alignments,
        disable_numparse=True,
    )

    # The legend decodes the Platforms column, so it travels with the table
    # rather than with the footnote definitions parked at the end of the readme.
    # The blank line before it is load-bearing: this output is mirrored into a
    # raw Markdown region that `mdformat` reformats in the autofix pipeline, and
    # a line abutting the table is parsed as one more table row, which the
    # formatter then rewrites into an explicit `| … |` row. That desynchronizes
    # the region from this generator and reddens `test_mirror_blocks_in_sync`.
    return (
        f"{rendered_table}\n\nPlatforms: {FACT_SEPARATOR.join(legend)}",
        "\n\n".join(footnotes),
    )


def _format_requirement(requirement: str) -> str:
    """Render a version specifier for reading: `>=2.10.0` becomes `>= 2.10`.

    Two cosmetic passes: the comparison operator is split from the version it
    applies to, and trailing zero components are dropped, since `2.10.0` and
    `2.10` pin the same floor while only one of them is worth reading.

    Shared by the readme's operation matrix and the manager infoboxes, so both
    render a requirement the same way. Display only: what the runtime parses is
    the manager's own
    {attr}`~meta_package_manager.manager.PackageManager.requirement`, which keeps
    the exact upstream release it was verified against.
    """

    def trim(match: re.Match) -> str:
        components = match.group(0).split(".")
        while len(components) > 1 and components[-1] == "0":
            components.pop()
        return ".".join(components)

    trimmed = re.sub(r"\d+(?:\.\d+)*", trim, requirement)
    # Split the comparison operator from the version it applies to, then give a
    # comma-joined range room to breathe.
    spaced = re.sub(r"(?<=[<>=!~])(?=[\d])", " ", trimmed)
    return re.sub(r",\s*", ", ", spaced)


def manager_source_url(manager_id: str) -> str:
    """Return a GitHub URL pointing to the class definition of a manager.

    Resolves the manager class via {data}`meta_package_manager.pool.pool`,
    then uses {mod}`inspect` to derive the source file and line number of
    the class declaration. Used by the benchmark page to back each `✅` in
    the `mpm` column with a link to its implementation.
    """
    manager = pool[manager_id]
    # A config-defined manager (built from a shipped TOML file, not a class body) has no
    # Python source line to point at; link to its bundled definition file instead.
    source = getattr(manager, "definition_source", None)
    if source:
        return f"{GITHUB_BLOB_URL}/{source}"
    cls = type(manager)
    src = Path(inspect.getsourcefile(cls)).resolve()  # type: ignore[arg-type]
    rel = src.relative_to(PROJECT_ROOT)
    _, lineno = inspect.getsourcelines(cls)
    return f"{GITHUB_BLOB_URL}/{rel.as_posix()}#L{lineno}"


@cache
def _load_benchmark_toml() -> dict:
    """Parse `docs/benchmark.toml`, shared by every generator reading it.

    Cached: the benchmark table, the manager index and its population stats
    all read the same file within one build.
    """
    toml_path = PROJECT_ROOT / "docs" / "benchmark.toml"
    content = toml_path.read_text(encoding="UTF-8")
    return tomllib.loads(content)  # type: ignore[no-any-return]


def _bare_support_glyph(
    mid: str,
    unsupported: dict[str, str],
    competitor_data: dict[str, list[str]],
    queued: Container[str],
) -> str:
    """Support glyph of a manager ID, unlinked: which {data}`SUPPORT_SCALE` state.

    A wrapped manager takes its {data}`WRAPPED_GLYPHS` entry, keyed by its
    `unmaintained` flag. A declined one takes {data}`TOPGRADE_FALLBACK_GLYPH`
    where `topgrade` still reaches it, and its {data}`UNSUPPORTED_GLYPHS`
    verdict otherwise. A manager `queued` names takes {data}`QUEUED_GLYPH`: it
    is a candidate whose wrap waits on something the assessing host lacks. A
    manager in none of the three, assessed by nobody yet, has no glyph at all.

    One glyph per manager. Where `topgrade` still reaches the tool, the lifebuoy
    stands alone: it already answers the only question a support cell asks, and
    pairing it with the verdict doubled the width of every such row for a fact
    the linked page states anyway. The skull and the cross therefore mark only
    the tools nothing reaches at all. `docs/unsupported.md` keeps both glyphs,
    being the record rather than the comparison.

    Split out of {func}`_support_glyph` because the glyph is also what
    {func}`manager_support_legend` counts and what {func}`managers_index_table`
    groups its rows by, neither of which wants the link.
    """
    if mid in pool:
        flag = "unmaintained" if pool[mid].unmaintained else "maintained"
        return WRAPPED_GLYPHS[flag]
    if mid in queued:
        return QUEUED_GLYPH
    if mid in unsupported:
        if "topgrade" in competitor_data.get(mid, []):
            return TOPGRADE_FALLBACK_GLYPH
        return UNSUPPORTED_GLYPHS[unsupported[mid]]
    return ""


def _support_glyph(
    mid: str,
    unsupported: dict[str, str],
    anchors: dict[str, str],
    competitor_data: dict[str, list[str]],
    queued: Container[str],
) -> str:
    """Linked support glyph for a manager ID: the benchmark's own `mpm` column rule.

    The glyph comes from {func}`_bare_support_glyph`; all this adds is its
    target. A wrapped manager links to the class proving it, a declined one to
    its own section of {data}`UNSUPPORTED_DOCS_URL`, a queued one stays
    unlinked for want of either, and a manager assessed by nobody yet renders
    an empty cell. Shared by
    {func}`benchmark_managers_table` and {func}`managers_index_table`, so the
    two pages can never disagree on what a manager's glyph should be.
    """
    glyph = _bare_support_glyph(mid, unsupported, competitor_data, queued)
    if not glyph:
        return ""
    if glyph == QUEUED_GLYPH:
        return glyph
    if mid in pool:
        return f"[{glyph}]({manager_source_url(mid)})"
    anchor = anchors.get(mid)
    target = f"{UNSUPPORTED_DOCS_URL}#{anchor}" if anchor else UNSUPPORTED_DOCS_URL
    return f"[{glyph}]({target})"


def benchmark_managers_table() -> str:
    """Produce the `Package manager support` table of the benchmark page.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    `docs/benchmark.md`, so the table (and its source-line anchors) always
    matches the code being documented without a checked-in copy.

    The `mpm` column is rendered by {func}`_support_glyph`, shared with the manager
    index so the two pages can never disagree on a manager's status. Competitor
    columns are filled from `docs/benchmark.toml`, which only encodes what the
    *other* tools support.

    Each manager identifier in the first column is rendered as a link: to its
    dedicated documentation page for implemented managers, or to its homepage
    from the TOML's `homepages` mapping for competitor-only managers. IDs
    without any known URL render as plain ``\\`code\\```.

    Support cells are normally `✅`, but render as `[🟡](url)` when the
    `(manager_id, competitor)` pair is listed in the TOML's
    `coarse_support` map, with the URL pointing to the maintainer's own
    acknowledgement of the bundling. `🟡` means the competitor can only
    reach this manager through a coarser umbrella step (topgrade's
    `--only shell` or `--only vim`), never in isolation. Refused
    managers (from the `refused` map) render as `[❌](url)` where the
    URL is the specific decision or refusal that documents the declined
    support.

    Manager rows are the sorted union of pool IDs and TOML keys, so a new
    entry on either side appears in the table without manual edits.
    """
    data = _load_benchmark_toml()
    competitor_data: dict[str, list[str]] = data["managers"]
    homepages: dict[str, str] = data.get("homepages", {})
    coarse_support: dict[str, dict[str, str]] = data.get("coarse_support", {})
    refused: dict[str, dict[str, str]] = data.get("refused", {})
    unsupported: dict[str, str] = data.get("unsupported", {})
    queued: dict[str, str] = data.get("queued", {})
    anchors = unsupported_anchors()

    pool_ids = set(pool.all_manager_ids)
    all_ids = sorted(
        pool_ids
        | competitor_data.keys()
        | refused.keys()
        | unsupported.keys()
        | queued.keys()
    )

    headers = ["Manager", "`mpm`"]
    headers.extend(f"`{name}`[^{name}]" for name in BENCHMARK_COMPETITORS)

    table = []
    for mid in all_ids:
        if mid in pool_ids:
            label = f"[`{mid}`](managers/{mid}.md)"
        else:
            url = homepages.get(mid)
            label = f"[`{mid}`]({url})" if url else f"`{mid}`"
        row = [
            label,
            _support_glyph(mid, unsupported, anchors, competitor_data, queued),
        ]
        flags = set(competitor_data.get(mid, []))
        coarse_map = coarse_support.get(mid, {})
        refused_map = refused.get(mid, {})
        cells: list[str] = []
        for name in BENCHMARK_COMPETITORS:
            if name in flags:
                if name in coarse_map:
                    cells.append(f"[🟡]({coarse_map[name]})")
                else:
                    cells.append("✅")
            elif name in refused_map:
                cells.append(f"[❌]({refused_map[name]})")
            else:
                cells.append("")
        row.extend(cells)
        table.append(row)

    alignments = ["left"] + ["center"] * (1 + len(BENCHMARK_COMPETITORS))

    return render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=alignments,
        disable_numparse=True,
    )


def augmentations_table() -> str:
    """Produce the per-manager table of the augmentations page.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    `docs/augmentations.md`, so the table always matches the code being
    documented without a checked-in copy.

    Each `✅` marks a capability `mpm` synthesizes for a manager that lacks
    it natively, straight from the capability introspection helpers:

    - *Full* `upgrade --all`: the manager only reaches the operation through
      the one-by-one fallback
      ({func}`meta_package_manager.capabilities.upgrade_all_is_synthesized`).
    - *Orphan sweep*: the manager has no native "remove every orphan" verb, so
      `mpm cleanup --orphans` synthesizes it from the manager's orphan listing
      and per-package removal
      ({func}`meta_package_manager.capabilities.cleanup_orphan_is_synthesized`).
    - *Exact search* and *Extended search*: the manager's native search cannot
      filter that way, so `mpm` refilters the raw results itself (the
      `exact_support`/`extended_support` flags set by
      {func}`meta_package_manager.capabilities.search_capabilities` and the
      config-defined manager builder).
    - *Cooldown gate*: the manager has no native release-age knob, so `mpm`
      enforces `--cooldown` itself, probing each package's publication date
      and holding back the too-fresh ones
      ({func}`meta_package_manager.capabilities.cooldown_is_synthesized`).

    Managers needing no backfill at all are left out of the table. Each listed
    manager links to its dedicated documentation page.
    """
    table = []
    for mid, manager in sorted(pool.items()):
        upgrade_all = upgrade_all_is_synthesized(manager)
        orphan_sweep = cleanup_orphan_is_synthesized(manager)
        exact = exact_search_is_synthesized(manager)
        extended = extended_search_is_synthesized(manager)
        cooldown = cooldown_is_synthesized(manager)
        if not (upgrade_all or orphan_sweep or exact or extended or cooldown):
            continue
        table.append([
            f"[`{mid}`](managers/{mid}.md)",
            "✅" if upgrade_all else "",
            "✅" if orphan_sweep else "",
            "✅" if exact else "",
            "✅" if extended else "",
            "✅" if cooldown else "",
        ])

    return render_table(
        table,
        headers=[
            "Manager",
            "Full `upgrade --all`",
            "Orphan sweep",
            "Exact search",
            "Extended search",
            "Cooldown gate",
        ],
        table_format=TableFormat.GITHUB,
        colalign=["left", "center", "center", "center", "center", "center"],
        disable_numparse=True,
    )


def binaries_download_table() -> str:
    """Produce the per-platform download table of the latest release binaries.

    Rendered live at Sphinx build time by the ``{python:render}`` block in
    `docs/install.md`, from `docs/assets/binaries.csv`, which the release pipeline
    extends at each release with the exact asset URLs, newest first.

    Every release publishes an unversioned `releases/latest/download` alias beside
    each versioned artifact, but the table links the versioned one
    (`meta-package-manager-7.3.0-linux-arm64.bin`): the alias moves on to the next
    release while the table's version column stays put, so only the versioned URL
    keeps delivering the bytes its row claims.
    """
    csv_path = PROJECT_ROOT / "docs" / "assets" / "binaries.csv"
    # Cells are markdown: the version cell starts with [`7.3.0` ...] and the
    # platform cell embeds the download link as
    # [... `linux-arm64`](https://github.com/.../meta-package-manager-7.3.0-linux-arm64.bin).
    version_regexp = re.compile(r"\[`(?P<version>[^`]+)`")
    link_regexp = re.compile(r"`(?P<target>[a-z0-9]+-[a-z0-9]+)`\]\((?P<url>[^)]+)\)")
    downloads = {}
    latest_version = None
    with csv_path.open(encoding="UTF-8") as csv_file:
        for row in csv.DictReader(csv_file):
            version_match = version_regexp.search(row["Version"])
            link_match = link_regexp.search(row["Platform"])
            if not version_match or not link_match:
                continue
            if latest_version is None:
                latest_version = version_match["version"]
            if version_match["version"] != latest_version:
                break
            downloads[link_match["target"]] = link_match["url"]

    table = []
    for os_label, os_id in (
        ("Linux", "linux"),
        ("macOS", "macos"),
        ("Windows", "windows"),
    ):
        cells = [f"**{os_label}**"]
        for arch in ("arm64", "x64"):
            url = downloads.get(f"{os_id}-{arch}")
            filename = url.rsplit("/", 1)[-1] if url else None
            cells.append(f"[Download `{filename}`]({url})" if url else "")
        table.append(cells)

    return render_table(
        table,
        headers=["Platform", "`arm64`", "`x86_64`"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "left"],
        disable_numparse=True,
    )


def _fenced(content: str, language: str) -> str:
    """Wrap content in a fenced code block, lengthening the fence as needed.

    Sample outputs are arbitrary text: a fence one backtick longer than the
    longest backtick run in the content can never be terminated early.
    """
    longest = max(
        (len(run.group(0)) for run in re.finditer(r"`+", content)),
        default=0,
    )
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{content}\n{fence}"


@cache
def _toml_definition(definition_source: str) -> dict:
    """Parse a bundled TOML definition file into its raw document.

    Cached: rendering one config-defined manager's page reads the same file
    from several section generators.
    """
    content = (PROJECT_ROOT / definition_source).read_text(encoding="UTF-8")
    return tomllib.loads(content)  # type: ignore[no-any-return]


@cache
def _cooldown_table(section_title: str) -> tuple[tuple[str, ...], ...]:
    """Parse one hand-curated table of `docs/cooldown.md` into its rows.

    Both tables of the page are reused on the per-manager pages, so both are
    read the same way: the section is delimited by its own title and the next
    `##` heading, and every pipe-prefixed line of at least four cells is kept
    with its markdown preserved. The header and separator lines come along
    harmlessly, as no manager ID ever matches them.
    """
    text = (PROJECT_ROOT / "docs" / "cooldown.md").read_text(encoding="UTF-8")
    section = text.partition(section_title)[2].partition("\n## ")[0]
    rows: list[tuple[str, ...]] = []
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) >= 4:
            rows.append(cells)
    return tuple(rows)


def _cooldown_status(manager_id: str) -> tuple[str, str, str] | None:
    """Extract a manager's row from the cooldown support table.

    The "Supported managers" table of `docs/cooldown.md` is the hand-curated
    source of truth for release-age gating: per manager, a status glyph, the
    native mechanism and an upstream reference. A row may cover several managers
    at once, its id cell listing each as a backticked code span (like the shared
    `uv`/`uvx` row). Returns the three cells with their markdown preserved
    (`—` marks an empty cell), or `None` when the table has no row for the
    manager yet.
    """
    for cells in _cooldown_table("## Supported managers"):
        if manager_id in re.findall(r"`([^`]+)`", cells[0]):
            return cells[1], cells[2], cells[3]
    return None


def _retraction_status(manager_id: str) -> tuple[str, str, str] | None:
    """Extract a manager's registry row from the retraction table.

    The "Retraction paths by registry" table of `docs/cooldown.md` records
    whether a compromised release can be withdrawn from the registry a manager
    resolves against, and whether that registry publishes a per-version release
    date. Both are properties of the registry rather than of the manager CLI, so
    the table is keyed by registry and lists its managers in the second cell,
    each as a linked code span. Returns the registry name, the retraction shape
    and the publish-date cell, or `None` when no row covers the manager.

    ```{note}
    Every pool manager belongs to exactly one row, and the reused cells link
    absolutely so they survive the move to `docs/managers/`. Both invariants
    are guarded by `test_retraction_table_well_formed`.
    ```
    """
    for cells in _cooldown_table("## Retraction paths by registry"):
        if manager_id in re.findall(r"\[`([^`]+)`\]", cells[1]):
            return cells[0], cells[2], cells[3]
    return None


def _toml_definition_intro(definition_source: str) -> str | None:
    """Extract the description comment atop a bundled TOML definition.

    The TOML counterpart of a manager class docstring: each bundled file opens
    with a comment block describing the manager and its quirks. The
    schema/loader pointer is stripped, bare URLs are wrapped into autolinks,
    and paragraph breaks (lone `#` lines) are preserved. Returns `None` when
    the file carries no such comment.
    """
    lines = []
    for line in (
        (PROJECT_ROOT / definition_source).read_text(encoding="UTF-8").splitlines()
    ):
        if line == "#":
            lines.append("")
        elif line.startswith("# "):
            lines.append(line[2:])
        else:
            break

    text = "\n".join(lines)
    # The schema/loader pointer spans reflowed lines, so strip it before
    # splitting paragraphs.
    text = re.sub(r"(?s)\s*See\s+docs/overrides\.md.*?for\s+the\s+loader\.", "", text)
    paragraphs = [p.strip("\n") for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return None
    intro = "\n\n".join(paragraphs)

    def autolink(match: re.Match) -> str:
        # Keep trailing punctuation out of the link target.
        url = match.group(0).rstrip(".,;:")
        return f"<{url}>{match.group(0)[len(url) :]}"

    # MyST's linkify extension is off: turn bare URLs into explicit autolinks.
    return re.sub(r"https?://[^\s)>]+", autolink, intro)


@cache
def logo_manifest() -> dict:
    """Read the provenance manifest of the vendored brand marks."""
    manifest: dict = yaml.safe_load(
        (LOGO_DIR / "logos.yaml").read_text(encoding="UTF-8"),
    )
    return manifest


def manager_logo(manager_id: str, *, inline: bool = False) -> str:
    """Produce the inlined brand mark of a manager, or nothing when it has none.

    The SVG is injected verbatim into the page instead of being referenced as an
    image file, which is what lets CSS recolor it: the vendored marks carry no
    `fill`, so they inherit `currentColor` and stay legible on both themes. The
    brand color is passed as a custom property and the stylesheet applies it on
    the light theme only, for every mark: {data}`MIN_LOGO_CONTRAST` is reported
    by `docs/logos_update.py` but never gates a render.

    Raw HTML is invisible to the linkcheck builder, which reads a raw node's
    `source` attribute rather than its content, so 75 pages of inlined artwork
    cost the link-check budget nothing.

    :param inline: Render the small variant sitting in a table cell, rather than
        the mark floated atop a manager's own page.
    """
    slug = pool[manager_id].logo
    if not slug:
        return ""
    icon = logo_manifest()["icons"][slug]
    svg = (LOGO_DIR / f"{slug}.svg").read_text(encoding="UTF-8").strip()

    # Size the tag itself, on top of the stylesheet's own rules. The vendored
    # marks carry a `viewBox` and nothing else, so they have no intrinsic size:
    # anywhere the stylesheet does not reach, an unsized one balloons to fill its
    # container instead of rendering as an icon.
    size = 24 if inline else 96
    svg = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)

    # A table cell wraps its content in a paragraph, where a <div> would be
    # invalid markup: the inline variant is a <span>.
    tag = "span" if inline else "div"
    classes = "manager-logo manager-logo-inline" if inline else "manager-logo"
    hex_color = icon["hex"]
    style = f' style="--manager-logo-color: #{hex_color}"'
    label = f"{icon['title']} logo"
    return (
        f'<{tag} class="{classes}"{style} role="img" aria-label="{label}">{svg}</{tag}>'
    )


def manager_label_url(manager_id: str) -> str:
    """Produce the tracker search listing what is still open about a manager.

    Managers sharing an ecosystem share a single label
    ({data}`~meta_package_manager.labels.MANAGER_LABEL_GROUPS`), so the five
    RPM-based wrappers all point at the same `📦 manager: rpm-based` search.

    The query carries `state:open`, without which GitHub answers with every
    issue and pull request ever filed under the label, closed ones included: a
    reader clicking a card's badge is asking what is left to do with the
    manager, and years of settled tickets bury the handful that answers it.

    Only the ASCII specials of the query are percent-encoded, the way GitHub's
    own label links are: escaping the emoji too would triple the length of an
    otherwise readable URL. `quote()` cannot express that on its own, since its
    `safe` set is ASCII-only, so it is applied character by character.
    """
    label = MANAGER_LABELS[manager_id]
    query = "".join(
        char if not char.isascii() else quote(char, safe="")
        for char in f'label:"{label}" state:open'
    )
    return f"{GITHUB_ISSUES_URL}?q={query}"


def _collapse_home(path: str) -> str:
    """Rewrite a path under the builder's home directory as `~`-prefixed.

    SDKMAN resolves its CLI search path from `$SDKMAN_DIR`, defaulting to the
    current user's home: rendering it raw would bake whichever account built the
    docs into the published page.
    """
    home = str(Path.home())
    return f"~{path[len(home) :]}" if path.startswith(home) else path


def manager_card(manager_id: str) -> str:
    """Produce the infobox of a manager's page: its mark atop its key facts.

    A `{card}` floated to the side of the intro prose, in the shape an
    encyclopaedia gives a subject: identity first, then what the manager can do,
    then how `mpm` invokes it, and the two ways off the page last, its tracker
    label and its source file. Everything needing more than a line (platforms in
    full, the operation caveats, transcripts) keeps its own section below, so the
    box stays a summary rather than a second copy of the page.

    The invocation rows are the whole of what used to be a *How `mpm` drives
    <id>* section: binary names and lookup paths, the arguments and environment
    forced on every call. They are one-line facts, so a box row states each one
    more plainly than a bulleted section could, and the rationale for forcing
    them sits next to the lever that overrides them
    ({func}`manager_selection`). What did not fit — the version probe and the
    regexes reading it — kept a section of its own
    ({func}`manager_version_probe`).

    The mark rides in the card's *header* rather than its `:img-top:` option,
    which takes a URI and would emit an `<img>`: an externally referenced SVG
    cannot inherit `currentColor`, so the unfilled marks would render black and
    disappear on the dark theme. The header takes arbitrary content, so the
    inlined SVG of {func}`manager_logo` keeps adapting to both themes.

    A manager with no mark still gets the box, headerless: the facts are the
    point, and the artwork is the bonus.

    The upstream readings sit beside the home page they describe, read from
    {func}`_manager_upstreams`: a star count and a commit date are two short
    facts, and a box of facts is where they belong. The rest of what a forge
    knows about the project is a section of its own further down the page
    ({func}`manager_upstream`), where a dozen live badges fit and the box would
    have burst. Nothing is stated in both places.

    ```{note}
    The newest release is sampled but deliberately not shown. Twelve upstreams
    last released over a year before their newest commit, and the gap means two
    opposite things: `cask` and `chromebrew` are committed to daily and simply
    cut no releases, where `pacaur` and `apm` really are abandoned. One row
    cannot tell those apart, so it reported the most active tap in the pool as
    dead since 2016. The question it was there to answer is already answered
    properly by the curated `unmaintained` flag, which is a maintainer's
    judgement rather than a date inferred from a tag that may never come. The
    commit date stays: it is measured, not interpreted.
    ```
    """
    m = pool[manager_id]
    source_url = manager_source_url(manager_id)
    source_path = source_url.removeprefix(f"{GITHUB_BLOB_URL}/").partition("#")[0]

    facts = [
        ("ID", f"`{manager_id}`"),
        ("Home page", f"<{m.homepage_url}>"),
    ]

    # How the manager's own project is doing, beside the home page it describes.
    # These sat in the manager index as three columns, which asked a reader
    # comparing one tool to scan a hundred rows for it; on the page devoted to
    # that tool they are read where the question is actually asked. Absent for a
    # manager whose upstream cannot be measured, rather than shown empty.
    upstream = _manager_upstreams().get(manager_id, {})
    stars = upstream.get("stars")
    if stars is not None:
        facts.append(("Upstream stars", f"⭐ {stars:,}"))
    if upstream.get("commit"):
        facts.append(("Last commit", upstream["commit"]))
    if m.requirement:
        # Unstyled, like the readme matrix's own Version column: a table cell is
        # data, not the prose the backtick-the-version rule governs. Both angle
        # brackets need escaping here, where that column needs only one: a `<`
        # opens a tag anywhere, but the `>` of a floor requirement also opens a
        # blockquote when it leads a definition, swallowing itself and boxing the
        # version in a quote.
        requirement = (
            _format_requirement(m.requirement).replace("<", r"\<").replace(">", r"\>")
        )
        facts.append(("Version requirement", requirement))
    if m.supports_cooldown:
        facts.append(("Cooldown", "✓"))

    platforms = manager_platforms(manager_id)
    if platforms:
        facts.append(("Platforms", platforms))

    # The same reading as the readme matrix's operation columns, folded into one
    # row: what this manager can do. The Operations section below keeps the full
    # table, with the caveats each one carries.
    supported = [f"`{op.name}`" for op in Operations if implements(m, op)]
    if supported:
        facts.append(("Operations", FACT_SEPARATOR.join(supported)))

    purl_types = sorted(
        {manager_id} | {t for t, ids in PURL_MAP.items() if ids and manager_id in ids},
    )
    facts.append((
        "purl types",
        FACT_SEPARATOR.join(f"`pkg:{t}`" for t in purl_types),
    ))

    # How mpm invokes the tool. Only the CLI names are unconditional: the rest is
    # listed when the manager departs from the plain "run the binary" default.
    cli_label = "CLI names (lookup order)" if len(m.cli_names) > 1 else "CLI name"
    facts.append((
        cli_label,
        FACT_SEPARATOR.join(f"`{name}`" for name in m.cli_names),
    ))
    if m.cli_search_path:
        facts.append((
            "Extra search paths",
            FACT_SEPARATOR.join(f"`{_collapse_home(p)}`" for p in m.cli_search_path),
        ))
    if m.pre_cmds:
        facts.append(("Pre-commands", f"`{' '.join(m.pre_cmds)}`"))
    if m.pre_args or m.post_args:
        # The shape of every invocation, not the bare fragments: one row then
        # shows arguments forced before the command, after it, or both, with no
        # ambiguity about which side each lands on. The placeholder is spelled
        # out, an ellipsis having read as truncated output.
        argv = " ".join((m.cli_names[0], *m.pre_args, "<command>", *m.post_args))
        facts.append(("Every call", f"`{argv}`"))
    if m.extra_env:
        # One per line, where every other repeated row keeps
        # {data}`FACT_SEPARATOR`. An assignment is a long token carrying its own
        # `=`, so three of them dot-separated wrap mid-value in a box this
        # narrow and read as one run-on string. The other rows hold short names
        # that stay whole on a line, which is what makes the dot work there.
        # A raw line break rather than a bullet list: markers and their vertical
        # padding dressed a wrapped value up as an enumeration, in a box whose
        # every other row is a plain run of values.
        facts.append((
            "Forced environment",
            "<br/>".join(f"`{k}={v}`" for k, v in sorted(m.extra_env.items())),
        ))
    if m.timeout is not None:
        facts.append(("Call timeout", f"{m.timeout} seconds"))

    # Last, the two ways out of the page: the tracker and the code. The label
    # renders as a `{bdg-link}` badge, the pill shape GitHub itself gives it,
    # repainted its own color by the stylesheet.
    badge = (
        f"{{bdg-link-secondary}}`{MANAGER_LABELS[manager_id]} "
        f"<{manager_label_url(manager_id)}>`"
    )
    facts.append(("Issues and PRs", badge))
    facts.append(("Source", f"[`{source_path}`]({source_url})"))

    # A definition list, so each fact reads as a labelled row of the box.
    rows = "\n\n".join(f"**{label}**\n: {value}" for label, value in facts)

    logo = manager_logo(manager_id)
    header = f"{logo}\n^^^\n" if logo else ""
    return f"```{{card}}\n:class-card: manager-card\n\n{header}{rows}\n```"


def manager_logo_credits() -> str:
    """Produce the attribution block for every vendored brand mark.

    Rendered into the *Package manager logos* section of `docs/license.md`, the
    project's legal sink, rather than next to the artwork it credits. Twelve of
    the marks carry an attribution-bearing license (Debian's `CC-BY-SA-3.0`,
    NixOS' `CC-BY-4.0`, Fedora's own brand policy, ...), so crediting them is a
    license condition rather than a courtesy. Generating the block from the
    manifest keeps the credit exhaustive on its own, with no hand-maintained
    list to forget when a manager joins or leaves the pool.
    """
    manifest = logo_manifest()
    upstream = manifest["upstream"]

    table = []
    for icon in sorted(manifest["icons"].values(), key=lambda i: i["title"].casefold()):
        license_id = icon["license"]
        license_cell = (
            f"[custom]({license_id})"
            if license_id.startswith("http")
            else f"`{license_id}`"
        )
        table.append([
            f"[{icon['title']}]({icon['source']})",
            ", ".join(f"[`{mid}`](managers/{mid}.md)" for mid in icon["managers"]),
            license_cell,
        ])

    rendered = render_table(
        table,
        headers=["Mark", "Stands for", "License"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "center"],
        disable_numparse=True,
    )
    return (
        f"Brand marks come from [{upstream['name']}]({upstream['url']}) "
        f"`{upstream['version']}`, whose set is `{upstream['license']}` except "
        "where a mark declares otherwise below. Each one is inlined atop its "
        "manager's own page and in the [manager index](managers.md).\n\n"
        f"{rendered}"
    )


def manager_intro(manager_id: str) -> str:
    """Produce the lede of a manager's documentation page.

    Rendered live at Sphinx build time by the first ``{python:render}`` block of
    `docs/managers/<id>.md`. Stacks, in order: an unmaintained-project warning when
    the manager is unmaintained (or a maintenance-watch note for a still-maintained
    but slowing upstream), the manager class's own docstring (whose caveats and
    notes are otherwise only surfaced by the API docs), and a facts list (home
    page, source, version requirement).

    The class docstring is MyST, so it inlines straight into the page, after a
    `{py:currentmodule}` directive letting module-sibling cross-references
    resolve outside their autodoc context. Config-defined managers get the
    description comment atop their bundled TOML definition
    ({func}`_toml_definition_intro`) instead of their synthesized class
    docstring, with a pointer to the file as fallback.
    """
    m = pool[manager_id]
    blocks = []

    if m.unmaintained:
        blocks.append(
            "```{warning}\n"
            f"`{manager_id}` is unmaintained. {m.unmaintained_message}\n"
            "```",
        )
    elif m.maintenance_note:
        blocks.append(
            f"```{{note}}\n{m.maintenance_note}\n```",
        )

    # After the admonition, never before: the card floats, and a float placed
    # above an admonition overlaps its background box instead of clearing it.
    blocks.append(manager_card(manager_id))

    source_url = manager_source_url(manager_id)

    if getattr(m, "definition_source", None):
        blocks.append(
            _toml_definition_intro(m.definition_source)
            or f"Defined as a [bundled TOML configuration]({source_url}) rather "
            "than a Python class.",
        )
    else:
        docstring = type(m).__dict__.get("__doc__")
        assert docstring, f"Manager class of {manager_id} has no docstring."
        blocks.append(
            f"```{{py:currentmodule}} {type(m).__module__}\n```\n\n"
            f"{inspect.cleandoc(docstring)}",
        )

    return "\n\n".join(blocks)


def _ecosystem_siblings(manager_id: str) -> list[str]:
    """Pool managers sharing a purl ecosystem with the given one.

    Two managers are siblings when {data}`~meta_package_manager.specifier.PURL_MAP`
    maps them to at least one common purl type: `uv`, `pip` and `pipx` all
    resolve `pkg:pypi`, so they surface each other. Used by
    {func}`manager_augments` to name the relatable neighbors a single-ecosystem
    user already juggles. Sorted, self excluded; empty for a manager whose purl
    types no other pool manager shares (`cargo`, `gem`).
    """
    pool_ids = set(pool.all_manager_ids)
    types = {t for t, ids in PURL_MAP.items() if ids and manager_id in ids}
    siblings: set[str] = set()
    for purl_type, ids in PURL_MAP.items():
        if purl_type in types and ids:
            siblings |= set(ids) & pool_ids
    return sorted(siblings - {manager_id})


def _augment_gains(manager_id: str) -> list[str]:
    """List the capabilities `mpm` backfills for this manager specifically.

    One entry per selective augmentation the manager relies on, read from the
    same capability introspection that feeds {func}`augmentations_table`:
    synthesized full `upgrade --all`, synthesized orphan sweep, and refiltered
    `--exact`/`--extended` search. Each is phrased as what `mpm` adds, never as
    a native limitation: the introspection proves `mpm` synthesizes the
    operation for the interface it drives, not that the tool as a whole lacks it
    (the `uv` id drives uv's `pip` interface, while `uvx` drives `uv tool`,
    which does ship a native `upgrade --all`). Empty for a feature-complete
    manager.
    """
    m = pool[manager_id]
    gains = []
    if upgrade_all_is_synthesized(m):
        gains.append(
            "a one-command `upgrade --all` that refreshes every outdated package "
            "in a single run",
        )
    if cleanup_orphan_is_synthesized(m):
        gains.append(
            "a one-command `cleanup --orphans` that removes every orphaned "
            "dependency at once",
        )
    exact = exact_search_is_synthesized(m)
    extended = extended_search_is_synthesized(m)
    if exact and extended:
        gains.append(
            "`--exact` and `--extended` search, to narrow to exact names or match "
            "descriptions",
        )
    elif exact:
        gains.append("`--exact` search, to narrow results to exact names")
    elif extended:
        gains.append("`--extended` search, to match against package descriptions")
    return gains


def manager_augments(manager_id: str) -> str:
    """Produce the "What `mpm` adds" section of a manager's documentation page.

    Rendered live at Sphinx build time by the second ``{python:render}`` block
    of `docs/managers/<id>.md`, right after the intro: the pitch for a reader
    who already knows the native tool. Stacks the manager-specific backfills
    ({func}`_augment_gains`), the cross-manager reach naming the ecosystem
    neighbors the reader already juggles ({func}`_ecosystem_siblings`), and the
    universal augmentations shared by every managed tool. Every claim describes
    what `mpm` does, derived from the capability introspection, so the section
    can neither overstate a native limitation nor drift from the code. Points at
    `docs/augmentations.md` for the full, cross-manager treatment.
    """
    gains = _augment_gains(manager_id)

    siblings = _ecosystem_siblings(manager_id)
    peers = (
        ", ".join(f"`{sibling}`" for sibling in siblings)
        + " and any other manager you run"
        if siblings
        else "every other manager you run"
    )
    reach_body = (
        f"`mpm installed` and `mpm outdated` cover `{manager_id}` alongside {peers} "
        "in one table, `mpm upgrade --all` updates them together, and `mpm sbom` "
        "exports the whole machine as one bill of materials."
    )
    universal = (
        "Every `mpm` command also gains `--dry-run` and `--plan` previews, "
        "cross-scheme version comparison and purl identifiers. See "
        "[manager augmentations](../augmentations.md) for how each one is built."
    )

    if gains:
        # A lone gain reads as a sentence: a bulleted list of one item is a list
        # in shape only, and the bullet claims a plurality that is not there.
        if len(gains) == 1:
            lede = f"Through `mpm`, `{manager_id}` gains {gains[0]}."
        else:
            bullets = "\n".join(f"- {gain}" for gain in gains)
            lede = f"Through `mpm`, `{manager_id}` gains:\n\n{bullets}"
        reach = (
            f"Bigger still, `mpm` reaches across every manager at once: {reach_body}"
        )
        return f"{lede}\n\n{reach}\n\n{universal}"
    reach = (
        f"`mpm` reaches across every manager at once, not `{manager_id}` alone: "
        f"{reach_body}"
    )
    return f"{reach}\n\n{universal}"


ROSETTA_OPERATIONS: tuple[tuple[str, str, str, bool], ...] = (
    # (manager method, task label, mpm-command template, whether it takes an operand).
    ("installed", "List what's installed", "mpm --{id} installed", False),
    ("outdated", "List outdated packages", "mpm --{id} outdated", False),
    ("search", "Search for a package", "mpm --{id} search {op}", True),
    ("install", "Install a package", "mpm install pkg:{id}/{op}", True),
    ("upgrade_one_cli", "Upgrade one package", "mpm --{id} upgrade {op}", True),
    ("upgrade_all_cli", "Upgrade everything", "mpm --{id} upgrade --all", False),
    ("remove", "Remove a package", "mpm remove pkg:{id}/{op}", True),
    ("orphans", "List orphaned dependencies", "mpm --{id} orphans", False),
    ("cleanup_cache", "Clear caches", "mpm --{id} cleanup --cache", False),
    ("doctor_cli", "Run health checks", "mpm --{id} doctor", False),
)
"""Rows of the Rosetta table, in display order.

Each tuple is the native operation method, its task label, the `mpm` command
template and whether the command takes a package operand. The native call is
harvested from the method's own documented sample; a row is dropped when
nothing is harvestable (see {func}`manager_rosetta`).
"""

_ROSETTA_TOML_MEMBER = {
    "upgrade_one_cli": "upgrade_one",
    "upgrade_all_cli": "upgrade_all",
    "doctor_cli": "doctor",
}
"""Methods whose name differs from their operation key in a bundled TOML definition."""


def _native_invocation(manager, member: str) -> tuple[list[str], str | None] | None:
    """Return the native command tokens and operand documented for an operation.

    The command is read from the manager's own captured sample, so it is exactly
    what the tool is invoked with: a bundled TOML manager's operation spec
    (`cli` plus `args`), or the first documented `shell-session` block of a
    class-based manager's method. The MRO is walked so an operation defined on a
    shared base (`Homebrew` for `brew`/`cask`) is found, not just the leaf class
    body. The forced arguments {func}`manager_card` lists separately are
    stripped to leave the recognizable native form, a trailing `| jq`-style
    illustration is dropped, and the operand is the last non-flag token. `None`
    when the operation documents no command.
    """
    forced = set(manager.pre_args) | set(manager.post_args)

    tokens = None
    source = getattr(manager, "definition_source", None)
    if source:
        operations = _toml_definition(source)["mpm"]["managers"][manager.id].get(
            "operations",
            {},
        )
        spec = operations.get(_ROSETTA_TOML_MEMBER.get(member, member))
        if spec:
            tokens = [spec.get("cli", manager.cli_names[0]), *spec.get("args", ())]
    else:
        for klass in type(manager).__mro__:
            try:
                blocks = class_display_blocks(klass).get(member, ())
            except (TypeError, OSError):
                continue  # A built-in base (object) has no source to harvest.
            commands = block_commands(blocks[0]) if blocks else []
            if commands:
                tokens = commands[0]
                break

    if not tokens:
        return None
    if "|" in tokens:  # Drop a `... | jq` illustration, keep the real command.
        tokens = tokens[: tokens.index("|")]
    core = [t for t in tokens if t not in forced]
    if not core:
        return None
    return core, _example_operand(manager, core)


def _example_operand(manager, core: list[str]) -> str | None:
    """Pick the example package operand out of a documented command.

    Best-effort heuristics over the audited failure classes; `None` (rendered as
    a placeholder) whenever the guess would mislead:

    - Candidates are the non-flag tokens, stripped of shell quoting, skipping
      `sudo`, the binary and any token restating the manager itself (winget's
      `--source winget` would otherwise shadow the package id).
    - Two candidates sitting in flag-value position means the package id cannot
      be told from the other value (PowerShell's `-Name X -Scope CurrentUser`).
    - The operand is the last candidate, except a version-looking tail hands
      over to the token before it (`asdf install nodejs 20.10.0`) when that one
      is not the leading subcommand: `mas install 945397020` keeps its numeric
      id.
    - A glob or quote residue is never a usable example (conda's `"*pytz*"`).
    """
    excluded = set(manager.cli_names) | {manager.id, "sudo"}
    candidates = []
    for position, token in enumerate(core):
        cleaned = token.strip("'\"")
        if not cleaned or cleaned.startswith("-") or cleaned in excluded:
            continue
        flag_value = position > 0 and core[position - 1].startswith("-")
        candidates.append((cleaned, flag_value))
    if not candidates:
        return None
    if sum(flag_value for _, flag_value in candidates) >= 2:
        return None
    operand = candidates[-1][0]
    if operand[0].isdigit() and len(candidates) >= 3:
        operand = candidates[-2][0]
    if any(char in operand for char in "*?\"'"):
        return None
    return operand


def manager_rosetta(manager_id: str) -> str:
    """Produce the command-mapping section of a manager's documentation page.

    A Rosetta table for a reader fluent in the native tool: each operation as
    the native call `mpm` makes (harvested by {func}`_native_invocation`) beside
    the uniform `mpm` command. Native DSL placeholders (`{package_id}`) are
    rewritten to `<pkg>`-style angle brackets, and a manager documenting fewer
    than three operations yields nothing (the section is then omitted from its
    stub), so the table appears only where it is useful. A closing note points
    at `--dry-run`, since the table lists every invocation the flag applies to.
    """
    m = pool[manager_id]
    rows = []
    for member, task, mpm_template, has_operand in ROSETTA_OPERATIONS:
        native = _native_invocation(m, member)
        if native:
            core, operand = native
            native_cell = "`" + " ".join(core) + "`"
        elif member == "upgrade_all_cli" and upgrade_all_is_synthesized(m):
            native_cell, operand = "—", None  # No single native command.
        else:
            continue
        operand = operand if (has_operand and operand) else "<pkg>"
        mpm_cell = "`" + mpm_template.format(id=manager_id, op=operand) + "`"
        # Rewrite DSL operand placeholders (`{package_id}`) to angle brackets.
        native_cell = re.sub(r"\{(\w+)\}", r"<\1>", native_cell)
        mpm_cell = re.sub(r"\{(\w+)\}", r"<\1>", mpm_cell)
        rows.append([task, native_cell, mpm_cell])

    if len(rows) < 3:
        return ""

    table = render_table(
        rows,
        headers=["To…", f"With `{manager_id}`", "With `mpm`"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left", "left"],
        disable_numparse=True,
    )
    intro = (
        f"You already know `{manager_id}`: each operation maps one-to-one onto "
        "`mpm`, in an interface shared by every manager."
    )
    dry_run = (
        "Prefix any command above with [`--dry-run`](../augmentations.md) to "
        "simulate the underlying manager calls without touching the system: the "
        "safe way to watch what `mpm` would do before trusting it."
    )
    return f"{intro}\n\n{table}\n\n{dry_run}"


def manager_recipes(manager_id: str) -> str:
    """Produce the recipes section of a manager's documentation page.

    A few copy-paste jobs a reader would otherwise script around the native
    tool: snapshot and restore, an SBOM export, and (when the manager implements
    it) a CI health gate. Each is a real `mpm` invocation, gated on the
    operation being available so no unsupported command is shown.
    """
    m = pool[manager_id]
    lines = [
        (
            f"- Snapshot and clone a machine: `mpm --{manager_id} dump "
            f"{manager_id}.toml`, then `mpm restore {manager_id}.toml` on the next one."
        ),
    ]
    if m.brewfile_entry_type:
        lines.append(
            f"- Export a Brewfile entry instead: `mpm --{manager_id} dump "
            "--brewfile Brewfile`.",
        )
    lines.append(
        f"- Export a compliance SBOM: `mpm --{manager_id} sbom` (CycloneDX by "
        "default, `--spdx` for SPDX).",
    )
    if implements(m, Operations.doctor):
        lines.append(
            f"- Gate CI on health: `mpm --{manager_id} doctor` relays {m.name}'s "
            "own diagnosis and exits non-zero on trouble.",
        )
    intro = (
        f"A few jobs you would otherwise script around `{manager_id}`, one `mpm` "
        "command each:"
    )
    return f"{intro}\n\n" + "\n".join(lines)


def _platform_coverage(p_obj, platforms: frozenset) -> tuple[str, str | None] | None:
    """Return the icon and partial-coverage annotation of a platform entry.

    `None` when the manager covers no member of the entry. The annotation is
    `None` on full coverage, and otherwise spells out whichever side is
    shorter: the covered members (`Exherbo Linux only`) or the missing ones
    (`except WSL1, WSL2`), so a manager backing most of a large group stays
    readable.
    """
    members = set(extract_members(p_obj))
    covered = members & platforms
    if not covered:
        return None
    annotation = None
    if covered != members:
        missing = members - covered
        side, template = (
            (missing, "except {}")
            if len(missing) < len(covered)
            else (covered, "{} only")
        )
        names = ", ".join(sorted((p.name for p in side), key=str.casefold))
        annotation = template.format(names)
    return p_obj.icon, annotation


def manager_platforms(manager_id: str) -> str:
    """Produce the platform row of a manager's infobox.

    Every supported {data}`~meta_package_manager.platforms.MAIN_PLATFORMS` entry
    on one line, with {func}`_platform_coverage`'s annotation when the manager
    only backs part of a multi-platform group: the readme's operation matrix
    renders an all-or-nothing icon, this row is where partial support is spelled
    out.

    Entries are separated the same way as every other repeated infobox value,
    which also keeps a coverage annotation from running into the platform that
    follows it.
    """
    m = pool[manager_id]
    entries = []
    for p_obj in MAIN_PLATFORMS:
        coverage = _platform_coverage(p_obj, m.platforms)
        if coverage is None:
            continue
        icon, annotation = coverage
        # Non-breaking too: an icon stranded at the end of a line, with its name
        # starting the next, reads as two separate platforms.
        entry = f"{icon}\u00a0{p_obj.name}"
        if annotation:
            entry += f" ({annotation})"
        entries.append(entry)
    return FACT_SEPARATOR.join(entries)


def manager_operations(manager_id: str) -> str:
    """Produce the operations table of a manager's documentation page.

    One row per member of {class}`~meta_package_manager.capabilities.Operations`,
    in enum order. The *Notes* column points out the capabilities `mpm`
    synthesizes on top of the native CLI, mirroring the introspection of
    {func}`augmentations_table`, and is dropped entirely for the managers
    needing no backfill.
    """
    m = pool[manager_id]
    table = []
    for op in Operations:
        supported = implements(m, op)
        note = ""
        if supported and op is Operations.upgrade_all and upgrade_all_is_synthesized(m):
            note = "[backfilled by `mpm`](../augmentations.md)"
        elif supported and op is Operations.search:
            missing = [
                label
                for label, synthesized in (
                    ("exact", exact_search_is_synthesized(m)),
                    ("extended", extended_search_is_synthesized(m)),
                )
                if synthesized
            ]
            if missing:
                note = (
                    f"{' and '.join(missing)} search "
                    "[backfilled by `mpm`](../augmentations.md)"
                )
        elif (
            supported
            and op is Operations.remove
            and implements_method(m, "remove_orphan")
        ):
            note = "`--orphans` also drops the package's orphaned dependencies"
        elif supported and op is Operations.cleanup:
            if implements_method(m, "cleanup_orphan"):
                note = "`--orphans` runs the system-wide orphan sweep"
            elif cleanup_orphan_is_synthesized(m):
                note = "`--orphans` sweep [backfilled by `mpm`](../augmentations.md)"
        table.append([f"`{op.name}`", "✓" if supported else "", note])

    headers = ["Operation", "Supported", "Notes"]
    colalign = ["left", "center", "left"]
    if not any(row[2] for row in table):
        table = [row[:2] for row in table]
        headers = headers[:2]
        colalign = colalign[:2]

    return render_table(
        table,
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=colalign,
        disable_numparse=True,
    )


def _python_regex_literal(pattern: str) -> str:
    """Render a regex as the Python raw-string literal it is declared as in source.

    Gives the version-probe block of the manager pages `python` highlighting
    (Pygments ships no standalone regex lexer). Falls back to `repr()` —
    escaped, non-raw — for the rare pattern a raw literal cannot express: one
    containing both quote characters, or ending with a backslash.
    """
    if not pattern.endswith("\\"):
        if '"' not in pattern:
            return f'r"{pattern}"'
        if "'" not in pattern:
            return f"r'{pattern}'"
    return repr(pattern)


def manager_version_probe(manager_id: str) -> str:
    """Produce the version-probe section of a manager's documentation page.

    The command `mpm` runs to read the manager's version, the output that
    command was captured producing, and the regexes pulling the version out of
    it. The transcript comes from the `[samples.version]` fixture of a bundled
    TOML manager or the `version_regexes` docstring of a class-based one; the
    per-operation samples render in the reference-traces section
    ({func}`manager_traces`).

    The rest of the invocation plumbing (binary names and lookup paths, forced
    arguments and environment) reads as one-line facts, so it sits in the page's
    infobox ({func}`manager_card`) rather than in a section here.
    """
    m = pool[manager_id]

    source = getattr(m, "definition_source", None)
    if source:
        doc = _toml_definition(source)
        version_sample = doc.get("samples", {}).get("version", {}).get("output")
    else:
        version_sample = version_trace(type(m))

    probe = " ".join(((m.version_cli or m.cli_names[0]), *m.version_cli_options))
    regex_suffix = (
        " the first of these regular expressions to match"
        if len(m.version_regexes) > 1
        else ""
    )
    regex_fence = _fenced(
        "\n".join(_python_regex_literal(regex) for regex in m.version_regexes),
        "python",
    )

    parts = []
    if version_sample:
        transcript = version_sample.strip("\n")
        parts.append("The version is probed by running:")
        parts.append(_fenced(f"$ {probe}\n{transcript}", "shell-session"))
        parts.append(f"and extracted with{regex_suffix}:")
    else:
        parts.append(
            f"The version is extracted from the output of `{probe}` "
            f"with{regex_suffix}:",
        )
    parts.append(regex_fence)

    return "\n\n".join(parts)


def manager_selection(manager_id: str) -> str:
    """Produce the selection-and-configuration section of a manager's page.

    The levers to control this manager's participation: the one-run
    `--no-<id>` deselector, the persistent selection toggle in the
    configuration file, and a per-manager override block for tuning how `mpm`
    drives it. The command-to-command mapping lives in the Rosetta section
    ({func}`manager_rosetta`); this one points at the fuller
    [configuration](configuration.md) and [overrides](overrides.md) references
    rather than restating them.

    A manager whose calls carry forced arguments or environment variables
    (listed in the infobox by {func}`manager_card`) gets the rationale for them
    here, where the lever that overrides them is.
    """
    m = pool[manager_id]
    select = (
        f"Deselect `{manager_id}` for a single run with `--no-{manager_id}`, or "
        "persist the choice in your [configuration](../configuration.md):"
    )
    select_toml = _fenced(f"[mpm]\n{manager_id} = false", "toml")
    forced = (
        "The arguments and environment variables listed in the box atop this "
        f"page are forced on every `{manager_id}` call, so runs stay quiet, "
        "non-interactive and reproducible: the defaults you would set in CI "
        "anyway."
        if m.pre_args or m.post_args or m.extra_env
        else ""
    )
    tune = (
        "Keep it enabled but tune how `mpm` drives it with a "
        "[per-manager override](../overrides.md):"
    )
    tune_toml = _fenced(f"[mpm.managers.{manager_id}]\ntimeout = 900", "toml")
    template = (
        f"`mpm config-template {manager_id}` prints every overridable attribute "
        "as a ready-to-paste block."
    )
    parts = [select, select_toml, forced, tune, tune_toml, template]
    return "\n\n".join(filter(None, parts))


def manager_sudo(manager_id: str) -> str:
    """Produce the privilege-escalation section of a manager's documentation page.

    States which escalation policy applies (system-wide `sudo` wrapping,
    internal escalation, or none) and how to flip it, deriving everything from
    the escalation attributes so the page can never contradict the code. For
    config-defined managers that do not escalate internally, the operations
    marked `sudo = true` in the bundled TOML definition are listed by name.
    """
    m = pool[manager_id]
    if m.internal_sudo:
        policy = (
            f"{m.name} runs `sudo` from inside its own commands: `mpm` never "
            "wraps it, keeps an already-warm credential cache alive for those "
            "internal escalations, and warns when a mutating call goes silent "
            "on a terminal with a cold cache, since a password prompt may be "
            "hiding in the stream."
        )
    elif m.default_sudo:
        policy = (
            "System-wide manager: `mpm` wraps its privileged operations in "
            "`sudo` out of the box. Instead of letting the tool prompt "
            "mid-run, `mpm` primes the credential cache up-front, with a "
            "single branded password prompt at most. Turn escalation off for "
            "rootless setups with `--no-sudo` or the per-manager "
            "[`sudo` override](../overrides.md)."
        )
    else:
        policy = (
            "`mpm` runs this manager as the current user and never prepends "
            "`sudo` by default. Flip the policy for its privileged operations "
            "with `--sudo` or the per-manager [`sudo` override](../overrides.md)."
        )

    parts = [policy]
    source = getattr(m, "definition_source", None)
    if source and not m.internal_sudo:
        operations = _toml_definition(source)["mpm"]["managers"][manager_id].get(
            "operations",
            {},
        )
        # Map the definition-schema operation names to the user-facing ones.
        privileged = sorted(
            {"upgrade_one": "upgrade"}.get(op, op)
            for op, spec in operations.items()
            if spec.get("sudo")
        )
        if privileged:
            ops_list = ", ".join(f"`{op}`" for op in privileged)
            plural = "s" if len(privileged) > 1 else ""
            parts.append(f"Root is required for its {ops_list} operation{plural}.")
        else:
            parts.append("None of its operations needs root.")
    parts.append("See [privilege escalation](../sudo.md) for the full policy.")
    return "\n\n".join(parts)


def manager_concurrency(manager_id: str) -> str:
    """Produce the concurrency section of a manager's documentation page.

    Renders the manager's {class}`~meta_package_manager.dispatch.LockFamily`: the
    siblings `mpm` will not let it overlap with, and that family's own reason for
    contending. A manager in no family drives state nothing else touches, has
    nothing to say here, and {func}`manager_page` drops the section entirely.

    ```{note}
    Derived from {data}`~meta_package_manager.dispatch.SHARED_LOCK_FAMILIES` rather
    than restated, so a family gained or lost moves every affected page at once. It
    is the same constant {func}`~meta_package_manager.dispatch.merge_into_lock_lanes`
    serializes on, which is what keeps the pages from promising a guarantee the
    dispatcher does not implement.
    ```
    """
    family = next(
        (f for f in SHARED_LOCK_FAMILIES if manager_id in f.members),
        None,
    )
    if family is None:
        return ""
    siblings = [
        f"[`{sibling}`]({sibling}.md)"
        for sibling in sorted(family.members - {manager_id})
    ]
    joined = (
        siblings[0]
        if len(siblings) == 1
        else f"{', '.join(siblings[:-1])} or {siblings[-1]}"
    )
    return "\n\n".join((
        f"`mpm` never runs `{manager_id}` at the same time as {joined}: "
        f"{family.contention}. Each mutating operation waits for the previous one, "
        "even with a higher `--jobs`, while managers outside this group keep "
        "running in parallel.",
        "Only mutations are held back. The read-only queries (`installed`, "
        "`outdated`, `search`) take no backend lock and stay fully concurrent.",
    ))


def _fact_block(facts: list[str]) -> str:
    """Render labelled facts as a bullet list, or as a plain line when alone.

    A list of one item is a list in shape only: the bullet promises siblings
    that never come. A manager whose cooldown row holds nothing but a status
    gets that status as a line of its own instead.
    """
    if len(facts) == 1:
        return facts[0]
    return "\n".join(f"- {fact}" for fact in facts)


def manager_cooldown(manager_id: str) -> str:
    """Produce the cooldown section of a manager's documentation page.

    Reuses the manager's row from the hand-curated "Supported managers" table
    of `docs/cooldown.md` (status, native mechanism, upstream reference), so
    the page and the cooldown overview can never diverge. Tops it with the
    enforcement facts derived from the manager's declarations: the injected
    environment variable when `mpm` drives a native gate, or the fail-closed
    skip applying to everyone else.

    Closes on the registry the manager resolves against, from the same page's
    "Retraction paths by registry" table. A gate that no withdrawal ever
    follows delays a compromised release instead of avoiding it, so whether
    the registry can pull a bad version belongs next to whether `mpm` can gate
    the manager at all.
    """
    m = pool[manager_id]
    row = _cooldown_status(manager_id)

    parts = []
    if m.supports_cooldown:
        if m.cooldown_env_var:
            parts.append(
                "`mpm` natively enforces its [release-age cooldown](../cooldown.md) "
                f"on {m.name}, injecting the `{m.cooldown_env_var}` environment "
                "variable on every call. Point it at a window "
                f"(`mpm --cooldown 7 --{manager_id} upgrade --all`) to skip anything "
                "published in the last 7 days: a guard against a compromised or "
                "yanked fresh release landing before anyone notices.",
            )
        else:
            parts.append(
                "`mpm` enforces its [release-age cooldown](../cooldown.md) on "
                f"{m.name} with its own per-package probe: before an install or "
                "upgrade, it reads the publication date of the package's latest "
                "release and holds back any release younger than the window "
                f"(`mpm --cooldown 7 --{manager_id} upgrade --all` skips anything "
                "published in the last 7 days): a guard against a compromised or "
                "yanked fresh release landing before anyone notices.",
            )
    elif row:
        parts.append(
            f"State of {m.name}'s release-age gating, from the "
            "[cooldown support table](../cooldown.md#supported-managers):",
        )
    else:
        parts.append(
            "Not yet assessed in the "
            "[cooldown support table](../cooldown.md#supported-managers).",
        )
    if row:
        status, mechanism, reference = row
        facts = [f"Status: {status}"]
        if mechanism not in EMPTY_CELLS:
            facts.append(f"Mechanism: {mechanism}")
        if reference not in EMPTY_CELLS:
            facts.append(f"Reference: {reference}")
        parts.append(_fact_block(facts))

    retraction = _retraction_status(manager_id)
    if retraction:
        registry, withdrawal, publish_date = retraction
        parts.append(
            "A cooldown only pays off where a compromised release can be "
            "withdrawn while the clock runs, and can only be emulated where the "
            "registry dates its releases. From the [retraction table]"
            "(../cooldown.md#retraction-paths-by-registry):",
        )
        facts = [f"Registry: {registry}"]
        if withdrawal not in EMPTY_CELLS:
            facts.append(f"Retraction: {withdrawal}")
        if publish_date not in EMPTY_CELLS:
            facts.append(f"Publish date: {publish_date}")
        parts.append(_fact_block(facts))

    if not m.supports_cooldown and any(
        implements(m, op)
        for op in (Operations.install, Operations.upgrade, Operations.upgrade_all)
    ):
        parts.append(
            "With `--cooldown` set, `mpm` skips this manager's install and "
            "upgrade operations rather than run them unguarded (fail-closed); "
            "`--cooldown best-effort` opts back in.",
        )
    return "\n\n".join(parts)


def manager_traces(manager_id: str) -> str:
    """Produce the reference-traces section of a manager's documentation page.

    Raw native outputs replayed as terminal transcripts: the reference `mpm`'s
    parsers were written against. Surfacing them lets users seasoned in the
    native tool spot wrong assumptions, or output formats a newer release has
    since changed. The captures come from the bundled TOML definition's
    `[samples]` fixtures for a config-defined manager, or from the
    `shell-session` blocks documented in a class-based manager's
    `installed`/`outdated` docstrings (harvested by
    {func}`~meta_package_manager.docstring_corpus.literal_blocks`, the same
    literal blocks the corpus test round-trips). Empty for managers without such
    samples (the section is then omitted from the stub); the version probe
    transcript keeps its own section ({func}`manager_version_probe`), next to
    the regexes consuming it.
    """
    m = pool[manager_id]
    source = getattr(m, "definition_source", None)
    if source:
        doc = _toml_definition(source)
        samples = doc.get("samples", {})
        operations = doc["mpm"]["managers"][manager_id].get("operations", {})
        fences = []
        for op in Operations:
            spec = operations.get(op.name, {})
            for sample in samples.get(op.name, ()):
                command = " ".join((
                    spec.get("cli", m.cli_names[0]),
                    *spec.get("args", ()),
                ))
                output = sample["output"].strip("\n")
                fences.append(_fenced(f"$ {command}\n{output}", "shell-session"))
        source_label = "bundled definition"
    else:
        fences = [
            _fenced(block, block_language(block))
            for _, _, block in literal_blocks(
                type(m), ("installed", "outdated", "orphans")
            )
        ]
        source_label = "manager source"
    if not fences:
        return ""
    intro = (
        "Raw native outputs captured in the "
        f"[{source_label}]({manager_source_url(manager_id)}): the reference "
        f"`mpm`'s parsers were written against. If you know {m.name} well and a "
        "transcript below looks wrong, or a newer release changed its output "
        f"format, [report it]({GITHUB_ISSUES_URL})."
    )
    outro = (
        "Feed any of these through `mpm` and the raw output becomes one uniform "
        "table, the same shape for every manager: filter it, project columns, or "
        f"export it (`mpm --{manager_id} installed --output json`, or `csv`, "
        "`toml`, `yaml`), each package carrying a purl and a version comparable "
        "across managers."
    )
    return "\n\n".join((intro, *fences, outro))


class ChangelogEntry(NamedTuple):
    """One changelog bullet, resolved to the release that shipped it."""

    version: str
    """Package version of the release the entry sits under."""

    date: str
    """Release date, or `unreleased` for the development section."""

    url: str
    """Comparison URL carried by the release heading."""

    flag: str | None
    """Bold marker opening the entry (`Breaking`), or `None` for a plain one."""

    text: str
    """Entry body, verbatim from the changelog."""


CHANGELOG_RELEASE = re.compile(
    r"^## \[`(?P<version>[^`]+)` \((?P<date>[^)]+)\)\]\((?P<url>[^)]+)\)",
    re.MULTILINE,
)
"""Release heading of `changelog.md`: its version, its date and its comparison URL.

The development section is headed by the version it will ship as, suffixed
`.devN`, and dated `unreleased` until it does.
"""


@cache
def changelog_releases() -> dict[str, tuple[str, str]]:
    """Index `changelog.md` by release, newest first: version to date and URL.

    Keyed on the bare version, so the `.devN` suffix of the development heading
    comes off and a page naming the release in preparation resolves to it.

    The URL is the comparison link the heading carries, because a release
    heading has no anchor to link to instead. `myst_heading_slug_func` is
    `docutils.nodes.make_id`, which strips a heading holding no letter down to
    the empty string, so `` `7.6.0` (2026-08-10) `` yields nothing at all. That
    is what {func}`scope_changelog` links each of its releases by, and what the
    `mpm-release` role of `docs/conf.py` renders a {data}`DECLINE_STAMP` as.
    """
    changelog = (PROJECT_ROOT / "changelog.md").read_text(encoding="UTF-8")
    return {
        re.sub(r"\.dev\d+$", "", match["version"]): (match["date"], match["url"])
        for match in CHANGELOG_RELEASE.finditer(changelog)
    }


@cache
def _changelog_entries() -> dict[str, tuple[ChangelogEntry, ...]]:
    """Index `changelog.md` by the scope tags its entries carry.

    Every changelog bullet opens with a comma-separated scope tag, and
    `test_changelog` already enforces that vocabulary: tags are sorted,
    deduplicated and drawn from the pool IDs plus the platform IDs and the
    `mpm`, `bar-plugin` and `gnome-shell` scopes. So the changelog needs no
    heuristic mining, only a read: every scope keys the entries naming it, and
    a multi-scope entry is filed under each one it names.

    Indexing every tag, in place of the pool alone, is what lets a page other
    than a manager's read its own history: the two desktop frontends do,
    through {func}`scope_changelog`. A scope no page renders costs one key.

    Entries keep their changelog order, which is newest release first and
    curated within a release. Cached: one parse feeds every page.
    """
    bullet = re.compile(
        r"^- (?:\*\*(?P<flag>[A-Za-z]+):\*\* )?"
        r"\[(?P<scopes>[a-z0-9,\-]+)\] (?P<text>.+)$",
    )

    entries: dict[str, list[ChangelogEntry]] = {}
    version = date = url = ""
    changelog = (PROJECT_ROOT / "changelog.md").read_text(encoding="UTF-8")
    # The older releases hard-wrap their bullets, so an entry's text can span
    # several lines. Fold every continuation back into its own bullet before
    # matching, or the entry lands on the manager page cut mid-sentence. An
    # indented line opening a nested bullet is a sub-item, not a continuation:
    # it stays out, as it always has.
    changelog = re.sub(r"\n[ \t]+(?![-*+] )(?=\S)", " ", changelog)
    for line in changelog.splitlines():
        heading = CHANGELOG_RELEASE.match(line)
        if heading:
            version, date, url = heading.group("version", "date", "url")
            continue
        match = bullet.match(line)
        if not match:
            continue
        for scope in match["scopes"].split(","):
            entries.setdefault(scope, []).append(
                ChangelogEntry(version, date, url, match["flag"], match["text"]),
            )
    return {scope: tuple(items) for scope, items in entries.items()}


def manager_upstream(manager_id: str) -> str:
    """Produce the upstream-project section of a manager's documentation page.

    The readings the benchmark tables carry for `mpm` and its peers, asked of
    each wrapped manager's own repository: its activity, its popularity and the
    metadata of its newest release, in the three groups those tables use.
    Grouped rather than strung out, so a dozen images read as three answers.

    Live badges here, where {func}`manager_card` states its two figures from the
    weekly sample, and the split is the point. A sampled date is written into
    the page at build time and starts ageing immediately: `pip` tagging a
    release the day after a sample leaves the page a week behind, and a page
    nobody rebuilds stays wrong for as long as that lasts. A badge is fetched
    when the page is read, so it cannot be stale, and shields renders a date as
    the distance to today (*last tuesday*, *january 2016*) coloured by age,
    which is the reading a reader wanted from a bare date anyway. What the badge
    cannot do is be there at all for a forge with no such endpoint, or be
    trusted to distinguish an unreleased project from a missing one, which is
    what {data}`UPSTREAM_BADGES` and {attr}`UpstreamBadge.release_source` settle
    from the sample.

    ```{note}
    The benchmark's *Distribution* section has no counterpart here. Its rows
    count downloads and repology packaging for `mpm`'s own release channels,
    and asking the same of a wrapped manager would need a hand-kept repology
    project id per manager, guessable for none of them: `brew` is `homebrew`
    there, `uvx` is not a project at all.
    ```
    """
    upstream = _manager_upstreams().get(manager_id, {})
    repo_url = upstream.get("repo")
    if not repo_url:
        return ""

    parsed = urlparse(repo_url)
    forge = UPSTREAM_FORGES.get(parsed.netloc)
    if forge is None:
        return ""
    family, instance_param = forge
    repo_path = parsed.path.strip("/")

    # The instance is named as a query parameter for every forge but GitHub, so
    # a project on Alpine's own GitLab is read through the same service as one
    # on the public instance.
    params = [f"style={BADGE_STYLE}"]
    if instance_param:
        instance = quote(f"{parsed.scheme}://{parsed.netloc}", safe="")
        params.insert(0, f"{instance_param}={instance}")
    query = "&".join(params)

    rows = []
    for group, badges in groupby(UPSTREAM_BADGES[family], key=lambda b: b.group):
        cells = [
            f"![{badge.label}]({SHIELDS_URL}/{family}/"
            f"{badge.path.format(repo=repo_path)}?{query})"
            for badge in badges
            if badge.release_source in (None, upstream.get("release_source"))
        ]
        if cells:
            rows.append([group, " ".join(cells)])
    if not rows:
        return ""

    return render_table(
        rows,
        # The repository names the column it heads, as the benchmark's own
        # tables are headed by the project each column reads.
        headers=["Metrics", f"[`{repo_path}`]({repo_url})"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left"],
        disable_numparse=True,
    )


def scope_changelog(scope: str) -> str:
    """Produce the release-history section of a page, from its changelog scope.

    Every change `mpm` shipped under that scope, grouped by the release that
    carried it, newest first. A manager page passes its own ID; the SwiftBar
    and GNOME Shell pages pass `bar-plugin` and `gnome-shell`, the two scopes
    naming a frontend rather than a wrapped tool. The entry text is reproduced
    verbatim: the changelog is the curated wording, and rewriting it here would
    be one more thing to drift. Reproducing it is only safe because every link
    it carries is absolute, so nothing breaks one directory deeper in
    `docs/managers/`.

    A change scoped to several subjects is repeated verbatim on each of their
    pages, carrying no marker of the others: a reader is on one page to read
    about that one subject.

    ```{note}
    Released headings are not linkable: `myst_heading_slug_func` is
    `docutils.nodes.make_id`, which strips a heading holding no letter down to
    the empty string, so `` `7.5.0` (2026-08-03) `` yields no anchor at all.
    Each version therefore links to the comparison URL its own heading
    carries, which is parsed rather than guessed, exists for every release, and
    costs `linkcheck` nothing since the changelog page already cites it.
    ```
    """
    entries = _changelog_entries().get(scope, ())
    if not entries:
        return ""

    lines: list[str] = []
    releases = groupby(entries, key=lambda e: (e.version, e.date, e.url))
    for (version, date, url), shipped in releases:
        lines.append(f"- [`{version}`]({url}) ({date})")
        for entry in shipped:
            flag = f"**{entry.flag}:** " if entry.flag else ""
            lines.append(f"  - {flag}{entry.text}")
    return "\n".join(lines)


METRICS_STORE = PROJECT_ROOT / "docs" / "assets" / "metrics.csv"
"""Forge readings sampled by `repomatic sample-metrics` on the weekly schedule
of `.github/workflows/metrics.yaml`, and committed.

One row per repository, metric and date. The star-history charts of the
benchmark and history pages read the accruing `stars` rows through the
repomatic renderer itself; the manager pages read the same store for the two
facts their cards state.
"""


@cache
def _metrics_config() -> dict:
    """Parse the `[tool.repomatic.metrics]` table of `pyproject.toml`.

    The sampler's own configuration is the single source declaring which
    repository each subject measures, so the manager pages join the store
    against it rather than carrying a second map.
    """
    content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="UTF-8")
    config = tomllib.loads(content)
    return config["tool"]["repomatic"]["metrics"]  # type: ignore[no-any-return]


def _canonical_repo_url(target: str) -> str:
    """Resolve a metrics subject to the full URL the store records.

    A bare `owner/name` is GitHub, mirroring the sampler's own rule; anything
    else is already the URL it reads.
    """
    if "://" in target:
        return target
    return f"https://github.com/{target}"


@cache
def _manager_upstreams() -> dict[str, dict]:
    """Read the sampled upstream readings of {data}`METRICS_STORE`.

    Committed by the weekly `metrics.yaml` schedule, which is what keeps the
    docs build hermetic: the manager pages report a hundred forge repositories
    without the build touching a network. Keyed by manager ID, resolved
    through the `[tool.repomatic.metrics] subjects` table; a manager whose
    upstream cannot be measured is simply absent, and renders as empty cells.
    """
    subjects = _metrics_config()["subjects"]

    # One aggregated view per repository: the newest star count, and the sole
    # row of each attribute metric.
    per_repo: dict[str, dict] = {}
    with METRICS_STORE.open(encoding="UTF-8") as store:
        for row in csv.DictReader(store):
            reading = per_repo.setdefault(row["repo"], {})
            metric = row["metric"]
            if metric == "stars":
                newest = reading.get("stars_day", "")
                if row["date"] >= newest:
                    reading["stars_day"] = row["date"]
                    reading["stars"] = int(row["value"])
            else:
                reading[metric] = row["value"]

    upstreams = {}
    for manager_id in pool:
        if manager_id not in subjects:
            continue
        repo = _canonical_repo_url(subjects[manager_id])
        readings = per_repo.get(repo)
        if not readings:
            continue
        upstreams[manager_id] = {"repo": repo} | {
            key: value
            for key, value in readings.items()
            if key in ("stars", "commit", "release", "release_source")
        }
    return upstreams


def brewfile_managers_table() -> str:
    """Produce the Brewfile-entry table of `docs/dump.md`.

    Which managers survive a `--brewfile` dump, and under which entry keyword.
    Generated from the pool's own `brewfile_entry_type` declarations rather than
    listed in prose, which had gone stale and could not show that a manager and
    its Brewfile keyword sometimes differ: `uvx` writes `uv` entries, a mapping
    a sentence naming both would have to state twice to be read once.

    It replaces the enumeration that used to carry this, and the per-manager
    cards that used to repeat it: `--brewfile` is an option of one command, so
    the fact belongs on that command's page, stated once.
    """
    table = [
        [f"[`{mid}`](managers/{mid}.md)", f"`{m.brewfile_entry_type}`"]
        for mid, m in sorted(pool.items())
        if m.brewfile_entry_type
    ]
    return render_table(
        table,
        headers=["Manager", "Brewfile entry"],
        table_format=TableFormat.GITHUB,
        colalign=["left", "left"],
        disable_numparse=True,
    )


def managers_index_table() -> str:
    """Produce the manager index table of `docs/managers.md`.

    Rendered live at Sphinx build time. Both the name and the ID link to the
    manager's dedicated page, since a reader scanning for `apt-mint` looks at the
    identifier column, not the prose name. `Support` renders the same
    {func}`_support_glyph` scale as the benchmark's `mpm` column: `✅`/`⚠️` for a
    wrapped manager, `☠️`/`❌`/`🛟` for one `mpm` declined. Keeping the glyph in a
    column of its own, rather than trailing the ID, avoids gluing a sort-worthy
    fact to an identifier. Platform icons follow the same coverage reading as the
    manager pages: a partially-backed group keeps its icon with
    {func}`_platform_coverage`'s annotation (`🐧 (Exherbo Linux only)`) instead of
    disappearing, as it does in the readme's all-or-nothing matrix.

    The glyph is all this table says about a manager's status. The stars, newest
    release and newest commit behind a wrapped one live in its own
    {func}`manager_card`, and the reason behind a declined one lives in its own
    section of `docs/unsupported.md`: both answer a question asked about one tool
    at a time, and as columns here they made a reader scan a hundred rows to find
    the single one they came for, while widening the table enough to push the
    platform icons off a narrow screen.

    Declined managers (`docs/benchmark.toml`'s `unsupported` mapping) share the
    same table as the wrapped ones: they used to be a second block behind a
    repeated header, which read as a separate table and cost a reader tracking a
    tool across both a second set of column widths to parse. No prose name or
    platform data exists for a tool `mpm` never wrapped, so those cells stay
    blank, and the ID cell links to the manager's verdict section instead of a
    dedicated page it does not have.

    Rows group by verdict rather than running one alphabet from `am` to
    `zypper`, in {data}`SUPPORT_SCALE` order and alphabetically within each
    group. A reader comes to this page asking what became of a tool, which is
    the question the grouping answers first; the one arriving with a name in
    hand still finds it, the browser's own find command reaching a row wherever
    it sits.

    Each group opens on a title row laid out like the rows it introduces: the
    state's glyph in the mark column, where every manager below it shows its
    own brand mark, and the state's {data}`SUPPORT_SCALE` label where their
    names start, spliced in as a `manager-group` span.
    `docs/_static/manager-index.js` reads that span for the two shapes a
    markdown table cannot express: it merges the label over the columns to its
    right, a table format having no spanning cell, and extends the ID cell's
    target over the whole row, since a row is one manager and every part of it
    should answer the same click. Both degrade to what the markdown already
    says: the title reads as a glyph and a label in the two leading columns,
    and the links stay real links, so the `Support` glyph still leads to the
    source proving it and any of them opens in a new tab.
    """
    data = _load_benchmark_toml()
    competitor_data: dict[str, list[str]] = data.get("managers", {})
    unsupported: dict[str, str] = data.get("unsupported", {})
    queued: dict[str, str] = data.get("queued", {})
    homepages: dict[str, str] = data.get("homepages", {})
    anchors = unsupported_anchors()

    headers = ["", "Manager", "ID", "Support", "Platforms"]
    colalign = ["center", "left", "left", "center", "center"]

    rows = {}
    for mid, m in sorted(pool.items()):
        parts = []
        for p_obj in MAIN_PLATFORMS:
            coverage = _platform_coverage(p_obj, m.platforms)
            if coverage is None:
                continue
            icon, annotation = coverage
            parts.append(f"{icon} ({annotation})" if annotation else icon)
        # The artwork is spliced in after rendering: a multi-kilobyte SVG in a
        # cell would pad every other row of the column to its own width.
        rows[mid] = [
            f"%logo:{mid}%",
            f"[{m.name}](managers/{mid}.md)",
            f"[`{mid}`](managers/{mid}.md)",
            _support_glyph(mid, unsupported, anchors, competitor_data, queued),
            " ".join(parts),
        ]

    for mid in queued:
        url = homepages.get(mid)
        rows[mid] = [
            "",
            "",
            f"[`{mid}`]({url})" if url else f"`{mid}`",
            _support_glyph(mid, unsupported, anchors, competitor_data, queued),
            "",
        ]

    for mid in unsupported:
        anchor = anchors.get(mid)
        target = f"{UNSUPPORTED_DOCS_URL}#{anchor}" if anchor else UNSUPPORTED_DOCS_URL
        rows[mid] = [
            "",
            "",
            f"[`{mid}`]({target})",
            _support_glyph(mid, unsupported, anchors, competitor_data, queued),
            "",
        ]

    scale = tuple(SUPPORT_SCALE)
    glyphs = {
        mid: _bare_support_glyph(mid, unsupported, competitor_data, queued)
        for mid in rows
    }

    table = []
    group = None
    for mid in sorted(rows, key=lambda mid: (scale.index(glyphs[mid]), mid)):
        if glyphs[mid] != group:
            group = glyphs[mid]
            # The glyph takes the mark column, which is the icon column of every
            # other row, and the label starts where the prose names do. Like the
            # artwork, the label is spliced in after rendering: its span markup
            # is wider than the column, and would pad every name to its width.
            table.append([group, f"%group:{group}%", "", "", ""])
        table.append(rows[mid])

    rendered = render_table(
        table,
        # The mark column is headerless: the artwork labels itself, and the
        # managers whose upstream has no usable mark leave the cell empty.
        headers=headers,
        table_format=TableFormat.GITHUB,
        colalign=colalign,
        disable_numparse=True,
    )
    for mid in pool:
        rendered = rendered.replace(f"%logo:{mid}%", manager_logo(mid, inline=True))
    for glyph, label in SUPPORT_SCALE.items():
        rendered = rendered.replace(
            f"%group:{glyph}%",
            f'<span class="manager-group" id="{SUPPORT_ANCHORS[glyph]}">{label}</span>',
        )

    return rendered


def _support_population() -> Counter[str]:
    """Count every assessed manager into its {data}`SUPPORT_SCALE` state.

    The single reading of the population, shared by {func}`manager_support_bar`
    and {func}`manager_support_legend` so the widths of the bar and the numbers
    of the legend below it cannot disagree. Both sources are the ones
    {func}`managers_index_table` builds its rows from: the live pool, and
    `docs/benchmark.toml`'s `unsupported` mapping.
    """
    data = _load_benchmark_toml()
    competitor_data: dict[str, list[str]] = data.get("managers", {})
    unsupported: dict[str, str] = data.get("unsupported", {})
    queued: dict[str, str] = data.get("queued", {})
    return Counter(
        _bare_support_glyph(mid, unsupported, competitor_data, queued)
        for mid in (*pool, *queued, *unsupported)
    )


def manager_support_bar() -> str:
    """Produce the support bar opening `docs/managers.md`.

    Rendered live at Sphinx build time, above the legend naming its regions and
    the index they summarize: one full-width bar cut into the five
    {data}`SUPPORT_SCALE` states, in scale order, each region as wide as its
    share of the assessed population. It answers in one glance the question the
    page exists for, how much of what has been assessed `mpm` actually drives,
    where the legend answers it in five numbers a reader has to add up.

    Emitted as raw HTML rather than as a chart image: the shares are three
    numbers and a ratio, a picture nothing but CSS is needed to draw, and a
    committed image would go stale on the next manager the pool gains.

    Each region carries its own state's count as `flex-grow`, over a zero
    basis, so the proportions come out exact at any width and the gaps between
    regions are taken out of the track before the split rather than distorting
    it. That is also what keeps the markup honest: the number in the style
    attribute is the population, not a percentage computed here.

    ```{note}
    A region too narrow to hold its glyph drops it rather than clipping it, on
    a container query in `docs/_static/manager-index.css`. Nothing is lost: the
    legend below names every state, and each region's tooltip carries its count
    and share. The `⚠️` region is the one this is written for, five managers of
    two hundred odd leaving it about fifteen pixels wide.
    ```
    """
    counts = _support_population()
    total = counts.total()
    regions = []
    for rank, (glyph, label) in enumerate(SUPPORT_SCALE.items(), start=1):
        count = counts[glyph]
        share = count / total * 100
        reading = f"{count} managers, {share:.1f}%: {label}".replace("`", "")
        regions.append(
            f'<a class="manager-bar-region manager-bar-{rank}"'
            f' href="#{SUPPORT_ANCHORS[glyph]}" style="flex-grow: {count}"'
            f' title="{glyph} {reading}" aria-label="{reading}">'
            f'<span class="manager-bar-glyph">{glyph}</span></a>'
        )
    # A group rather than an image: the regions are links onto the matching
    # group of the index below, and a `role="img"` would hide them. Each one
    # names its own share, so the bar reads without its pictographs, which a
    # screen reader would otherwise announce as "lifebuoy".
    return (
        f'<div class="manager-bar" role="group" aria-label="Share of each'
        f" support state among the {total} package managers assessed so far,"
        f' counted in the table below">{"".join(regions)}</div>'
    )


def manager_support_legend() -> str:
    """Produce the counted glyph legend opening `docs/managers.md`.

    Rendered live at Sphinx build time, right above the index table it is the
    key to. Each {data}`SUPPORT_SCALE` state gets a row: its glyph, how many
    managers are in it, and what it means. Counts come from
    {func}`_bare_support_glyph` over the same two sources
    {func}`managers_index_table` builds its rows from, the live pool and
    `docs/benchmark.toml`'s `unsupported` mapping, so the legend cannot claim a
    population the table below does not show.

    The counts replace the prose summary that used to open the page ("`mpm`
    wraps N of them, M flagged unmaintained…"), a sentence restating in words
    what the reader was about to see as glyphs, and holding the same numbers a
    second time. Folding them into the legend costs a column and settles both
    questions at once: what a glyph means, and how much of the pool it covers.
    """
    counts = _support_population()
    table = [
        [glyph, str(counts[glyph]), meaning] for glyph, meaning in SUPPORT_SCALE.items()
    ]
    rendered = render_table(
        table,
        headers=["Glyph", "Managers", "Meaning"],
        table_format=TableFormat.GITHUB,
        colalign=["center", "right", "left"],
        disable_numparse=True,
    )
    return (
        f"{counts.total()} package managers have been assessed so far, each in "
        "one of six states. The index below reports them in its `Support` "
        "column, on the same glyph scale as the benchmark's "
        f"[`mpm` column](benchmark.md#package-manager-support):\n\n{rendered}"
    )


def manager_page(manager_id: str) -> str:
    """Produce a manager's whole documentation page, title included.

    Opens on the page title, then walks {data}`MANAGER_SECTIONS`: an untitled
    entry renders as the lede, a titled one as its heading followed by its
    generator's output. A section whose generator produces nothing for this
    manager (like reference traces for a manager documenting no literal output
    samples) is skipped.

    Nothing is left for the stub but the call, which is the point: a section
    added, renamed or dropped is an edit to {data}`MANAGER_SECTIONS` alone,
    where it used to rewrite every file in `docs/managers/`.

    ```{note}
    The title has to come from here rather than stay in the stub, and it is the
    lede that forces it. Headings survive the directive's nested parse,
    `myst-parser` having grown explicit support for them (`temp_root_node` in
    its `MockState.nested_parse`) since the days they had to be committed into
    each stub. What does not survive is content emitted *above* the first
    heading of that parse: the parser builds the sections under the parent node
    and appends the loose lead nodes after them, so a lede printed before the
    first `##` renders at the foot of the page. Printing the `#` title first
    puts every later node inside a section of its own, and the order holds.
    `test_manager_page_headings_survive_a_build` builds a page for real and
    asserts it, both regressions being silent otherwise.
    ```
    """
    m = pool[manager_id]
    blocks = [f"# {{octicon}}`package` {m.name}"]
    for title, func_name in MANAGER_SECTIONS:
        body = globals()[func_name](manager_id)
        if not body.strip():
            continue
        if title:
            blocks.append(f"## {title.format(manager_id=manager_id)}")
        blocks.append(body)
    return "\n\n".join(blocks) + "\n"


def manager_page_stub(manager_id: str) -> str:
    """Produce the committed stub of a manager's documentation page.

    One ``{python:render}`` block calling {func}`manager_page`, and nothing
    else: the title, the lede and every section render live at Sphinx build
    time and never drift from the pool. The block formatting mirrors
    `docs/benchmark.md` so the stubs are an `mdformat` fixpoint.

    The stubs went from 9,671 committed lines that every layout change rewrote
    to a template naming nothing but the manager. What is lost is a page's
    title as committed text: `docs/managers/` no longer greps for the name a
    manager is published under, which `docs/managers.md` and the pool both
    still carry.
    """
    return (
        "```{python:render}\n"
        "from meta_package_manager._docs import manager_page\n"
        "\n"
        f'print(manager_page("{manager_id}"))\n'
        "```\n"
    )
