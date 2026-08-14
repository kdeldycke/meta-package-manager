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
"""Terminal rendition of the mpm brand mark, and the `--version` screen it decorates.

The mark is the isometric open box of `docs/assets/logo-square.svg`, redrawn as a
half-block raster: two sub-pixel rows share one terminal line, so {data}`LOGO` paints
as half as many lines as it has rows.

Half-blocks are the primitive because a terminal cell is twice as tall as it is
wide, which makes their sub-pixels square. That also rules out the alternative worth
naming, since it looks obvious and is not: drawing the mark as directional line-art
characters (`╱`, `╲`, `│`), the way edge-detection ASCII art does. An isometric edge
sits at slope `0.25` in cell space, far too shallow for `╱`, and that figure is
scale-invariant — no height fixes it. Stretching the projection to 45° earns the
diagonals but leaves the mark only ~12 columns wide, too few for the four flaps.

```{caution}
The mark's structure is carried by *color* alone: strip the ANSI codes and it
collapses into one solid silhouette. {class}`LogoVersionOption` therefore only draws
it when color reaches the output, falling back to click-extra's plain rendering
everywhere else — which is also the form machine readers parse, the bar plugin
probing `mpm --no-color --version`.
```
"""

from __future__ import annotations

import platform
import shutil

import click
from click_extra import style
from click_extra.color import invocation_color, is_a_tty
from click_extra.commands import default_params
from click_extra.context import ACCESSIBLE, get
from click_extra.version import VersionOption
from extra_platforms import current_architecture, current_platform

from .pool import pool

DOCS_URL = "https://mpm.run"
"""Canonical documentation host, advertised on the version screen."""

TAGLINE = "Meta Package Manager"
"""What the `mpm` acronym stands for, as spelled out under the logo's wordmark."""

LOGO: tuple[str, ...] = (
    "       ..    ..       ",
    "     .....  .....     ",
    "   ......    ......   ",
    " ......        ...... ",
    " ....    ....    .... ",
    "   .     ++::     .   ",
    "  ...    ++::    ...  ",
    " ......   +:   ...... ",
    "  ......      ......  ",
    "   +......  ......:   ",
    "   +++....+:....:::   ",
    "   ++++++++::::::::   ",
    "   ++++++++::::::::   ",
    "   ++++++++::::::::   ",
    "    +++++++:::::::    ",
    "      +++++:::::      ",
    "        +++:::        ",
    "          +:          ",
)
"""The mark, as one shading tone per sub-pixel, two rows to a rendered line.

A space is transparent and leaves the terminal's own background alone. The rest name
the plane the sub-pixel faces, which is what an isometric solid shades by: `.` up
(the flap tops and the cube's lid), `:` right, `+` left. No outlines: the solid is
reconstructed from the three shades its planes catch, the way an unlit render reads.

Rasterized from a model re-derived from the SVG's polygon geometry — rim, flap fold
depth, body height and cube placement all measured off it — then mirrored about its
vertical axis, swapping `+` for `:` since what faces left on one side faces right on
the other. Symmetry is imposed at that point rather than left to the rasterizer,
which drifted three separate ways: a column count rounded off the row scale left the
sampling grid off-centre, paint order tilted mirror-paired surfaces, and an odd
column count gave the axis a column that would have had to face both ways at once.

Hand-editing a row is fine, but keep the rows equal in length and even in number,
keep the width even, and keep every row symmetric.
"""

TONES: dict[str, int] = {
    ".": 189,  # `#d7d7ff`, standing in for the artwork's `#d3d3f6` fill.
    ":": 103,  # `#8787af`, a mid tone interpolated for the right-hand faces.
    "+": 60,  # `#5f5f87`, standing in for the artwork's `#534d73` stroke.
}
"""Xterm-256 palette index per shading tone of {data}`LOGO`.

Indices rather than truecolor: the 256-color cube is the widest-supported palette
that still lands within a few units of the brand colors, and click emits no downgrade
of its own for a terminal that cannot do 24-bit.
"""

LOGO_WIDTH = len(LOGO[0])
"""Columns the mark occupies, every rendered line being padded to it."""

LOGO_LINES = len(LOGO) // 2
"""Terminal lines the mark renders to, two sub-pixel rows making one."""

GUTTER = "   "
"""Blank columns separating the mark from the metadata column beside it."""

LABEL_WIDTH = 10
"""Column width the metadata keys are padded to, aligning their values."""

_UPPER = "▀"
_LOWER = "▄"
_FULL = "█"

Colors = tuple[int | None, int | None]
"""A cell's foreground and background palette indices.

`None` is transparent, leaving the terminal's own color to show through.
"""


def env_summary() -> str:
    """One-line interpreter and platform summary.

    Feeds both the plain `--version` output (as click-extra's `env_info` template
    field) and the version screen's own `Python` and `Platform` rows, so the two
    renderings can never disagree on what they report.
    """
    return f"Python {platform.python_version()}, {platform_label()}"


def platform_label() -> str:
    """Current platform and CPU architecture, as displayed to the user."""
    return f"{current_platform().name} {current_architecture().name}"


def render_logo() -> tuple[str, ...]:
    """Paint {data}`LOGO` into styled lines, one per pair of sub-pixel rows.

    A cell whose two sub-pixels carry different tones paints the top one as
    foreground over the bottom one as background, which is what fits two independent
    colors on one line. Runs of cells sharing a color pair are styled together rather
    than one escape sequence per character, keeping the mark from tripling in size.
    """
    lines = []
    for row in range(0, len(LOGO), 2):
        line = ""
        run = ""
        colors: Colors = (None, None)
        for over, under in zip(LOGO[row], LOGO[row + 1]):
            pair: Colors
            if over == " " and under == " ":
                char, pair = " ", (None, None)
            elif under == " ":
                char, pair = _UPPER, (TONES[over], None)
            elif over == " ":
                char, pair = _LOWER, (TONES[under], None)
            elif over == under:
                char, pair = _FULL, (TONES[over], None)
            else:
                char, pair = _UPPER, (TONES[over], TONES[under])
            if pair != colors:
                line += _paint(run, colors)
                run, colors = "", pair
            run += char
        lines.append(line + _paint(run, colors))
    return tuple(lines)


def _paint(run: str, colors: Colors) -> str:
    """Style a run of cells, leaving fully transparent ones as bare spaces.

    Transparent runs must not go through `style()`: it would wrap them in a reset
    sequence, which costs bytes and, worse, cancels nothing while looking like it
    might.
    """
    if not run or colors == (None, None):
        return run
    return style(run, fg=colors[0], bg=colors[1])


def _metadata(prog_name: str, version: str) -> tuple[tuple[str, str], ...]:
    """The column of facts rendered beside the mark, as (plain, styled) pairs.

    Both forms are built together because the styled one cannot be measured: its
    escape sequences take columns that never reach the screen, and the plain twin is
    what {func}`version_screen` sizes the layout against.
    """
    supported = len(pool.default_manager_ids)
    total = len(pool.all_manager_ids)
    rows = (
        ("Python", platform.python_version()),
        ("Platform", platform_label()),
        ("Managers", f"{supported} supported here, {total} total"),
        ("Docs", DOCS_URL),
    )
    return (
        (
            f"{prog_name}, version {version}",
            style(prog_name, fg="bright_white", bold=True)
            + ", version "
            + style(version, fg="green"),
        ),
        (TAGLINE, style(TAGLINE, fg="bright_black")),
        ("", ""),
        *(
            (
                f"{label:<{LABEL_WIDTH}}{value}",
                style(f"{label:<{LABEL_WIDTH}}", fg="bright_black") + value,
            )
            for label, value in rows
        ),
    )


def version_screen(prog_name: str, version: str) -> str | None:
    """Compose the mark and the metadata column into the full version screen.

    The metadata is centred against the mark's height, and either column may be the
    taller of the two: a line missing from one side simply renders blank.

    Returns `None` when the terminal is too narrow to seat the two columns side by
    side, leaving the caller to fall back rather than emit a wrapped mess. The
    threshold is measured off the metadata actually built, since its widest row grows
    with the manager count and the platform name. A non-interactive stream reports
    `shutil`'s 80-column default, wide enough that a redirected-but-forced-color run
    still gets the screen it asked for.
    """
    metadata = _metadata(prog_name, version)
    width = LOGO_WIDTH + len(GUTTER) + max(len(plain) for plain, _ in metadata)
    if width > shutil.get_terminal_size().columns:
        return None

    logo = render_logo()
    offset = max(0, (len(logo) - len(metadata)) // 2)
    blank = " " * LOGO_WIDTH
    lines = []
    for index in range(max(len(logo), offset + len(metadata))):
        left = logo[index] if index < len(logo) else blank
        text_index = index - offset
        right = metadata[text_index][1] if 0 <= text_index < len(metadata) else ""
        lines.append(f"{left}{GUTTER}{right}".rstrip())
    # Open on a blank line: `--version` is often the tail of a noisier command (a
    # `uv run` resolving, a wrapper announcing itself), and the mark reads as part of
    # that noise when it starts flush against it.
    return "\n" + "\n".join(lines)


def colors_reach_output() -> bool:
    """Will ANSI codes survive all the way to the user's terminal?

    Resolves click-extra's color tri-state, deferring to the output stream's TTY
    status on its `auto` default, exactly as `click.echo` does when it decides
    whether to strip the codes itself.
    """
    color = invocation_color()
    if color is None:
        return is_a_tty(click.get_text_stream("stdout"))
    return color


class LogoVersionOption(VersionOption):
    """`--version`, upgraded to the full version screen when the terminal allows it.

    Three conditions gate the screen, and failing any one of them falls back to
    click-extra's plain `message` template unchanged — which is a deliberate
    guarantee, not just a default: that plain form is the one every machine reader
    parses.

    - **Color reaches the output.** The mark keeps its structure in its colors alone,
      so a stripped one is an unreadable blob.
    - **The terminal is wide enough** to seat the metadata column beside the mark
      without wrapping it.
    - **Accessible mode is off.** A raster read out cell by cell is noise to a screen
      reader, so `--accessible` keeps the plain two lines.
    """

    def render_message(self, template: str | None = None) -> str:
        """Draw the version screen, or defer to the plain template."""
        ctx = click.get_current_context(silent=True)
        accessible = bool(ctx is not None and get(ctx, ACCESSIBLE, False))
        # An explicit template is a caller asking for that exact string, never for a
        # screen built around it.
        if template is None and not accessible and colors_reach_output():
            screen = version_screen(
                str(self.prog_name or ""),
                str(self.version or ""),
            )
            if screen is not None:
                return screen
        return super().render_message(template)


def version_screen_params() -> list[click.Parameter]:
    """click-extra's default parameters, with `--version` swapped for our own.

    Passed to the CLI's `@group(params=…)`, the documented hook for tuning that list.
    Swapping the instance in place keeps click-extra's carefully ordered parameter
    sequence, and keeps `version_fields=` working: it targets whichever parameter is
    a {class}`~click_extra.version.VersionOption`, which the subclass still is.
    """
    return [
        LogoVersionOption() if isinstance(param, VersionOption) else param
        for param in default_params()
    ]
