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

"""Sample GitHub stars of `mpm` and its benchmarked peers, and plot the history.

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
import gzip
import io
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from itertools import accumulate
from pathlib import Path
from typing import Any

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


def fetch(url: str, tries: int = 3, timeout: int = 45) -> bytes | None:
    """Fetch a URL with backoff, returning `None` once every attempt failed.

    The Wayback Machine answers `503` and truncates responses under load, often
    for minutes at a time, so a single failure never means a missing capture.
    """
    delay = 2.0
    for attempt in range(1, tries + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload: bytes = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    # Annotated above: `GzipFile.read()` is untyped, and the
                    # reassignment would otherwise widen `payload` to `Any`.
                    payload = gzip.GzipFile(fileobj=io.BytesIO(payload)).read()
                return payload
        except Exception:  # noqa: BLE001
            if attempt < tries:
                time.sleep(delay)
                delay *= 2
    return None


def sample(store: dict[tuple[str, str], dict]) -> int:
    """Snapshot today's aggregate star count of every tracked repository.

    The scheduled half of the pipeline, and the only collector that works for
    repositories the token does not administer.
    """
    today = datetime.now(tz=timezone.utc).date().isoformat()
    changed = 0
    for column, repo in TRACKED_REPOS.items():
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


def wayback_captures(repo: str) -> list[str]:
    """List one archived capture per month of a repository's GitHub page."""
    query = urllib.parse.urlencode({
        "url": f"github.com/{repo}",
        "output": "json",
        "fl": "timestamp",
        "filter": "statuscode:200",
        "collapse": "timestamp:6",
    })
    payload = fetch("https://web.archive.org/cdx/search/cdx?" + query, tries=4)
    if not payload or not payload.strip():
        return []
    try:
        return [row[0] for row in json.loads(payload)[1:]]
    except (json.JSONDecodeError, IndexError):
        return []


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
            tries=3,
        )
        if not payload:
            print(f"    {day}: unreachable")
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
    for column, repo in TRACKED_REPOS.items():
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
    for column in TRACKED_REPOS:
        # Distinct from the `points` bound above, which holds dates rather
        # than the day offsets this loop plots.
        shifted = offsets.get(column)
        if not shifted:
            continue
        coords = " ".join(f"{x_of(x):.1f},{y_of(s):.1f}" for x, s in shifted)
        parts.append(f'<polyline class="s-{column}" points="{coords}"/>')
        _end_offset, end_stars = shifted[-1]
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
        (args.sample, args.backfill_github, args.backfill_wayback, args.render)
    ):
        parser.error("pick at least one mode")

    store = load_store()
    changed = 0

    if args.sample:
        print("Sampling current star counts:")
        changed += sample(store)

    if args.backfill_github:
        for column, repo in TRACKED_REPOS.items():
            print(f"Reconstructing {column} ({repo}):")
            changed += backfill_github(store, repo)

    if args.backfill_wayback:
        for column, repo in TRACKED_REPOS.items():
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
