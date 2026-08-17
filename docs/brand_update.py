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

"""Export the project's own brand artwork: light and dark PNGs, and the app icons.

The SVGs under `docs/assets/` are the sources, and this script is the only thing
that writes a raster beside them. It exists because the dark exports are not files
anyone can open and edit: they are the light artwork with {data}`DARK_THEME`'s
substitutions baked in, and the mapping used to live nowhere but in whoever ran the
converter that day. That is how the wordmark and the mark drifted onto two
different purples in the first place.

Run by hand, like `docs/logos_update.py` beside it, and never from a docs build:
the exports are committed, so a build stays hermetic and needs no rasterizer.

```{note}
Only the lettering and the social card's own background differ between themes.
The mark itself is one artwork everywhere: flat faces need no outline, and a flat
face is legible on any surface, which is what an ink outline on a dark background
was not. That is also what lets `favicon.svg` and the app icons serve both themes
from a single rendering.
```
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets"
"""Directory holding both the SVG sources and their committed exports."""

INK = "#2d2364"
"""The deep purple of the mark's shadowed planes, its lettering and its lines.

One of the two colors the identity is built from, with {data}`WASH`. It fills
every left-facing face of the mark, the far-right interior wall behind the
floating cube, the `mpm` wordmark and, at 80%, the tagline. It used to be the
wordmark's alone while the mark's outline carried a third, lighter purple, which
is what left the two visibly mismatched.
"""

WASH = "#d3d3f6"
"""The pale lavender of every lit plane, and of the lettering on a dark surface.

The second brand color, and the mark's brightest value: the four flaps and the
three cube lids.
"""

MID = "#807bad"
"""The exact midpoint of {data}`INK` and {data}`WASH`, for the third plane.

Not a third brand color so much as the one value a flat isometric solid cannot
do without: with no outline left to carry the structure, each of the three planes
a face can point at needs a value of its own. Computed rather than chosen, so the
palette stays two colors and a derivation: `#807bad` is `(0x2d+0xd3)/2`,
`(0x23+0xd3)/2`, `(0x64+0xf6)/2`.

It paints the right-facing faces and, mirrored, the far-left interior wall: an
interior wall is lit as the plane it faces, not as the one it sits behind, which
is also what keeps the floating cube's own ink face from disappearing into the
wall behind it.
"""

DARK_THEME = {
    # Only the lettering and the card's own surfaces move. The mark keeps its
    # three planes: a flat face is legible on any background, which is what an
    # ink outline on a dark one was not.
    f".word{{fill:{INK}}}": f".word{{fill:{WASH}}}",
    f".sub{{fill:{INK};fill-opacity:.8}}": f".sub{{fill:{WASH};fill-opacity:.8}}",
    # The social banner's background is the only opaque surface, and the only
    # value that cannot be expressed as one of the two colors over white: the ink
    # mixed 45% into black, dark enough for the wash to read against it.
    ".bg{fill:#e7e7fa}": ".bg{fill:#141029}",
    # Veins are the wash rather than the ink once the surface under them is dark.
    f"stroke:{INK};stroke-width:3": f"stroke:{WASH};stroke-width:3",
}
"""Substitutions turning a light SVG source into its dark rendering.

Applied to the source text, never to a committed file: {func}`export_png` bakes
them into a temporary copy and rasterizes that. Every key is a whole CSS rule as
written in the sources, which is what keeps the swap off the mark: `.mpm-left`
names the same ink the wordmark does, and a substitution keyed on the color alone
would repaint every shadowed plane of a mark meant to look identical on both
themes. A key that stops matching shows up as an unchanged export rather than as
a silent partial swap.
"""

DARK_DECLARATIONS = re.compile("|".join(map(re.escape, DARK_THEME)))
"""One alternation over every {data}`DARK_THEME` key, for the single-pass swap."""

BRAND_SVGS = (
    "banner-social.svg",
    "favicon.svg",
    "icon.svg",
    "logo-banner.svg",
    "logo-square.svg",
)
"""The SVGs this script owns, and the only ones held to the two-purple palette.

`docs/assets/` also holds artwork with a palette of its own that nothing here
should touch: the mascot illustrations and the star-history charts drawn by
`repomatic sample-metrics`.
"""

EXPORTS = (
    ("logo-square.svg", "logo-square", 640, 640),
    ("logo-banner.svg", "logo-banner", 1280, 454),
    ("banner-social.svg", "banner-social", 1200, 630),
)
"""Each `(source, stem, width, height)` exported as a light and a dark PNG.

`favicon.svg` is absent on purpose: browsers render an SVG favicon natively, and
the mark it carries is the same under either theme.
"""

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
"""Square renderings of `icon.svg` packed into the platform icon bundles.

Nuitka ships one icon per platform (`[tool.nuitka]` in `pyproject.toml`): `.png`
for Linux, `.ico` for Windows, `.icns` for macOS. A single set of renderings feeds
all three, the app icon carrying no lettering and so needing no theme variant.
"""


def rasterizer() -> str:
    """Path to `rsvg-convert`, the one converter this script drives.

    Chosen over Inkscape's command line for being a library front-end rather than
    an editor: it starts in milliseconds and renders the same bytes on any host.
    """
    path = shutil.which("rsvg-convert")
    if not path:
        sys.exit("rsvg-convert not found: install librsvg (brew install librsvg).")
    return path


def export_png(source: Path, target: Path, width: int, height: int, dark: bool) -> None:
    """Render `source` to `target`, baking the dark substitutions when asked.

    {data}`DARK_THEME` is applied in a single pass over the source, so no
    replacement can be re-read as a key by a later one.
    """
    text = source.read_text(encoding="UTF-8")
    if dark:
        text = DARK_DECLARATIONS.sub(lambda match: DARK_THEME[match.group()], text)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".svg", encoding="UTF-8", delete=False
    ) as baked:
        baked.write(text)
        baked_path = Path(baked.name)
    try:
        subprocess.run(
            (
                rasterizer(),
                "--width",
                str(width),
                "--height",
                str(height),
                "--output",
                str(target),
                str(baked_path),
            ),
            check=True,
        )
    finally:
        baked_path.unlink()


def export_icons() -> None:
    """Repack `icon.svg` into the three platform icon formats.

    Renders one PNG per {data}`ICON_SIZES` entry into a temporary directory, then
    lets `magick` assemble the multi-resolution `.ico` and `.icns` bundles from
    them. The Linux `.png` is the 128px rendering, kept at the size the committed
    one already had.
    """
    source = ASSETS_DIR / "icon.svg"
    with tempfile.TemporaryDirectory() as tmp:
        renders = []
        for size in ICON_SIZES:
            render = Path(tmp) / f"icon-{size}.png"
            export_png(source, render, size, size, dark=False)
            renders.append(render)
        shutil.copyfile(Path(tmp) / "icon-128.png", ASSETS_DIR / "icon.png")
        magick = shutil.which("magick")
        if not magick:
            sys.exit(
                "magick not found: install ImageMagick (brew install imagemagick)."
            )
        for bundle in ("icon.ico", "icon.icns"):
            subprocess.run(
                (magick, *(str(p) for p in renders), str(ASSETS_DIR / bundle)),
                check=True,
            )


def check_palette() -> list[str]:
    """Report every color in the SVG sources that is not one of the two purples.

    Inkscape's own editor chrome (`bordercolor`, `pagecolor`) is skipped: it lives
    in the `sodipodi:namedview` element, is never rendered, and would otherwise
    report as a stray gray on every run.
    """
    strays = []
    for name in BRAND_SVGS:
        svg = ASSETS_DIR / name
        text = re.sub(
            r"<sodipodi:namedview[\s\S]*?/>",
            "",
            svg.read_text(encoding="UTF-8"),
        )
        for color in sorted({m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}", text)}):
            if color not in {INK, MID, WASH, "#e7e7fa"}:
                strays.append(f"{name}: {color}")
    return strays


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check-palette",
        action="store_true",
        help="Report colors outside the two-purple palette, and exit.",
    )
    args = parser.parse_args()

    if args.check_palette:
        strays = check_palette()
        for stray in strays:
            print(stray)
        sys.exit(1 if strays else 0)

    for source_name, stem, width, height in EXPORTS:
        source = ASSETS_DIR / source_name
        for theme in ("light", "dark"):
            target = ASSETS_DIR / f"{stem}-{theme}.png"
            export_png(source, target, width, height, dark=theme == "dark")
            print(f"Wrote {target.relative_to(ASSETS_DIR.parent.parent)}")
    export_icons()
    print("Wrote the app icons.")
