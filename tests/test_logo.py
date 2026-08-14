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

import os
import re
import shutil

import pytest
from boltons.strutils import strip_ansi

from meta_package_manager.logo import (
    GUTTER,
    LOGO,
    LOGO_LINES,
    LOGO_WIDTH,
    TONES,
    env_summary,
    render_logo,
    version_screen,
)

PROG, VERSION = "mpm", "1.2.3"

BLANK = " "

MIRROR = str.maketrans({"+": ":", ":": "+"})
"""Reflecting the mark swaps its two vertical planes, left-facing for right."""


def screen_lines(*args, **kwargs) -> list[str]:
    """The version screen body, stripped of ANSI and split into lines.

    Drops the leading blank the screen opens on, so every assertion below indexes
    the mark itself.
    """
    screen = version_screen(*args, **kwargs)
    assert screen is not None
    lines = strip_ansi(screen).split("\n")
    assert lines[0] == ""
    return lines[1:]


def test_logo_is_rectangular_and_pairable():
    """Rows must be equal-length and even in count, or the half-blocks desync."""
    assert len(LOGO) % 2 == 0
    assert len({len(row) for row in LOGO}) == 1


def test_declared_dimensions_match_the_logo():
    assert LOGO_WIDTH == len(LOGO[0])
    assert LOGO_LINES == len(LOGO) // 2


def test_logo_width_is_even():
    """An odd width gives the axis a column that would face both ways at once."""
    assert LOGO_WIDTH % 2 == 0


def test_logo_is_symmetric():
    """Mirroring swaps the two vertical planes and leaves the up-facing ones."""
    for row in LOGO:
        assert row == row[::-1].translate(MIRROR)


def test_logo_uses_declared_tones_only():
    """A tone with no palette entry would raise a `KeyError` mid-render."""
    used = {char for row in LOGO for char in row} - {BLANK}
    assert used <= set(TONES)


def test_logo_carries_structure():
    """The mark must shade in more than one tone.

    Its structure lives entirely in the shading, so a single-tone map would render
    as a featureless silhouette — the failure the color gate exists to avoid.
    """
    assert len({char for row in LOGO for char in row} - {BLANK}) > 1


def test_render_logo_halves_the_rows():
    """Two sub-pixel rows collapse into one terminal line."""
    assert len(render_logo()) == LOGO_LINES


def test_render_logo_lines_are_logo_wide():
    """Every line must be the same visible width, or the metadata column shears."""
    assert {len(strip_ansi(line)) for line in render_logo()} == {LOGO_WIDTH}


def test_render_logo_silhouette_is_symmetric():
    """Symmetry has to survive the render, not just hold in the source map.

    Only the silhouette is asserted, because *shading* is handed and should be: the
    two vertical planes catch different light, so mirroring the mark swaps them, and
    that difference is spent entirely on the colors.
    """
    for line in render_logo():
        inked = [char != BLANK for char in strip_ansi(line)]
        assert inked == inked[::-1]


def test_render_logo_mirrors_character_for_character():
    """Half-blocks say only how much of a cell is covered, which mirrors."""
    for line in render_logo():
        plain = strip_ansi(line)
        assert plain == plain[::-1]


def test_render_logo_leaves_transparent_runs_unstyled():
    """Transparent cells stay bare spaces, never wrapped in a no-op reset."""
    for line in render_logo():
        assert "\x1b[0m\x1b[0m" not in line


def test_version_screen_opens_on_a_blank_line():
    """Separates the mark from whatever noisier command preceded it."""
    screen = version_screen(PROG, VERSION)
    assert screen is not None
    assert screen.startswith("\n")
    assert not screen.startswith("\n\n")


def test_version_screen_aligns_the_metadata_column():
    """The metadata starts at the same column on every line that carries some."""
    start = LOGO_WIDTH + len(GUTTER)
    for line in screen_lines(PROG, VERSION):
        if len(line) > start:
            assert line[start - len(GUTTER) : start] == GUTTER
            assert not line[start].isspace()


def test_version_screen_reports_the_version():
    """The first metadata row is the plain-rendering version line, verbatim."""
    assert f"{PROG}, version {VERSION}" in "\n".join(screen_lines(PROG, VERSION))


def test_version_screen_is_as_tall_as_the_logo():
    assert len(screen_lines(PROG, VERSION)) == LOGO_LINES


def test_logo_is_tall_enough_for_its_metadata():
    """A mark shorter than the column beside it would leave the text overhanging."""
    assert LOGO_LINES >= len(screen_lines(PROG, VERSION))


def test_version_screen_has_no_trailing_whitespace():
    for line in screen_lines(PROG, VERSION):
        assert line == line.rstrip()


@pytest.mark.parametrize(
    ("columns", "renders"),
    (
        ("200", True),
        ("80", True),
        ("40", False),
        ("1", False),
    ),
)
def test_version_screen_needs_room(monkeypatch, columns, renders):
    """A terminal too narrow for the two columns declines instead of wrapping."""
    monkeypatch.setenv("COLUMNS", columns)
    monkeypatch.setenv("LINES", "40")
    assert (version_screen(PROG, VERSION) is not None) is renders


def test_version_screen_width_never_exceeds_the_terminal():
    """The threshold is measured, not guessed: no line may overflow the width."""
    width = shutil.get_terminal_size().columns
    for line in screen_lines(PROG, VERSION):
        assert len(line) <= width


def test_env_summary_shape():
    """The plain rendering's environment line, also split across two screen rows."""
    assert re.fullmatch(r"Python [^,]+, .+", env_summary())


def test_env_summary_facts_reach_the_screen():
    """Both halves of the plain summary are restated as their own metadata rows."""
    python_part, platform_part = env_summary().split(", ", 1)
    screen = "\n".join(screen_lines(PROG, VERSION))
    assert python_part.removeprefix("Python ") in screen
    assert platform_part in screen


def test_version_screen_survives_a_missing_terminal(monkeypatch):
    """No `COLUMNS` and no terminal still lands on `shutil`'s 80-column default.

    That is the shape of a redirected run with colors forced on, which must still
    get the screen it asked for.
    """

    def no_terminal(*args):
        raise OSError

    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.delenv("LINES", raising=False)
    monkeypatch.setattr(os, "get_terminal_size", no_terminal)
    assert version_screen(PROG, VERSION) is not None
