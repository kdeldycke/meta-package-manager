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

"""Sample forge metrics: `mpm`'s star history, and every manager's upstream.

Two datasets, collected by one module because they read the same APIs on the
same schedule and land in the same commit. The star history plotted on the
benchmark and history pages is the older of the two; {data}`UPSTREAM_REPOS`
adds the popularity and activity readings the manager index shows, one per
wrapped manager.

Replaces the third-party star-history.com chart the benchmark and history pages
used to embed. On 2026-06-30 GitHub restricted the REST stargazer endpoints to a
repository's own admins and collaborators, and closed the equivalent GraphQL
field on 2026-07-17, which left every embed on the web rendering an error card.

What survived is the aggregate `stargazers_count` on the repository object, which
stays public for everyone. That single scalar is the whole basis of this module:
sampled on a schedule it accumulates into a history nobody can revoke.

```{note}
Two collectors, because the two halves of the chart are not equally knowable.

For a repository the token administers (`mpm`), the per-star `starred_at`
timestamps are still served, so its curve is reconstructed exactly, back to the
first star in 2016, in a handful of calls.

For the competitors, only the aggregate is readable. Their history therefore
comes from periodic samples going forward, plus a one-time backfill mined from
archived copies of their GitHub pages, each of which states the precise count on
the day it was captured.
```

```{warning}
The reconstruction and the samples do not measure the same thing, and the
difference is deliberate rather than a defect.

The stargazers API lists only the people who *still* have the repository
starred, so a reconstruction attributes today's surviving stars to the dates
they were given: it understates every past date by the number of stars since
withdrawn, converging on the true figure at the present day. Measured against
contemporaneous archived counts for `mpm`, the gap grows from 1 star in 2017 to
21 by 2023. Kept on purpose, since a curve that sags where a project shed
followers carries a signal a monotonic one hides. Each record therefore names
its {data}`SOURCES`, so a reader can always tell which question a point answers.
```
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter
from datetime import date, datetime, timezone
from itertools import accumulate
from pathlib import Path
from typing import Any, NamedTuple

ASSETS = Path(__file__).parent / "assets"
"""Directory holding the committed data file and the rendered chart."""

CHART = ASSETS / "star-history.svg"
"""Rendered chart, committed so the docs build and GitHub both stay offline.

An SVG rather than the client-side canvas the VirusTotal trend uses: GitHub
strips `<script>` and `<canvas>` from Markdown, so a scripted chart is invisible
to every reader of the repository, while the embed it replaces was an image that
rendered there. Committing it also drops the pinned CDN artifact and its
subresource-integrity digest, which is the point of moving off a service that
died without notice.
"""

CHART_MPM = ASSETS / "star-history-mpm.svg"
"""Single-series variant plotted on the history page.

That page charts `mpm`'s own trajectory rather than the competition, and a peer
four times its size would flatten the curve the page exists to show.
"""

CHART_RELATIVE = ASSETS / "star-history-relative.svg"
"""Same series, plotted against each project's own age rather than the calendar.

The absolute chart answers when a project gathered its following, and buries the
younger ones in the left margin. This one starts every curve at its repository's
creation, which is the only origin all five share, so a project that took eight
years to reach a figure another hit in two is read at a glance.
"""

STORE = ASSETS / "star-history.json"
"""Accumulated star history, one record per repository and date.

Shares the shape of `virustotal-scans.json`: a flat list of records with
alphabetically sorted keys, itself sorted by repository then date, so a
scheduled commit shows up as an append rather than a reshuffle.
"""

TRACKED_REPOS = {
    "mpm": "kdeldycke/meta-package-manager",
    "topgrade": "topgrade-rs/topgrade",
    "upt": "sigoden/upt",
    "pacaptr": "rami3l/pacaptr",
    "metapac": "ripytide/metapac",
}
"""Repositories plotted on the chart, keyed by their benchmark column.

Holds `mpm` plus every entry of
{data}`~meta_package_manager._docs.BENCHMARK_COMPETITORS`, which a conformance
test enforces. `brew` is tracked in the benchmark's popularity table but stays
off the chart on purpose: Homebrew outweighs the rest by an order of magnitude
and flattens all five curves onto the axis.
"""

PREDECESSOR_REPOS = {
    "topgrade": "r-darwish/topgrade",
}
"""Retired forerunner of a tracked project, plotted beside its successor.

`topgrade-rs/topgrade` is a continuation rather than a fresh start: the
original was archived at 3308 stars, and the successor opened its own
repository in 2022 to carry the project on. Its curve therefore begins with an
audience it inherited, not one it gathered, which is exactly what the
by-age chart would otherwise misreport as the fastest start in the field.

Drawn in the successor's own hue to tie the two together, but dashed and never
joined to it: the counts are independent tallies on separate repositories, so a
continuous line would claim a running total that no repository ever showed.
"""

PREDECESSOR_SUFFIX = ":prior"
"""Marks a predecessor's series key, appended to the column it belongs to.

Keeps `TRACKED_REPOS` exactly the benchmark's own columns, which a conformance
test pins, while still letting the collector and the renderer address the extra
curve through the same code paths.
"""

SOURCES = {
    "created": "Repository creation, the one date a star count is known to be 0.",
    "github": "Exact per-star timestamps, surviving stars only (admin token).",
    "sample": "Aggregate `stargazers_count` snapshot, contemporaneous.",
    "wayback": "Contemporaneous count mined from an archived GitHub page.",
}
"""Provenance vocabulary, recorded per point.

The chart mixes methodologies it cannot reconcile, so it records which one each
point came from rather than presenting a uniform curve it cannot honestly claim.

`created` is the outlier: not a measurement but a fact, and the only origin the
five series share. A repository backfilled from the archives has no knowable
first star, since its earliest capture already shows a count, so its curve would
otherwise begin in mid-air. It is also what the relative chart aligns on.
"""

# Categorical slots 1-5 of the documented palette, validated as a set for the
# adjacent pairlist in both modes. Light mode puts three of them below 3:1
# against the surface, which the direct labels at each line's end answer.
SERIES_COLORS = {
    "mpm": ("#2a78d6", "#3987e5"),
    "topgrade": ("#eb6834", "#d95926"),
    "upt": ("#1baf7a", "#199e70"),
    "pacaptr": ("#eda100", "#c98500"),
    "metapac": ("#e87ba4", "#d55181"),
}
"""Light and dark hex pair per series, in fixed order and never cycled."""

UPSTREAMS = ASSETS / "manager-upstreams.json"
"""Popularity and activity of each wrapped manager's own upstream project.

One record per manager, where {data}`STORE` keeps one per repository *and* date:
the manager index reports where a project stands today, and a hundred managers
sampled weekly would otherwise pile up thousands of records a year that nothing
ever reads chronologically. A record therefore carries the date its reading was
taken and is rewritten only when that reading moves, which keeps a quiet week
out of the diff and dates a dead project's row honestly.
"""

UPSTREAM_REPOS = {
    "am": "https://github.com/ivan-hc/AM",
    "antidote": "https://github.com/mattmc3/antidote",
    "antigen": "https://github.com/zsh-users/antigen",
    "apk": "https://gitlab.alpinelinux.org/alpine/apk-tools",
    "apm": "https://github.com/atom/apm",
    "apt": "https://salsa.debian.org/apt-team/apt",
    "apt-cyg": "https://github.com/transcode-open/apt-cyg",
    "asdf": "https://github.com/asdf-vm/asdf",
    "bin": "https://github.com/marcosnils/bin",
    "bpkg": "https://github.com/bpkg/bpkg",
    "brew": "https://github.com/Homebrew/brew",
    "bun": "https://github.com/oven-sh/bun",
    "cargo": "https://github.com/rust-lang/cargo",
    "cask": "https://github.com/Homebrew/homebrew-cask",
    "cave": "https://gitlab.exherbo.org/paludis/paludis",
    "choco": "https://github.com/chocolatey/choco",
    "clib": "https://github.com/clibs/clib",
    "chromebrew": "https://github.com/chromebrew/chromebrew",
    "composer": "https://github.com/composer/composer",
    "conda": "https://github.com/conda/conda",
    "cpan": "https://github.com/andk/cpanpm",
    "deb-get": "https://github.com/wimpysworld/deb-get",
    "dkp-pacman": "https://github.com/devkitPro/pacman",
    "dnf": "https://github.com/rpm-software-management/dnf",
    "dnf5": "https://github.com/rpm-software-management/dnf5",
    "dotnet": "https://github.com/dotnet/sdk",
    "emerge": "https://github.com/gentoo/portage",
    "eopkg": "https://github.com/getsolus/eopkg",
    "fink": "https://github.com/fink/fink",
    "fisher": "https://github.com/jorgebucaran/fisher",
    "flatpak": "https://github.com/flatpak/flatpak",
    "fwupd": "https://github.com/fwupd/fwupd",
    "gem": "https://github.com/ruby/rubygems",
    "gext": "https://github.com/essembeh/gnome-extensions-cli",
    "gh-ext": "https://github.com/cli/cli",
    "ghcup": "https://github.com/haskell/ghcup-hs",
    "guix": "https://codeberg.org/guix/guix",
    "haxelib": "https://github.com/HaxeFoundation/haxelib",
    "jpm": "https://github.com/janet-lang/jpm",
    "juliaup": "https://github.com/JuliaLang/juliaup",
    "krew": "https://github.com/kubernetes-sigs/krew",
    "lazy": "https://github.com/folke/lazy.nvim",
    "luarocks": "https://github.com/luarocks/luarocks",
    "macports": "https://github.com/macports/macports-base",
    "mamba": "https://github.com/mamba-org/mamba",
    "mas": "https://github.com/mas-cli/mas",
    "mason": "https://github.com/mason-org/mason.nvim",
    "micro": "https://github.com/micro-editor/micro",
    "micromamba": "https://github.com/mamba-org/mamba",
    "miktex": "https://github.com/MiKTeX/miktex",
    "mise": "https://github.com/jdx/mise",
    "nimble": "https://github.com/nim-lang/nimble",
    "nix": "https://github.com/NixOS/nix",
    "npm": "https://github.com/npm/cli",
    "oh-my-fish": "https://github.com/oh-my-fish/oh-my-fish",
    "ollama": "https://github.com/ollama/ollama",
    "opam": "https://github.com/ocaml/opam",
    "pacaur": "https://github.com/E5ten/pacaur",
    "pacman": "https://gitlab.archlinux.org/pacman/pacman",
    "pacstall": "https://github.com/pacstall/pacstall",
    "pamac": "https://github.com/manjaro/pamac-cli",
    "paru": "https://github.com/Morganamilo/paru",
    "pikaur": "https://github.com/actionless/pikaur",
    "pip": "https://github.com/pypa/pip",
    "pipx": "https://github.com/pypa/pipx",
    "pixi": "https://github.com/prefix-dev/pixi",
    "pkcon": "https://github.com/PackageKit/PackageKit",
    "pkg": "https://github.com/freebsd/pkg",
    "pkg-tools": "https://github.com/openbsd/src",
    "pkgin": "https://github.com/NetBSDfr/pkgin",
    "pnpm": "https://github.com/pnpm/pnpm",
    "ports": "https://github.com/freebsd/freebsd-ports",
    "pwsh-gallery": "https://github.com/PowerShell/PSResourceGet",
    "pyenv": "https://github.com/pyenv/pyenv",
    "rustup": "https://github.com/rust-lang/rustup",
    "scoop": "https://github.com/ScoopInstaller/Scoop",
    "sdkman": "https://github.com/sdkman/sdkman-cli",
    "sfsu": "https://github.com/winpax/sfsu",
    "sheldon": "https://github.com/rossmacarthur/sheldon",
    "slapt-get": "https://github.com/jaos/slapt-get",
    "snap": "https://github.com/canonical/snapd",
    "soar": "https://github.com/pkgforge/soar",
    "sorcery": "https://github.com/sourcemage/sorcery",
    "stew": "https://github.com/marwanhawari/stew",
    "swupd": "https://github.com/clearlinux/swupd-client",
    "tlmgr": "https://github.com/TeX-Live/texlive-source",
    "topgrade": "https://github.com/topgrade-rs/topgrade",
    "trizen": "https://github.com/trizen/trizen",
    "uv": "https://github.com/astral-sh/uv",
    "uvx": "https://github.com/astral-sh/uv",
    "vagrant": "https://github.com/hashicorp/vagrant",
    "vcpkg": "https://github.com/microsoft/vcpkg",
    "vim-pack": "https://github.com/neovim/neovim",
    "volta": "https://github.com/volta-cli/volta",
    "vscode": "https://github.com/microsoft/vscode",
    "vscodium": "https://github.com/VSCodium/vscodium",
    "winget": "https://github.com/microsoft/winget-cli",
    "xbps": "https://github.com/void-linux/xbps",
    "yazi": "https://github.com/sxyazi/yazi",
    "xcodes": "https://github.com/XcodesOrg/xcodes",
    "yarn": "https://github.com/yarnpkg/yarn",
    "yarn-berry": "https://github.com/yarnpkg/berry",
    "yay": "https://github.com/Jguer/yay",
    "yum": "https://github.com/rpm-software-management/yum",
    "zerobrew": "https://github.com/lucasgelfond/zerobrew",
    "zim": "https://github.com/zimfw/zimfw",
    "zinit": "https://github.com/zdharma-continuum/zinit",
    "zplug": "https://github.com/zplug/zplug",
    "zypper": "https://github.com/openSUSE/zypper",
}
"""Source repository of each manager's upstream project, keyed by manager ID.

Curated by hand, since a manager declares a home page and nothing else, and a
home page is a website far more often than a repository. Two rules settle the
projects that have more than one:

- **The canonical repository beats a mirror**, however well known the mirror is.
  Alpine's `apk-tools` is mirrored on GitHub, where the newest tag is `v2.10.4`
  from 2019 while the GitLab original sits on `v3.0.7`: a mirror's activity is
  not the project's. The exception is a canonical forge exposing no API at all
  (Gentoo's gitweb, the FreeBSD and OpenBSD trees), where the project's own
  mirror is the only readable copy and stands in for it.
- **A manager shipped inside a larger tool takes that tool's repository**, so
  `vscode` reads Visual Studio Code's figures and `vim-pack` reads Neovim's.
  A count cannot be split out of a monorepo, and choosing case by case which
  manager deserves its parent's numbers would be arbitrary.

Sorted by manager ID, and paired with {data}`NO_UPSTREAM` so every wrapped
manager appears in exactly one of the two.
"""

NO_UPSTREAM = {
    "apt-mint": "Ships in a distribution package with no public repository.",
    "gcloud": "Google publishes the Cloud SDK as a binary; its source is not.",
    "nala": "Hosted on GitLab, which the sampler does not query.",
    "opkg": "Hosted on the Yocto Project's cgit, which serves no API.",
    "steamcmd": "Valve ships SteamCMD as a proprietary binary.",
    "sun-tools": "Oracle Solaris packaging tools are proprietary.",
    "tazpkg": "Hosted on SliTaz's Mercurial server, which serves no API.",
    "urpmi": "Hosted on Mageia's own git server, which serves no API.",
}
"""Managers whose upstream cannot be measured, and why.

Recorded rather than left implicit: a manager absent from both maps is an
oversight a conformance test reports, while one listed here is a decision. Their
popularity and activity cells stay empty in the manager index.
"""

FORGE_APIS = {
    "codeberg.org": "forgejo",
    "github.com": "github",
    "gitlab.alpinelinux.org": "gitlab",
    "gitlab.archlinux.org": "gitlab",
    "gitlab.exherbo.org": "gitlab",
    "salsa.debian.org": "gitlab",
}
"""Forge software each host runs, which is what selects the API to call.

Never guessed from the host name: an unknown host raises instead, so a manager
whose upstream lands on a fourth kind of forge has to declare how to read it
rather than silently sampling nothing.
"""

GITHUB_METRICS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    stargazerCount
    latestRelease { publishedAt }
    defaultBranchRef { target { ... on Commit { committedDate } } }
    refs(refPrefix: "refs/tags/", first: 1,
         orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
      nodes {
        target {
          ... on Commit { committedDate }
          ... on Tag { target { ... on Commit { committedDate } } }
        }
      }
    }
  }
}
"""
"""Reads a repository's stars, newest release, newest tag and last commit.

One call where REST needs three, and correct where REST is not: `/tags` answers
in an order nobody should assume. Its first tag is the newest for `pip`, but
`v0.0.1-pre` from 2014 for `cargo` and a 2019 branch marker for `zypper`, so a
fallback trusting that order would date live projects a decade into the past.
Ordering on `TAG_COMMIT_DATE` states the question instead of hoping the default
matches it.

The commit date is read off the default branch rather than from the repository's
`pushedAt`, which any push to any branch bumps.
"""

LAST_FETCH_REASONS: Counter[str] = Counter()
"""Why the most recent {func}`fetch` gave up, tallied by outcome.

Module-level rather than returned, so the retry loop keeps its `bytes | None`
signature while the caller can still report what went wrong. Only ever read
straight after a `None`.
"""

MAX_RETRY_DELAY = 15.0
"""Ceiling on {func}`fetch`'s exponential backoff, in seconds.

Doubling without a bound spends the whole attempt budget waiting, which is the
wrong trade against a service that fails most requests but recovers within
seconds on the next one.
"""

WAYBACK_PAGE_TRIES = 8
"""Attempts per archived page.

Sized against a measurement rather than a guess: 25 requests for one capture
known to exist returned 23 plain `503`s and 2 truncated bodies, and no clean
response at all. Since a truncated body still carries the counter, the per-try
success rate that matters was 2 in 25, and eight tries is the point past which
more attempts cost more than the captures they recover.
"""

WAYBACK_REQUEST_DELAY = 3.0
"""Seconds to wait between two archived pages.

The backfill is a one-off that nobody watches, so trading minutes for a higher
completion rate is free. Its counterpart is the retry backoff in {func}`fetch`,
which handles a single hiccup; this handles the sustained budget.
"""

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
"""Sent to the Wayback Machine, which serves robots a reduced index."""

FORGE_USER_AGENT = "meta-package-manager docs collector"
"""Sent to every forge API, where the browser identity above backfires.

Three of the four self-hosted GitLab instances read here answer a browser
user-agent with a page rather than a payload: salsa, Exherbo's and Arch's each
returned two to eight kilobytes of HTML where the same URL fetched under a plain
agent returned under a kilobyte of JSON. Nothing errors, so the symptom is a
manager quietly missing from the index rather than a failed run.
"""

WAYBACK_STAR_PATTERNS = (
    re.compile(r'id="repo-stars-counter-star"[^>]*title="([\d,]+)"', re.IGNORECASE),
    re.compile(r'title="([\d,]+)"[^>]*id="repo-stars-counter-star"', re.IGNORECASE),
    re.compile(r'aria-label="([\d,]+) users? starred', re.IGNORECASE),
    re.compile(
        r'href="/[^"]+/stargazers"[^>]*class="social-count[^"]*"[^>]*>\s*([\d,]+)',
        re.IGNORECASE,
    ),
    re.compile(
        r'class="social-count[^"]*"[^>]*href="/[^"]+/stargazers"[^>]*>\s*([\d,]+)',
        re.IGNORECASE,
    ),
)
"""Star-counter markups GitHub has shipped over the years, newest first.

An archived page states the exact figure in an attribute rather than the
abbreviated `4.4k` shown to readers, so a capture yields an integer, not an
estimate. The layout was reworked twice in the window we mine, hence the
alternatives.
"""


def collected_repos() -> dict[str, str]:
    """Every repository the collector touches, keyed by its series name.

    The benchmark columns plus the retired forerunners of
    {data}`PREDECESSOR_REPOS`, whose keys carry {data}`PREDECESSOR_SUFFIX` so a
    caller can tell the two apart without a second lookup.
    """
    repos = dict(TRACKED_REPOS)
    for column, slug in PREDECESSOR_REPOS.items():
        repos[column + PREDECESSOR_SUFFIX] = slug
    return repos


def load_store() -> dict[tuple[str, str], dict]:
    """Read the committed history, keyed by repository and date."""
    if not STORE.exists():
        return {}
    records = json.loads(STORE.read_text(encoding="UTF-8"))
    return {(r["repo"], r["date"]): r for r in records}


def save_store(store: dict[tuple[str, str], dict]) -> None:
    """Write the history back, sorted and tab-indented like its sibling.

    Merges whatever is on disk under the caller's own records rather than
    overwriting the file wholesale. The archive backfill flushes after every
    point across a run lasting hours, so it holds a snapshot that goes stale
    the moment anything else records a sample: without the merge its next
    flush silently drops those points. The history only ever grows, so
    preferring the in-memory copy on a conflict resolves it correctly.
    """
    merged = load_store() | store
    records = [merged[key] for key in sorted(merged)]
    STORE.write_text(
        json.dumps(records, indent="\t", sort_keys=True) + "\n", encoding="UTF-8"
    )


def upsert(
    store: dict[tuple[str, str], dict],
    repo: str,
    day: str,
    stars: int,
    source: str,
) -> bool:
    """Record one point, returning whether it changed anything.

    A re-run on the same day overwrites rather than appends, which is what keeps
    the scheduled job idempotent. A more authoritative source wins over a weaker
    one for the same day: an exact reconstruction supersedes an archived count.
    """
    key = (repo, day)
    previous = store.get(key)
    if previous and previous["stars"] == stars and previous["source"] == source:
        return False
    if previous and source == "wayback" and previous["source"] != "wayback":
        return False
    store[key] = {"date": day, "repo": repo, "source": source, "stars": stars}
    return True


def gh_api(path: str, *headers: str) -> Any:
    """Call the GitHub API through `gh`, inheriting its authentication.

    Returns the decoded JSON as {data}`~typing.Any`: the endpoints called here
    answer with a list or an object depending on the path, and narrowing that
    union at every call site costs more than the payload shapes are worth.
    """
    argv = ["gh", "api", path]
    for header in headers:
        argv += ["--header", header]
    result = subprocess.run(
        argv, capture_output=True, text=True, encoding="UTF-8", check=True
    )
    return json.loads(result.stdout)


def gh_graphql(query: str, **variables: str) -> Any:
    """Run a GraphQL query through `gh`, inheriting its authentication.

    The query travels as a raw field, since `--field` reads a value looking like
    a number or a boolean as one, and returns the `data` envelope unwrapped.
    """
    argv = ["gh", "api", "graphql", "--raw-field", f"query={query}"]
    for name, value in variables.items():
        argv += ["--field", f"{name}={value}"]
    result = subprocess.run(
        argv, capture_output=True, text=True, encoding="UTF-8", check=True
    )
    return json.loads(result.stdout)["data"]


def forge_json(url: str) -> Any:
    """Read one JSON document from a forge's public API.

    Covers every forge but GitHub, whose authentication `gh` already carries.
    The instances read here (GitLab and Forgejo) serve their project metadata
    to anonymous callers, so no token is involved and none is asked for.
    """
    payload = fetch(url, user_agent=FORGE_USER_AGENT)
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


class ForgeMetrics(NamedTuple):
    """One repository's popularity and activity, as any forge reports them."""

    stars: int
    """Count of accounts following the repository on its own forge."""

    release: str | None
    """ISO date of the newest release or tag, `None` when a project has neither."""

    release_source: str | None
    """Where {attr}`release` came from: a `release` object, or a bare `tag`.

    Recorded because the two are not the same claim. A release is something the
    project announced; a tag is only the newest thing it labelled, which is the
    closest available answer for the many upstreams that never cut a release.
    """

    commit: str | None
    """ISO date of the newest commit on the default branch.

    The second half of the activity reading, and the half that stays true for a
    rolling repository. Homebrew's cask tap last tagged a release in 2016 and is
    committed to several times a day: a release date alone would report the most
    used tap in the pool as a decade dead.
    """


def newest_dated(release: str | None, tag: str | None) -> tuple[str | None, str | None]:
    """Pick whichever of a project's newest release and newest tag is more recent.

    Not a preference for releases: six of the sampled upstreams carry a tag
    newer than their latest release object, `tlmgr` by eleven months, so
    always reading the release would report them as idle for a year. ISO dates
    compare as strings, which is the whole of the arithmetic here.
    """
    if release and tag:
        return (release, "release") if release >= tag else (tag, "tag")
    if release:
        return release, "release"
    if tag:
        return tag, "tag"
    return None, None


def github_metrics(path: str) -> ForgeMetrics:
    """Read a GitHub repository through {data}`GITHUB_METRICS_QUERY`."""
    owner, _, name = path.partition("/")
    repo = gh_graphql(GITHUB_METRICS_QUERY, owner=owner, name=name)["repository"]
    release = repo["latestRelease"]
    tag = None
    for node in repo["refs"]["nodes"]:
        # A lightweight tag points straight at its commit, an annotated one at a
        # tag object wrapping it, and the query asks for both shapes.
        target = node["target"]
        committed = target.get("committedDate") or (target.get("target") or {}).get(
            "committedDate"
        )
        if committed:
            tag = committed[:10]
    dated, source = newest_dated(release["publishedAt"][:10] if release else None, tag)
    branch = repo["defaultBranchRef"]
    return ForgeMetrics(
        repo["stargazerCount"],
        dated,
        source,
        branch["target"]["committedDate"][:10] if branch else None,
    )


def gitlab_metrics(host: str, path: str) -> ForgeMetrics | None:
    """Read a GitLab project, on whichever instance hosts it."""
    project = f"{host}/api/v4/projects/{urllib.parse.quote(path, safe='')}"
    payload = forge_json(project)
    if not payload:
        return None
    releases = forge_json(f"{project}/releases?per_page=1")
    # Ordering spelled out rather than inherited: it is GitLab's current default
    # for tags, but the whole point of asking is to not depend on that.
    tags = forge_json(
        f"{project}/repository/tags?per_page=1&order_by=updated&sort=desc"
    )
    commits = forge_json(f"{project}/repository/commits?per_page=1")
    dated, source = newest_dated(
        releases[0]["released_at"][:10] if releases else None,
        tags[0]["commit"]["created_at"][:10] if tags else None,
    )
    return ForgeMetrics(
        payload["star_count"],
        dated,
        source,
        commits[0]["committed_date"][:10] if commits else None,
    )


def forgejo_metrics(host: str, path: str) -> ForgeMetrics | None:
    """Read a Forgejo or Gitea repository, on whichever instance hosts it."""
    repo = f"{host}/api/v1/repos/{path}"
    payload = forge_json(repo)
    if not payload:
        return None
    releases = forge_json(f"{repo}/releases?limit=1")
    tags = forge_json(f"{repo}/tags?limit=1")
    commits = forge_json(f"{repo}/commits?limit=1")
    dated, source = newest_dated(
        releases[0]["published_at"][:10] if releases else None,
        tags[0]["commit"]["created"][:10] if tags else None,
    )
    return ForgeMetrics(
        payload["stars_count"],
        dated,
        source,
        commits[0]["commit"]["committer"]["date"][:10] if commits else None,
    )


def upstream_metrics(url: str) -> ForgeMetrics | None:
    """Read one upstream repository, through whichever API its host speaks."""
    host, _, path = url.removeprefix("https://").partition("/")
    forge = FORGE_APIS[host]
    if forge == "github":
        return github_metrics(path)
    if forge == "gitlab":
        return gitlab_metrics(f"https://{host}", path)
    return forgejo_metrics(f"https://{host}", path)


def load_upstreams() -> dict[str, dict]:
    """Read the committed upstream readings, keyed by manager ID."""
    if not UPSTREAMS.exists():
        return {}
    records = json.loads(UPSTREAMS.read_text(encoding="UTF-8"))
    return {record["id"]: record for record in records}


def save_upstreams(records: dict[str, dict]) -> None:
    """Write the upstream readings back, sorted and indented like {data}`STORE`."""
    ordered = [records[manager_id] for manager_id in sorted(records)]
    UPSTREAMS.write_text(
        json.dumps(ordered, indent="\t", sort_keys=True) + "\n", encoding="UTF-8"
    )


def sample_upstreams() -> int:
    """Snapshot the popularity and activity of every manager's upstream.

    A repository that fails to answer keeps its previous reading rather than
    losing it: one flaky instance must not blank a column of the manager index,
    and a stale figure carrying its own date is more useful than a hole.
    """
    today = datetime.now(tz=timezone.utc).date().isoformat()
    records = load_upstreams()
    # A manager that left the pool, or one whose upstream moved out of reach,
    # takes its reading with it: nothing downstream would ever read the row
    # again, and the conformance test rejects the file while it lingers.
    changed = 0
    for stale in set(records) - set(UPSTREAM_REPOS):
        del records[stale]
        changed += 1
        print(f"  {stale:14} dropped, no longer measured")
    for manager_id, url in sorted(UPSTREAM_REPOS.items()):
        try:
            metrics = upstream_metrics(url)
        except Exception as error:  # noqa: BLE001
            # Caught wide and per manager, like the star sampler's own loop: a
            # repository gone private, a host answering a payload of a shape
            # nobody anticipated or a forge added without its API declared must
            # cost one row, not the ninety-two others collected before it.
            metrics = None
            detail = getattr(error, "stderr", None) or repr(error)
            print(f"  {manager_id:14} {url}: FAILED ({detail.strip()[:60]})")
        if metrics is None:
            if manager_id not in records:
                print(f"  {manager_id:14} {url}: unreadable, and never sampled")
            continue
        record = {"date": today, "id": manager_id, "repo": url, "stars": metrics.stars}
        if metrics.release:
            record["release"] = metrics.release
            record["release_source"] = metrics.release_source
        if metrics.commit:
            record["commit"] = metrics.commit
        previous = records.get(manager_id)
        # Compared without their dates: a week where nothing moved must leave
        # the file untouched rather than restamping a hundred unchanged rows.
        if previous and {k: v for k, v in previous.items() if k != "date"} == {
            k: v for k, v in record.items() if k != "date"
        }:
            continue
        records[manager_id] = record
        changed += 1
        print(
            f"  {manager_id:14} {metrics.stars} stars, "
            f"{metrics.release_source or 'nothing'} {metrics.release or ''}, "
            f"commit {metrics.commit or 'unknown'}"
        )
    if changed:
        save_upstreams(records)
    return changed


def gunzip(blob: bytes) -> bytes:
    """Decompress a gzip payload, tolerating one cut short mid-stream.

    {class}`gzip.GzipFile` needs the trailer to finish, so it raises on the
    truncated bodies the archive delivers, discarding the megabyte that did
    arrive. Feeding the same bytes to a raw decompressor returns everything
    decodable before the cut and simply never reports the end of stream.
    """
    decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
    try:
        return decompressor.decompress(blob)
    except zlib.error:
        return b""


def fetch(
    url: str,
    tries: int = 3,
    timeout: int = 45,
    user_agent: str = USER_AGENT,
) -> bytes | None:
    """Fetch a URL with capped backoff, returning `None` once every try failed.

    The identity defaults to the browser one the archive wants and every forge
    refuses: see {data}`FORGE_USER_AGENT`.

    The archive's replay service is frequently only partly healthy: its
    load balancer answers `503` for most requests while a minority succeed,
    measured at roughly one in five during an outage, with neighbouring
    requests for the same capture landing on different backends. A failure
    therefore says nothing about whether the capture exists, and repeating the
    request is the lever that works. Pacing is not: the whole service is
    degraded, not this client's budget.

    The delay is capped rather than doubled without bound, since a long tail of
    attempts is what converts a low per-request success rate into a fetched
    page, and an uncapped schedule spends that budget waiting instead.
    """
    delay = 2.0
    reasons: Counter[str] = Counter()
    for attempt in range(1, tries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                gzipped = response.headers.get("Content-Encoding") == "gzip"
                try:
                    payload: bytes = response.read()
                except http.client.IncompleteRead as truncation:
                    # Kept, not discarded. A degraded backend routinely cuts the
                    # connection after sending most of the page, and the star
                    # counter sits in markup that arrives well before the end:
                    # measured over 25 requests, every delivery that was not a
                    # 503 arrived this way, so dropping them threw away the only
                    # payloads the run produced.
                    payload = truncation.partial
                    reasons["truncated"] += 1
                if gzipped:
                    payload = gunzip(payload)
                if payload:
                    return payload
                reasons["empty body"] += 1
        except urllib.error.HTTPError as error:
            reasons[f"HTTP {error.code}"] += 1
        except Exception as error:  # noqa: BLE001
            reasons[type(error).__name__] += 1
        if attempt < tries:
            time.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_DELAY)
    # Named rather than swallowed: a run that reports only "unreachable" cannot
    # tell a service refusing every request from one this collector is asking
    # wrongly, and those call for opposite responses.
    LAST_FETCH_REASONS.clear()
    LAST_FETCH_REASONS.update(reasons)
    return None


def sample(store: dict[tuple[str, str], dict]) -> int:
    """Snapshot today's aggregate star count of every tracked repository.

    The scheduled half of the pipeline, and the only collector that works for
    repositories the token does not administer.
    """
    today = datetime.now(tz=timezone.utc).date().isoformat()
    changed = 0
    for column, repo in collected_repos().items():
        try:
            payload = gh_api(f"repos/{repo}")
        except subprocess.CalledProcessError as error:
            # A single unreachable repository must not lose the other samples.
            print(f"  {column:9} {repo}: FAILED ({error.stderr.strip()[:70]})")
            continue
        stars = payload["stargazers_count"]
        if upsert(store, repo, today, stars, "sample"):
            changed += 1
        # Immutable, and free to re-assert: the repository object carries it on
        # every sample, so the origin is recorded without a second call.
        if upsert(store, repo, payload["created_at"][:10], 0, "created"):
            changed += 1
        print(f"  {column:9} {repo}: {stars} stars")
    return changed


def backfill_github(store: dict[tuple[str, str], dict], repo: str) -> int:
    """Reconstruct one repository's curve from per-star timestamps.

    Only works where the token administers the repository. Collapses to one
    cumulative point per day on which the count moved, rather than one per star.
    """
    per_day: Counter[str] = Counter()
    page = 1
    while True:
        try:
            batch = gh_api(
                f"repos/{repo}/stargazers?per_page=100&page={page}",
                "Accept: application/vnd.github.star+json",
            )
        except subprocess.CalledProcessError:
            # Expected for every repository the token does not administer:
            # GitHub answers 404 rather than 403 on the restricted endpoint.
            print("  stargazers not readable (not an admin), skipping")
            return 0
        if not batch:
            break
        for entry in batch:
            per_day[entry["starred_at"][:10]] += 1
        print(f"  page {page}: {len(batch)} stars")
        page += 1

    if not per_day:
        print("  no stargazers returned: the endpoint answered empty")
        return 0

    days = sorted(per_day)
    changed = 0
    for day, total in zip(days, accumulate(per_day[d] for d in days)):
        if upsert(store, repo, day, total, "github"):
            changed += 1
    print(f"  {len(days)} daily points, {per_day.total()} stars total")
    return changed


def wayback_captures(repo: str) -> list[str] | None:
    """List one archived capture per month of a repository's GitHub page.

    Returns `None` when the index itself could not be read, which is not the
    same answer as an empty list and must not be reported as one: the archive
    fails this query as readily as any other, and a run that treats the outage
    as "this repository was never archived" skips it silently and for good. A
    repository with 63 captures was passed over exactly that way.
    """
    query = urllib.parse.urlencode({
        "url": f"github.com/{repo}",
        "output": "json",
        "fl": "timestamp",
        "filter": "statuscode:200",
        "collapse": "timestamp:6",
    })
    payload = fetch("https://web.archive.org/cdx/search/cdx?" + query, tries=6)
    if payload is None:
        return None
    if not payload.strip():
        # A genuinely empty index answers 200 with no rows.
        return []
    try:
        return [row[0] for row in json.loads(payload)[1:]]
    except (json.JSONDecodeError, IndexError):
        # Unparseable is a fault, not an absence: same reasoning as above.
        return None


def backfill_wayback(store: dict[tuple[str, str], dict], repo: str) -> int:
    """Mine contemporaneous star counts from archived copies of a GitHub page.

    The only route to a competitor's past, and the only one that reports what
    the counter actually read on the day rather than what survives today.
    """
    if any(
        record["repo"] == repo and record["source"] == "github"
        for record in store.values()
    ):
        # An exact reconstruction already covers this repository, and mining it
        # would only add a second, differently-measured curve over the same
        # dates. The archives are slow and rate-limited: spend them on the
        # repositories that have no other source of history.
        print("  already reconstructed exactly, skipping the archives")
        return 0

    stamps = wayback_captures(repo)
    if stamps is None:
        # Loud, and distinct from "nothing was ever archived": this repository
        # still has a past to mine, so the next run must come back to it.
        tally = ", ".join(
            f"{count}x {reason}" for reason, count in LAST_FETCH_REASONS.most_common()
        )
        print(f"  capture index unreadable ({tally or 'no response'}), retry later")
        return 0
    print(f"  {len(stamps)} monthly captures")
    changed = 0
    for stamp in stamps:
        day = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        if (repo, day) in store:
            continue
        # Paced deliberately. The archive answers 503 to every URL form once a
        # sustained crawl exhausts its budget, and it stays shut for a while:
        # a run that races through the captures finishes by collecting nothing,
        # which is how the last repository of a long run came back empty while
        # the earlier ones succeeded.
        time.sleep(WAYBACK_REQUEST_DELAY)
        payload = fetch(
            f"https://web.archive.org/web/{stamp}id_/https://github.com/{repo}",
            tries=WAYBACK_PAGE_TRIES,
        )
        if not payload:
            tally = ", ".join(
                f"{count}x {reason}"
                for reason, count in LAST_FETCH_REASONS.most_common()
            )
            print(f"    {day}: unreachable ({tally or 'no response'})")
            continue
        html = payload.decode("utf-8", errors="replace")
        stars = None
        for pattern in WAYBACK_STAR_PATTERNS:
            match = pattern.search(html)
            if match:
                stars = int(match.group(1).replace(",", ""))
                break
        if stars is None:
            print(f"    {day}: no counter found")
            continue
        if upsert(store, repo, day, stars, "wayback"):
            changed += 1
            # Flushed per point: a run spans many minutes of a flaky remote.
            save_store(store)
        print(f"    {day}: {stars} stars")
    return changed


def series(store: dict[tuple[str, str], dict]) -> dict[str, list[tuple[date, int]]]:
    """Group the history into one chronological series per benchmark column."""
    grouped: dict[str, list[tuple[date, int]]] = {}
    for column, repo in collected_repos().items():
        # Coerced rather than trusted: the records come back from JSON as
        # `Any`, and letting that leak makes every downstream chart
        # coordinate untyped too.
        points = sorted(
            (date.fromisoformat(record["date"]), int(record["stars"]))
            for (rec_repo, _day), record in store.items()
            if rec_repo == repo
        )
        if points:
            grouped[column] = points

    # A forerunner's line stops where its successor's begins. The archived
    # repository keeps collecting the odd star to this day, and plotting that
    # tail would run it the whole width of the chart alongside the successor,
    # reading as two projects living side by side. Cutting it at the handover
    # shows what actually happened: one audience stopped being counted here and
    # started being counted there. The store keeps the discarded points, so the
    # record stays complete even though the chart does not draw them.
    for column in PREDECESSOR_REPOS:
        key = column + PREDECESSOR_SUFFIX
        if key not in grouped or column not in grouped:
            continue
        handover = grouped[column][0][0]
        clipped = [point for point in grouped[key] if point[0] <= handover]
        if clipped:
            grouped[key] = clipped
        else:
            del grouped[key]
    return grouped


def render_chart(
    store: dict[tuple[str, str], dict],
    columns: tuple[str, ...] | None = None,
    relative: bool = False,
) -> str:
    """Draw the line chart as a standalone, themeable SVG.

    Written by hand rather than through a plotting library: the output is
    committed, so the docs build never needs the dependency, and the file stays
    a few kilobytes of readable vector.

    :param columns: Benchmark columns to plot, defaulting to every tracked one.
        The history page asks for `mpm` alone, where the competition is not the
        subject and Homebrew-scale peers would only squash the curve.
    :param relative: Measure the horizontal axis from each repository's own
        creation rather than from the calendar, so projects born eight years
        apart are compared at the same age. Answers how fast a project gathered
        its following, where the calendar view answers when.
    """
    grouped = series(store)
    if columns is not None:
        grouped = {col: pts for col, pts in grouped.items() if col in columns}
    if not grouped:
        msg = "No star history recorded yet: run a sample or a backfill first."
        raise ValueError(msg)

    width, height = 960, 460
    left, right, top, bottom = 58, 168, 28, 46
    plot_w, plot_h = width - left - right, height - top - bottom

    all_points = [point for points in grouped.values() for point in points]
    first_day = min(day for day, _ in all_points)
    last_day = max(day for day, _ in all_points)
    peak = max(stars for _, stars in all_points)

    # Both modes plot a day offset; only its origin differs. Absolute measures
    # from the earliest date on the chart, so the curves share a calendar.
    # Relative measures each series from its own repository's creation, which
    # slides every project to a common birth and compares trajectories rather
    # than calendars.
    offsets: dict[str, list[tuple[int, int]]] = {}
    for column, points in grouped.items():
        origin = points[0][0] if relative else first_day
        offsets[column] = [((day - origin).days, stars) for day, stars in points]
    span = max(
        (max(x for x, _ in points) for points in offsets.values()),
        default=1,
    )
    span = max(span, 1)

    # Round the axis up to a decade-ish step so the top gridline is a whole
    # number the eye can anchor on. Annotated because `int ** int` widens to
    # `Any` (a negative exponent would yield a float), which would otherwise
    # leak all the way into the plotted coordinates.
    step: int = 10 ** (len(str(peak)) - 1)
    step = step // 2 if peak / step < 2 else step
    ceiling: int = ((peak // step) + 1) * step

    def x_of(offset: int) -> float:
        return left + offset / span * plot_w

    def y_of(stars: int) -> float:
        return top + plot_h - (stars / ceiling) * plot_h

    parts: list[str] = []

    # Horizontal gridlines and their value labels.
    ticks = [round(ceiling * i / 4) for i in range(5)]
    for value in ticks:
        y = y_of(value)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" '
            f'x2="{left + plot_w}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="tick" x="{left - 10}" y="{y + 4:.1f}" '
            f'text-anchor="end">{value:,}</text>'
        )

    # Vertical gridlines: calendar years when absolute, years of age when
    # relative. Thinned on a long relative span so the labels stay readable.
    if relative:
        stride = 1 + span // 365 // 8
        marks = [
            (year * 365, "1st year" if year == 1 else f"{year} years")
            for year in range(stride, span // 365 + 1, stride)
        ]
    else:
        marks = [
            ((date(year, 1, 1) - first_day).days, str(year))
            for year in range(first_day.year, last_day.year + 1)
            if first_day <= date(year, 1, 1) <= last_day
        ]
    for offset, caption in marks:
        x = x_of(offset)
        parts.append(
            f'<line class="grid" x1="{x:.1f}" y1="{top}" '
            f'x2="{x:.1f}" y2="{top + plot_h}"/>'
        )
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{top + plot_h + 20}" '
            f'text-anchor="middle">{caption}</text>'
        )

    # Series, drawn in the fixed palette order so a column keeps its hue.
    labels: list[tuple[float, str, str]] = []
    for key in collected_repos():
        # Distinct from the `points` bound above, which holds dates rather
        # than the day offsets this loop plots.
        shifted = offsets.get(key)
        if not shifted:
            continue
        # The separator, not the tail: `partition` returns what follows it,
        # which for a key ending in the suffix is always the empty string.
        column, prior, _ = key.partition(PREDECESSOR_SUFFIX)
        coords = " ".join(f"{x_of(x):.1f},{y_of(s):.1f}" for x, s in shifted)
        css = f"s-{column} prior" if prior else f"s-{column}"
        parts.append(f'<polyline class="{css}" points="{coords}"/>')
        end_offset, end_stars = shifted[-1]
        if prior:
            # Annotated where it stops rather than in the right margin: a
            # forerunner ends mid-chart, and a label parked at the edge would
            # read as its final position on a date it never reached.
            parts.append(
                f'<text class="lbl prior s-{column}" '
                f'x="{x_of(end_offset) + 6:.1f}" '
                f'y="{y_of(end_stars) - 8:.1f}">retired · {end_stars:,}</text>'
            )
            continue
        labels.append((y_of(end_stars), column, f"{end_stars:,}"))

    # Direct labels at each line's end. Three light-mode hues sit below 3:1
    # against the surface, and these labels are the relief that answers it.
    # Nudged apart so close finishers stay legible.
    labels.sort()
    for index in range(1, len(labels)):
        gap = labels[index][0] - labels[index - 1][0]
        if gap < 15:
            # Rebuilt field by field rather than with a starred unpack, which
            # widens the tuple to a homogeneous type mypy cannot match. The
            # names stay distinct from the axis-tick loop above, whose `value`
            # is an integer.
            _label_y, label_column, label_text = labels[index]
            labels[index] = (labels[index - 1][0] + 15, label_column, label_text)
    for label_y, label_column, label_text in labels:
        parts.append(
            f'<text class="lbl s-{label_column}" x="{left + plot_w + 12}" '
            f'y="{label_y + 4:.1f}">{label_column} · {label_text}</text>'
        )

    css_light = "\n".join(
        f"    .s-{col}{{stroke:{light};color:{light}}}"
        for col, (light, _dark) in SERIES_COLORS.items()
    )
    css_dark = "\n".join(
        f"      .s-{col}{{stroke:{dark};color:{dark}}}"
        for col, (_light, dark) in SERIES_COLORS.items()
    )

    stamp = datetime.now(tz=timezone.utc).date().isoformat()
    body = "\n  ".join(parts)
    if relative:
        caption = "GitHub stars by age of the project, aligned on each repository's creation"
        described = "GitHub stars of mpm and its benchmarked peers, by project age"
    else:
        caption = f"GitHub stars, {first_day} to {last_day}"
        described = "GitHub star history of mpm and its benchmarked peers"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     width="{width}" height="{height}" font-family="system-ui, sans-serif"
     role="img" aria-label="{described}">
  <style>
    text{{fill:#0b0b0b}}
    .tick{{font-size:12px;fill:#52514e}}
    .lbl{{font-size:13px;font-weight:600;fill:currentColor}}
    .grid{{stroke:#0b0b0b;stroke-opacity:.10;stroke-width:1}}
    .axis{{font-size:12px;fill:#52514e}}
    polyline{{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}}
    .prior{{stroke-dasharray:6 4;stroke-width:1.5;opacity:.65}}
    text.prior{{font-size:11px;font-weight:600;opacity:1}}
{css_light}
    @media (prefers-color-scheme: dark) {{
      text{{fill:#fff}}
      .tick,.axis{{fill:#c3c2b7}}
      .grid{{stroke:#fff;stroke-opacity:.14}}
{css_dark}
    }}
  </style>
  {body}
  <text class="axis" x="{left}" y="{height - 10}">{caption} · sampled by mpm on {stamp}</text>
</svg>
"""


def main() -> int:
    """Collect star history and render the chart."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Snapshot every tracked repository's current star count.",
    )
    parser.add_argument(
        "--sample-upstreams",
        action="store_true",
        help="Snapshot each manager's upstream popularity and activity.",
    )
    parser.add_argument(
        "--backfill-github",
        action="store_true",
        help="Reconstruct exact history for repositories the token administers.",
    )
    parser.add_argument(
        "--backfill-wayback",
        action="store_true",
        help="Mine contemporaneous counts from archived GitHub pages.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Redraw the committed SVG from the stored history.",
    )
    args = parser.parse_args()
    if not any(
        (
            args.sample,
            args.sample_upstreams,
            args.backfill_github,
            args.backfill_wayback,
            args.render,
        )
    ):
        parser.error("pick at least one mode")

    store = load_store()
    changed = 0

    if args.sample:
        print("Sampling current star counts:")
        changed += sample(store)

    # Counted apart from the chart's own points: this dataset has no curve to
    # redraw, and folding it into `changed` would re-render three SVGs every
    # time an unrelated upstream gained a star.
    if args.sample_upstreams:
        print("Sampling manager upstreams:")
        moved = sample_upstreams()
        print(f"\n{moved} upstream reading(s) updated in {UPSTREAMS.name}")

    if args.backfill_github:
        for column, repo in collected_repos().items():
            print(f"Reconstructing {column} ({repo}):")
            changed += backfill_github(store, repo)

    if args.backfill_wayback:
        for column, repo in collected_repos().items():
            print(f"Mining archives for {column} ({repo}):")
            changed += backfill_wayback(store, repo)

    if changed:
        save_store(store)
        print(f"\n{changed} point(s) recorded in {STORE.name}")

    if args.render or changed:
        for path, kwargs in (
            (CHART, {}),
            (CHART_RELATIVE, {"relative": True}),
            (CHART_MPM, {"columns": ("mpm",)}),
        ):
            path.write_text(render_chart(store, **kwargs), encoding="UTF-8")
            print(f"Chart written to {path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
