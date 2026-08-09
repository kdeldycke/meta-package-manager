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

"""Vendor the brand marks rendered atop the per-manager documentation pages.

Downloads one SVG per distinct `logo` slug declared in the pool, normalizes it and
writes it to `docs/assets/managers/`, alongside a `logos.yaml` manifest recording
each mark's title, brand color, upstream source and license.

Run by hand, never from CI or a docs build: the artwork is committed, so a build
stays hermetic and an upstream icon removal can never break it. Deliberately kept
out of `docs/docs_update.py` for that reason, since repomatic's `update-docs` job
runs that one on every push.

Artwork comes from [Simple Icons](https://simpleicons.org), pinned to
{data}`SIMPLE_ICONS_VERSION`. The set is CC0-1.0 as a whole, with a per-icon
license override for the marks whose owner requires attribution; both are recorded
in the manifest, which feeds the credits block of `docs/license.md`. Simple Icons
honors brand removal requests, so a manager whose upstream polices its mark simply
has no `logo` and keeps the default package glyph on its page.

```{note}
Every mark is stored monochrome and unfilled, so the page inherits `currentColor`
and adapts to the light and dark themes. The brand color is applied on the light
theme only, and only when it clears {data}`MIN_CONTRAST` against a white
background: a pale yellow mark is dropped back to `currentColor` rather than
rendered nearly invisible.
```
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

import yaml

from meta_package_manager.pool import pool

PROJECT_ROOT = Path(__file__).parent.parent

DEFAULT_LICENSE = "CC0-1.0"
"""Blanket license of the Simple Icons set, used for every mark declaring none."""

LOGO_DIR = PROJECT_ROOT / "docs" / "assets" / "managers"
"""Directory wholly owned by this script: one SVG per slug, plus the manifest."""

MANIFEST = LOGO_DIR / "logos.yaml"
"""Provenance of each vendored mark, consumed by the documentation generators."""

MIN_CONTRAST = 3.0
"""Lowest contrast ratio a brand color may have against the light theme.

The 3:1 floor [WCAG 2.2 sets for non-text
contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html),
which is the applicable rule for a graphical object. Marks failing it (OpenBSD's
yellow, Homebrew's amber) render in `currentColor` instead of their brand color.
"""

SIMPLE_ICONS_REPO = "https://github.com/simple-icons/simple-icons"

SIMPLE_ICONS_VERSION = "16.28.0"
"""Pinned upstream release, so a refresh is reproducible and reviewable."""

UNSAFE_MARKUP = re.compile(
    r"<(script|image|foreignObject)\b|xlink:href|url\(", re.IGNORECASE
)
"""Markup that has no place in a static mark, and would fetch or execute.

The vendored files are inlined verbatim into the built pages, so this is the gate
that keeps a compromised upstream from smuggling anything executable or
network-bound into the documentation. `test_manager_logo_assets` re-checks the
committed files, so the guard survives a hand edit.
"""


def raw_url(path: str) -> str:
    """Build a `raw.githubusercontent.com` URL for the pinned Simple Icons tag."""
    return (
        "https://raw.githubusercontent.com/simple-icons/simple-icons/"
        f"{SIMPLE_ICONS_VERSION}/{path}"
    )


def fetch(url: str, retries: int = 3) -> str:
    """Download a text resource, retrying the truncated reads the CDN serves.

    Fetching the whole set in one run reliably trips over an `IncompleteRead` or a
    reset connection somewhere in the sequence, which would otherwise abort a
    refresh halfway through and leave the directory half-written.
    """
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                body: str = response.read().decode("UTF-8")
                return body
        except (OSError, http.client.HTTPException) as ex:
            if attempt == retries:
                raise
            print(f"  retrying {url} after {type(ex).__name__}")
            time.sleep(attempt)
    raise AssertionError("unreachable")


def slugify(title: str) -> str:
    """Derive a Simple Icons slug from a brand title, following their own rules.

    Reimplemented rather than imported: the upstream mapping lives in their
    JavaScript SDK, and only the handful of titles carrying a diacritic or a
    symbol needs the transliteration table.
    """
    replacements = {
        "+": "plus",
        ".": "dot",
        "&": "and",
        "đ": "d",
        "ħ": "h",
        "ı": "i",
        "ĸ": "k",
        "ŀ": "l",
        "ł": "l",
        "ß": "ss",
        "ŧ": "t",
        "ø": "o",
    }
    text = title.lower()
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z\d]", "", text)


def relative_luminance(hex_color: str) -> float:
    """Compute the [WCAG relative
    luminance](https://www.w3.org/WAI/GL/wiki/Relative_luminance) of an RGB color.
    """
    channels = []
    for offset in (0, 2, 4):
        channel = int(hex_color[offset : offset + 2], 16) / 255
        if channel <= 0.04045:
            channels.append(channel / 12.92)
        else:
            channels.append(((channel + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_on_white(hex_color: str) -> float:
    """Contrast ratio of a brand color against the light theme's white background."""
    return round((1.0 + 0.05) / (relative_luminance(hex_color) + 0.05), 2)


def normalize_svg(body: str, title: str) -> str:
    """Reduce an upstream SVG to the minimal form inlined into the pages.

    Keeps the drawing and its `<title>`, drops the `xmlns` declaration (redundant
    once inlined into HTML) and every presentational attribute, so the mark
    inherits its color from the page. Emitted on a single line: the result is
    injected into MyST, where a blank line would split the raw HTML block.
    """
    match = re.search(r"<svg\b[^>]*>(?P<inner>.*)</svg>", body, re.DOTALL)
    if not match:
        raise ValueError(f"{title}: no <svg> element found.")
    inner = " ".join(match.group("inner").split())

    if UNSAFE_MARKUP.search(inner):
        raise ValueError(f"{title}: unsafe markup in the upstream SVG.")
    if 'fill="' in inner:
        raise ValueError(f"{title}: upstream SVG carries a hard-coded fill.")

    if f"<title>{title}</title>" not in inner:
        inner = f"<title>{title}</title>{re.sub(r'<title>.*?</title>', '', inner)}"
    return f'<svg viewBox="0 0 24 24">{inner}</svg>\n'


def icon_license(entry: dict) -> str:
    """Read a mark's effective license, defaulting to the set's blanket one."""
    declared: dict[str, str] | None = entry.get("license")
    if not declared:
        return DEFAULT_LICENSE
    # A "custom" license points at the owner's own brand policy instead of an
    # SPDX identifier, so the URL is the only citable form.
    if declared["type"] == "custom":
        return declared["url"]
    return declared["type"]


def collect(slugs: dict[str, list[str]]) -> tuple[dict[str, str], dict]:
    """Download every mark and assemble the manifest.

    :param slugs: Manager IDs to render, keyed by the slug they declare.
    :return: The SVG of each slug, and the manifest as a plain mapping.
    """
    catalog = json.loads(fetch(raw_url("data/simple-icons.json")))
    entries = {}
    for entry in catalog["icons"] if isinstance(catalog, dict) else catalog:
        slug = (entry.get("aliases") or {}).get("slug") or slugify(entry["title"])
        entries[slug] = entry

    svgs = {}
    icons = {}
    for slug in sorted(slugs):
        entry = entries.get(slug)
        if entry is None:
            raise KeyError(
                f"{slug!r} is gone from Simple Icons {SIMPLE_ICONS_VERSION}. "
                f"Drop the `logo` of {', '.join(slugs[slug])} or vendor it by hand."
            )
        svgs[slug] = normalize_svg(fetch(raw_url(f"icons/{slug}.svg")), entry["title"])
        icons[slug] = {
            "contrast_on_light": contrast_on_white(entry["hex"]),
            "hex": entry["hex"],
            "license": icon_license(entry),
            "managers": sorted(slugs[slug]),
            "source": entry["source"],
            "title": entry["title"],
        }

    manifest = {
        "icons": icons,
        "upstream": {
            "license": DEFAULT_LICENSE,
            "name": "Simple Icons",
            "url": SIMPLE_ICONS_REPO,
            "version": SIMPLE_ICONS_VERSION,
        },
    }
    return svgs, manifest


def render_manifest(manifest: dict) -> str:
    """Serialize the manifest with its provenance header."""
    header = (
        "# Brand marks vendored for the per-manager documentation pages.\n"
        "#\n"
        "# Regenerated by tools/update_manager_logos.py, never by hand. The\n"
        "# credits block of docs/license.md renders from this file.\n"
    )
    body = yaml.safe_dump(manifest, sort_keys=True, default_flow_style=False, indent=2)
    return f"{header}{body}"


def main() -> int:
    """Refresh every vendored mark, or report what a refresh would change."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report out-of-date marks and exit non-zero without writing.",
    )
    args = parser.parse_args()

    slugs: dict[str, list[str]] = {}
    for manager_id, manager in pool.items():
        if manager.logo:
            slugs.setdefault(manager.logo, []).append(manager_id)

    svgs, manifest = collect(slugs)
    files = {f"{slug}.svg": svg for slug, svg in svgs.items()}
    files[MANIFEST.name] = render_manifest(manifest)

    if not args.check:
        LOGO_DIR.mkdir(parents=True, exist_ok=True)

    drifted = []
    for path in sorted(LOGO_DIR.glob("*")) if LOGO_DIR.exists() else []:
        if path.name not in files:
            drifted.append(f"orphan: {path.name}")
            if not args.check:
                path.unlink()

    for name, content in files.items():
        path = LOGO_DIR / name
        if path.exists() and path.read_text(encoding="UTF-8") == content:
            continue
        drifted.append(f"{'stale' if path.exists() else 'missing'}: {name}")
        if not args.check:
            path.write_text(content, encoding="UTF-8")

    if args.check:
        for item in drifted:
            print(f"Out of date: {item}")
        return 1 if drifted else 0

    faded = sorted(
        slug
        for slug, icon in manifest["icons"].items()
        if icon["contrast_on_light"] < MIN_CONTRAST
    )
    print(f"{len(svgs)} marks for {sum(len(m) for m in slugs.values())} managers.")
    print(f"{len(faded)} below the {MIN_CONTRAST}:1 floor, drawn in currentColor:")
    print(f"  {', '.join(faded)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
