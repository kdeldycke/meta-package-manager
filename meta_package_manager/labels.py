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
        "🔌 plugin",
        "#fef2c0",
        "SwiftBar/Xbar/GNOME Shell plugin code, documentation and features",
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


MANAGER_LABEL_COLOR = "#bfdadc"
"""Color GitHub paints every `📦 manager: *` label with.

Also the color of the badge each manager's documentation page links its label
with, hard-coded in `docs/_static/custom.css` since a stylesheet cannot read
this module; `test_manager_label_badge_color` keeps the two in step.
"""

MANAGER_PREFIX = "📦 manager: "

MANAGER_LABEL_GROUPS: TLabelGroup = {
    "asdf-based": frozenset({"asdf", "mise"}),
    "bash-based": frozenset({"basalt", "bpkg"}),
    "conda-based": frozenset({"conda", "mamba", "micromamba", "pixi"}),
    "rpm-based": frozenset({"dnf", "dnf5", "urpmi", "yum", "zypper"}),
    "dpkg-based": frozenset({
        "apt",
        "apt-mint",
        "deb-get",
        "fink",
        "nala",
        "opkg",
        "pacstall",
    }),
    "fish-based": frozenset({"fisher", "oh-my-fish"}),
    "homebrew": frozenset({"brew", "cask", "zerobrew"}),
    "neovim-based": frozenset({"bob", "lazy", "mason", "vim-pack"}),
    "npm-based": frozenset({
        "bun",
        "npm",
        "pnpm",
        "volta",
        "yarn",
        "yarn-berry",
    }),
    "pacman-based": frozenset({
        "dkp-pacman",
        "pacman",
        "pacaur",
        "pamac",
        "paru",
        "pikaur",
        "trizen",
        "yay",
    }),
    "pkg-based": frozenset({"pkg", "ports"}),
    "pypi-based": frozenset({"pip", "pipx", "pipxu", "uv", "uvx"}),
    "scoop-based": frozenset({"scoop", "sfsu"}),
    "vscode-based": frozenset({"vscode", "vscodium"}),
    "zsh-based": frozenset({"antidote", "antigen", "zim", "zinit", "zplug"}),
}
"""Managers sharing the same ecosystem are grouped together under the same label.

Grouping is by ecosystem (the underlying packaging system), not by installation
paradigm. For example, source-based helpers like Pacstall and AUR helpers are grouped
with their ecosystem (dpkg-based and pacman-based respectively), even though they build
from source rather than fetching pre-built binaries. `fink` follows the same rule over
its platform: it manages `.deb` packages through dpkg, so it groups with the other dpkg
front-ends despite being the only macOS one among them.

`pypi-based` is named for the registry rather than for a tool, because no single tool is
common to it: `uv` reimplements resolution and installation from scratch and touches no
`pip` code. What the four share is the index they all resolve against, which is the
level a report lands at.

The host-program groups (`bash-based`, `fish-based`, `neovim-based`, `zsh-based`) widen
that reading, and deliberately so: plugin managers share no backend at all, each cloning
straight from upstream Git into its own tree. What they share is the host program a
report is about, which is what the label has to answer. An issue mentioning a Neovim
plugin is about the same corner of `mpm` whether it arrives through `vim-pack` or
`lazy`, so both carry one label and one tracker search. The groups stay separate along
that same line, one per host program: `zinit` and `antidote` host Zsh plugins, not
Neovim ones, and a report about either belongs nowhere near the editor label. Grouping
all of them under a single shell-plugin label was considered and rejected on the same
grounds, since it would answer with `mpm`'s implementation shape (an interpreter-keyed
manager wrapping every call in `zsh -c` or `fish -c`) where the reporter filed against a
shell.

`mason` is the one member of those groups that manages no plugins at all, installing
ordinary developer tools rather than editor Lua. It groups under `neovim-based` anyway,
because the host program is the axis: Neovim is what a `mason` report is about, and it
is also what `mpm` keys the manager on, the three sharing one module and one `nvim`
binary. Naming the group for the editor rather than for plugins is what lets it hold
`mason` without straining.

`bob` stretches that naming one step further, and is the member to check the axis
against. It installs Neovim itself rather than anything into it, and is the only member
`mpm` does not key on the `nvim` binary, being its own executable in its own definition.
It groups here regardless, because the axis is what a report is *about* and every bob
report is about Neovim: leaving it out would split the editor across two labels and two
tracker searches, which is the split this group exists to prevent. `volta` is the same
call already taken elsewhere, kept under `npm-based` though it manages a runtime too.

`sheldon` is the one shell plugin manager left ungrouped, and it fails both halves of
that test: it manages plugins for any shell rather than for one, and it is a compiled
binary rather than a sourced function, so it shares neither a host program nor the
interpreter wrapper with the groups above.

`asdf-based` is the plain reading again: `mise` resolves asdf's plugins directly through
its `asdf:` backend, so the two share one plugin ecosystem and one class of report.
`volta` stays under `npm-based` despite also managing a runtime, because what it
installs is npm packages.

`conda-based` follows `pypi-based`: `pixi` shares no code with `conda`, reimplementing
resolution and installation on top of rattler, but both resolve conda packages from the
same channels, `conda-forge` by default. The registry is the level a report lands at, so
the two share one label even though their CLIs have nothing else in common.
"""

all_manager_label_ids = frozenset(set(pool.all_manager_ids) | {"mpm"})
"""Adds `mpm` as its own manager alongside all those implemented."""

# Check group IDs do not collide with original labels.
assert all_manager_label_ids.isdisjoint(MANAGER_LABEL_GROUPS.keys())

MANAGER_LABELS, _manager_label_rows = generate_labels(
    all_manager_label_ids,
    MANAGER_LABEL_GROUPS,
    MANAGER_PREFIX,
    MANAGER_LABEL_COLOR,
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


LABEL_RENAMES: dict[str, tuple[str, ...]] = {
    f"{MANAGER_PREFIX}conda-based": (f"{MANAGER_PREFIX}conda",),
    f"{MANAGER_PREFIX}pypi-based": (f"{MANAGER_PREFIX}pip-based",),
}
"""Labels a renamed one supersedes, emitted as labelmaker's `rename-from`.

Folding managers into a group orphans the labels they used to carry, and the
issues already filed against those. `rename-from` migrates one in place, which
is the only lossless move available: GitHub keeps every issue and pull request
attached across a rename, whereas creating the new label and deleting the old
one drops the association.

The mechanism is strictly one-to-one, so this map cannot express a merge:
labelmaker errors outright when two `rename-from` labels both exist, and falls
to `on-rename-clash` (`error`, repomatic's default) when the target already
exists. An N-to-1 fold therefore names the *single* source carrying the most
history, leaving the remainder to a hand migration, and a fold whose target
label already exists names none at all.

`conda-based` is the same lossless shape: only `conda` carries history, `pixi` arrives
with no label of its own, and the target does not exist yet, so the fold is genuinely
one-to-one.

`dpkg-based`, `zsh-based` and `asdf-based` were all synced into existence before
their predecessors were retired, so a declared rename would only error; their
orphans (`fink`, `zinit`, `asdf`, `mise`) carry no issue or pull request at all
and are deleted rather than migrated. `vim-based` was created on those same
terms, orphaning `vim-pack`, and has since been folded into `neovim-based`.

`bash-based` names no source either, for the other reason: it folds two labels
rather than one, and `basalt` and `bpkg` both carry zero issues and zero pull
requests, so there is no history for the single rename slot to preserve.
`neovim-based` is that same shape, folding `vim-based` and `mason`, which
likewise carry zero of each.
"""


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
    ("🔌 plugin", ("gnome shell", "gnome-shell", "plugin", "swiftbar", "xbar")),
]
"""Curated keywords feeding the content rules of labels not derived from the pool.

Holds bare keywords, like every other content rule: repomatic's `apply-labels`
does the anchoring and case-folding (see {func}`generate_content_rules`).
"""


FILE_RULES_STATIC: TLabelRules = [
    # The label covers every menubar/panel integration: the stdlib-only
    # bar_plugin.py script, its mpm-side bar_plugin_renderer.py companion (no
    # trailing slash: they are modules, not a package directory), and the GNOME
    # Shell extension tree with its gjs test runner.
    (
        "🔌 plugin",
        (
            "gnome-shell/**",
            "meta_package_manager/bar_plugin*",
            "tests/*bar_plugin*",
            "tests/*gnome*",
            "tests/gnome/**",
        ),
    ),
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
    "asdf-based": ("asdf-vm", "mise-en-place"),
    "cargo": ("crate", "rust"),
    "cave": ("exherbo", "paludis"),
    "choco": ("chocolatey",),
    "chromebrew": ("chrome os", "chromeos"),
    "composer": ("php",),
    "conda-based": ("anaconda", "conda-forge", "miniconda", "prefix.dev"),
    "cpan": ("perl",),
    "dotnet": ("nuget",),
    "dpkg-based": ("aptitude", "debian", "dpkg", "ubuntu"),
    "emerge": ("gentoo", "portage"),
    "eopkg": ("solus",),
    "flatpak": ("flathub",),
    "fwupd": ("lvfs",),
    "gem": ("ruby",),
    "getnf": ("nerd font", "nerd fonts"),
    "gh-ext": ("gh extension", "github cli"),
    "guix": ("gnu guix",),
    "homebrew": ("homebrew",),
    "mas": ("app store", "app-store"),
    "nix": ("nixos", "nixpkgs"),
    "npm-based": ("node.js", "nodejs"),
    "pacman-based": ("arch",),
    "pypi-based": ("pypi",),
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
"""Curated keywords feeding each platform label's content rule."""

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


def _sorted_keywords(keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Order a label's keywords case-insensitively.

    Matching is order-independent, so this is purely to keep the generated
    `pyproject.toml` stable: a reordered source tuple must not churn the file.
    """
    return tuple(sorted(keywords, key=str.casefold))


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

    Keywords are emitted raw, one pattern each, because repomatic's `apply-labels`
    applies a label as soon as *any* one of its patterns matches, and compiles a
    bare pattern case-insensitively with a `\b` anchor on each edge that is itself
    a word character. That is what the retired `github/issue-labeler` needed
    hand-built here: its all-of semantics forced a `/…/i` alternation to mean "any
    keyword wins", and its case-sensitive default forced the `i` flag. Keep the
    keywords bare, and reach for the `/body/flags` escape hatch only for something
    an anchored literal cannot express.

    A label with no keyword is skipped: that manager gets no content rule, only its
    file rule. Rules are sorted by label, and each label's keywords among
    themselves, both cases folded.
    """
    rules = [
        (label_name, _sorted_keywords(keywords))
        for label_name, keywords in CONTENT_RULES_STATIC
    ]
    for label_name in _label_members():
        key = label_name.removeprefix(MANAGER_PREFIX)
        keywords = MANAGER_CONTENT_KEYWORDS.get(key, ())
        if not keywords:
            continue
        rules.append((label_name, _sorted_keywords(keywords)))
    for platform_name, platform_keywords in PLATFORM_CONTENT_KEYWORDS.items():
        rules.append((
            f"{PLATFORM_PREFIX}{platform_name}",
            _sorted_keywords(platform_keywords),
        ))
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
