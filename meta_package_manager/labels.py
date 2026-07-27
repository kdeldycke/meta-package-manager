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
"""Utilities to generate the extra labels and labeller rules for GitHub issues
and PRs.

The content and file rules produced here are a convenience: they pre-label a
freshly filed issue or PR to save the maintainer a first pass. They never replace
the manual review and classification, and nothing downstream treats them as
authoritative. They are therefore tuned for precision over recall: a rule is
encoded only when its signal is unambiguous (see {func}`generate_content_rules`
and {func}`generate_file_rules`), and a manager with no unambiguous term simply
gets no content rule and is labelled by hand.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from boltons.iterutils import flatten
from extra_platforms import extract_members

from .platforms import MAIN_PLATFORMS
from .pool import pool

TYPE_CHECKING = False
if TYPE_CHECKING:
    TLabelSet = frozenset[str]
    TLabelGroup = dict[str, TLabelSet]
    TLabelRules = list[tuple[str, tuple[str, ...]]]


LABELS: list[tuple[str, str, str]] = [
    (
        "🔌 bar-plugin",
        "#fef2c0",
        "Xbar/SwiftBar plugin code, documentation and features",
    ),
]
"""Global registry of all labels used in the project.

Structure:

```{code-block} python

("label_name", "color", "optional_description")
```
"""


def generate_labels(
    all_labels: TLabelSet,
    groups: TLabelGroup,
    prefix: str,
    color: str,
) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Generate labels.

    A dedicated label is produced for each entry of the `all_labels` parameter,
    unless it is part of a `group`. In which case a dedicated label for that group
    will be created.

    Returns the ``{label_id: label_name}`` map and the list of
    `(label_name, color, description)` rows to register, leaving the caller to fold
    them into the global {data}`LABELS` registry. Kept pure (no global mutation) so it
    can be called repeatedly without double-populating the registry.
    """
    # Check all labels to group are referenced in the full label set.
    grouped_labels = set(flatten(groups.values()))
    assert grouped_labels.issubset(all_labels)

    label_map = {}
    rows: list[tuple[str, str, str]] = []

    # Create a dedicated label for each non-grouped entry.
    standalone_labels = all_labels - grouped_labels
    for label_id in standalone_labels:
        label_name = f"{prefix}{label_id}"
        # Check the addition of the prefix does not collide with an existing label.
        assert label_name not in all_labels
        label_map[label_id] = label_name
        rows.append((label_name, color, label_id))

    # Create a dedicated label for each group.
    for group_id, label_ids in groups.items():
        label_name = f"{prefix}{group_id}"
        # Check the addition of the prefix does not collide with an existing label.
        assert label_name not in all_labels
        for label_id in label_ids:
            label_map[label_id] = label_name
        # Build a description that is less than 100 characters.
        description = ""
        truncation_mark = ", …"
        for item_id in sorted(label_ids, key=str.casefold):
            new_item = f", {item_id}" if description else item_id
            if len(description) + len(new_item) <= 100 - len(truncation_mark):
                description += new_item
            else:
                description += truncation_mark
                break
        rows.append((label_name, color, description))

    # Sort label_map by their name.
    return dict(sorted(label_map.items(), key=lambda i: str.casefold(i[1]))), rows


MANAGER_PREFIX = "📦 manager: "

MANAGER_LABEL_GROUPS: TLabelGroup = {
    "rpm-based": frozenset({"dnf", "dnf5", "urpmi", "yum", "zypper"}),
    "dpkg-based": frozenset({"apt", "apt-mint", "deb-get", "opkg", "pacstall"}),
    "homebrew": frozenset({"brew", "cask", "zerobrew"}),
    "npm-based": frozenset({"npm", "pnpm", "yarn", "yarn-berry"}),
    "pacman-based": frozenset({"pacman", "pacaur", "paru", "yay"}),
    "pip-based": frozenset({"pip", "pipx"}),
    "pkg-based": frozenset({"pkg", "ports"}),
    "scoop-based": frozenset({"scoop", "sfsu"}),
    "uv-based": frozenset({"uv", "uvx"}),
    "vscode-based": frozenset({"vscode", "vscodium"}),
}
"""Managers sharing the same ecosystem are grouped together under the same label.

Grouping is by ecosystem (the underlying packaging system), not by installation
paradigm. For example, source-based helpers like Pacstall and AUR helpers are grouped
with their ecosystem (dpkg-based and pacman-based respectively), even though they build
from source rather than fetching pre-built binaries.
"""

all_manager_label_ids = frozenset(set(pool.all_manager_ids) | {"mpm"})
"""Adds `mpm` as its own manager alongside all those implemented."""

# Check group IDs do not collide with original labels.
assert all_manager_label_ids.isdisjoint(MANAGER_LABEL_GROUPS.keys())

MANAGER_LABELS, _manager_label_rows = generate_labels(
    all_manager_label_ids,
    MANAGER_LABEL_GROUPS,
    MANAGER_PREFIX,
    "#bfdadc",
)
"""Maps all manager IDs to their labels."""


PLATFORM_PREFIX = "🖥 platform: "

PLATFORM_LABEL_GROUPS: TLabelGroup = {}
for p_obj in MAIN_PLATFORMS:
    PLATFORM_LABEL_GROUPS[p_obj.name] = frozenset(
        p.name for p in extract_members(p_obj)
    )
"""Similar platforms are grouped together under the same label."""

all_platform_label_ids = frozenset(flatten(PLATFORM_LABEL_GROUPS.values()))

PLATFORM_LABELS, _platform_label_rows = generate_labels(
    all_platform_label_ids,
    PLATFORM_LABEL_GROUPS,
    PLATFORM_PREFIX,
    "#bfd4f2",
)
"""Maps all platform names to their labels."""

# Fold the generated manager and platform rows into the registry, then sort it.
LABELS = sorted(
    (*LABELS, *_manager_label_rows, *_platform_label_rows),
    key=lambda i: str.casefold(i[0]),
)


# Labeller rules.
#
# repomatic's PR/issue labeller consumes two rule sets from pyproject.toml:
# content-rules (keyword patterns matched against issue and PR text) and file-rules
# (globs matched against a PR's changed files). Both are synced into
# [tool.repomatic.labels.*] by docs/docs_update.py. File rules derive their globs
# from the pool (each manager's definition-file paths); content rules are driven
# solely by the hand-curated ecosystem keywords below, never by bare manager IDs
# (see generate_content_rules for why).


CONTENT_RULES_STATIC: TLabelRules = [
    ("🔌 bar-plugin", ("plugin", "swiftbar", "xbar")),
]
"""Content rules for labels that are not derived from the pool."""


FILE_RULES_STATIC: TLabelRules = [
    # The plugin spans two sibling modules: the stdlib-only bar_plugin.py script and
    # its mpm-side bar_plugin_renderer.py companion. No trailing slash: they are
    # modules, not a package directory.
    ("🔌 bar-plugin", ("meta_package_manager/bar_plugin*", "tests/*bar_plugin*")),
    (f"{MANAGER_PREFIX}mpm", ("meta_package_manager/*",)),
]
"""File rules for labels that are not derived from the pool.

`mpm` gets no content rule: as the project's own name it would match nearly
every issue and PR.
"""


MANAGER_CONTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "apk": ("alpine", "alpine linux"),
    "apm": ("atom",),
    "apt-cyg": ("cygwin",),
    "asdf": ("asdf-vm",),
    "cargo": ("crate", "rust"),
    "cave": ("exherbo", "paludis"),
    "choco": ("chocolatey",),
    "chromebrew": ("chrome os", "chromeos"),
    "composer": ("php",),
    "conda": ("anaconda", "conda-forge", "miniconda"),
    "cpan": ("perl",),
    "dpkg-based": ("aptitude", "debian", "dpkg", "ubuntu"),
    "emerge": ("gentoo", "portage"),
    "eopkg": ("solus",),
    "flatpak": ("flathub",),
    "fwupd": ("lvfs",),
    "gem": ("ruby",),
    "gh-ext": ("gh extension", "github cli"),
    "guix": ("gnu guix",),
    "homebrew": ("homebrew",),
    "mas": ("app store", "app-store"),
    "nix": ("nixos", "nixpkgs"),
    "npm-based": ("node.js", "nodejs"),
    "pacman-based": ("arch",),
    "pip-based": ("pypi",),
    "pkcon": ("packagekit",),
    "pkg-based": ("freebsd", "freebsd ports"),
    "pkg-tools": ("openbsd",),
    "pkgin": ("netbsd", "pkgsrc"),
    "pwsh-gallery": (
        "powershell",
        "powershell gallery",
        "psgallery",
        "psresourceget",
    ),
    "rpm-based": ("fedora", "mageia", "opensuse", "redhat", "rhel", "rpm", "suse"),
    "sdkman": ("sdk man",),
    "slapt-get": ("slackware",),
    "snap": ("snapcraft",),
    "sorcery": ("source mage",),
    "steamcmd": ("valve",),
    "sun-tools": ("solaris", "svr4"),
    "swupd": ("clear linux", "clearlinux"),
    "tazpkg": ("slitaz",),
    "tlmgr": ("ctan", "tex live", "texlive"),
    "vscode-based": ("visual studio", "visual studio code"),
    "xbps": ("void linux",),
}
"""Curated ecosystem keywords feeding each manager label's content rule.

Keyed by the manager or group ID the label derives from. These are the *only*
content patterns a manager label gets: the bare manager IDs are deliberately left
out (see {func}`generate_content_rules`). Add only terms that are both
unambiguously about this manager and absent from anything mpm prints itself: the
`✓ <id>` trail, the `<id>: <count>` summary line, the `managers` table (which
lists every manager's ID and CLI binary) and the `$`-prompt command disclosure.
That rules out manager IDs and CLI names (`fwupdmgr`, `pwsh`), leaving the distro,
language and brand names a human types in an issue. A manager with no such term
gets no content rule and is labelled by hand.

Skip anything that doubles as a common word even once word-anchored (`port`,
`flat`, `mint`, `void`): dropping the ID removed the implicit AND-guard those
leaned on, so on their own they match unrelated prose.
"""

# Check synonym keys against the label registry: a key matching no manager label is
# a leftover from a renamed group or a removed manager.
assert set(MANAGER_CONTENT_KEYWORDS).issubset(
    set(all_manager_label_ids) | set(MANAGER_LABEL_GROUPS)
)


PLATFORM_CONTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "BSD": ("bsd",),
    "Linux": ("linux",),
    "macOS": ("apple", "mac os", "macos", "os x", "osx"),
    "Unix": ("unix",),
    "Windows": ("c:", "microsoft", "windows"),
}
"""Curated keyword patterns feeding each platform label's content rule."""

assert set(PLATFORM_CONTENT_KEYWORDS) == {p_obj.name for p_obj in MAIN_PLATFORMS}


def _label_members() -> dict[str, set[str]]:
    """Regroup {data}`MANAGER_LABELS` by label: ``{label_name: {manager_id, ...}}``.

    The `mpm` pseudo-manager is left out: it maps to no pool entry and its label
    is ruled by {data}`FILE_RULES_STATIC`.
    """
    members: dict[str, set[str]] = {}
    for manager_id, label_name in MANAGER_LABELS.items():
        if manager_id == "mpm":
            continue
        members.setdefault(label_name, set()).add(manager_id)
    return members


def _definition_stem(manager_id: str) -> str:
    """File stem of the manager's definition: its module or bundled TOML file."""
    manager = pool[manager_id]
    source = getattr(manager, "definition_source", None)
    if source:
        return Path(source).stem
    return Path(inspect.getfile(type(manager))).stem


def _anchored(keyword: str) -> str:
    r"""Anchor a keyword to whole-token matches with `\b` boundaries.

    `github/issue-labeler` matches each pattern as an unanchored regex, so a bare
    keyword also matches inside a larger word (`arch` in `search`). A boundary is
    added only on an edge that closes on a word character, so a keyword ending in
    punctuation (`c:`) stays unanchored there.
    """
    escaped = re.escape(keyword)
    prefix = r"\b" if keyword[:1].isalnum() else ""
    suffix = r"\b" if keyword[-1:].isalnum() else ""
    return f"{prefix}{escaped}{suffix}"


def _content_pattern(keyword: str) -> str:
    """Render one keyword as a case-insensitive labeller regex (`/…/i`).

    Case-insensitive because users capitalize ecosystem names (`Perl`, `PyPI`),
    which a lowercase keyword would miss under the labeller's case-sensitive
    default.
    """
    return f"/{_anchored(keyword)}/i"


def _keyword_alternation(keywords: tuple[str, ...]) -> str:
    """OR-join a label's keywords into one case-insensitive `/…/i` regex.

    `github/issue-labeler` requires *every* pattern in a label's list to match, so
    a raw keyword list reads as "all of these" rather than "any of these": a label
    carrying both `node.js` and `nodejs` would fire only when both appear at once.
    Collapsing the keywords into a single alternation restores "any keyword wins".
    """
    alternatives = "|".join(_anchored(kw) for kw in sorted(keywords, key=str.casefold))
    return f"/{alternatives}/i"


def generate_content_rules() -> TLabelRules:
    r"""Build every content rule: the static ones plus one per manager or platform
    label that has curated keywords.

    Manager labels are driven solely by {data}`MANAGER_CONTENT_KEYWORDS`, never by
    the bare manager IDs or CLI names. mpm enumerates every installed manager in its
    own output (the `✓ <id>` trail, the `<id>: <count>` summary line, the `managers`
    table), so a pasted trace would otherwise make every manager on the user's
    system match at once: a `cpan`-only report came back tagged `mise`, `pip` and
    `uv` merely because they sat in the trace. The keywords are the distro, language
    and brand names a human types, which mpm never prints.

    A manager label's keywords are OR-joined into a single case-insensitive pattern
    by {func}`_keyword_alternation`, since the labeller demands that every pattern
    in a list match. Platform labels instead keep a per-keyword list under that
    same all-of semantics: their names surface in every bug report's `mpm --version`
    block, so requiring several at once stops the platform labels from tagging every
    issue. A label with no keyword is skipped: that manager gets no content rule,
    only its file rule. Rules are sorted by label, both cases folded.
    """
    rules = list(CONTENT_RULES_STATIC)
    for label_name in _label_members():
        key = label_name.removeprefix(MANAGER_PREFIX)
        keywords = MANAGER_CONTENT_KEYWORDS.get(key, ())
        if not keywords:
            continue
        rules.append((label_name, (_keyword_alternation(keywords),)))
    for platform_name, platform_keywords in PLATFORM_CONTENT_KEYWORDS.items():
        patterns = tuple(
            _content_pattern(kw) for kw in sorted(platform_keywords, key=str.casefold)
        )
        rules.append((f"{PLATFORM_PREFIX}{platform_name}", patterns))
    return sorted(rules, key=lambda rule: str.casefold(rule[0]))


def generate_file_rules() -> TLabelRules:
    """Build every file rule: static ones plus one per manager label.

    A manager label matches its members' definition files (Python modules and
    bundled TOML files alike, anchored on the full stem so `pkg.*` never swallows
    `pkgin.toml` or `pkcon.py`) and any test file carrying a member's stem or
    ID. Platform labels have no file rule: no file is platform-specific.
    """
    rules = list(FILE_RULES_STATIC)
    for label_name, manager_ids in _label_members().items():
        definition_stems = {_definition_stem(mid) for mid in manager_ids}
        test_stems = definition_stems | {mid.replace("-", "_") for mid in manager_ids}
        globs = [
            f"meta_package_manager/managers/{stem}.*"
            for stem in sorted(definition_stems)
        ]
        globs.extend(f"tests/*{stem}*" for stem in sorted(test_stems))
        rules.append((label_name, tuple(globs)))
    return sorted(rules, key=lambda rule: str.casefold(rule[0]))
