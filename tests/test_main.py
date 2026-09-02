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

import pytest

from meta_package_manager.__main__ import force_unicode_output

# The glyphs mpm prints that a legacy code page cannot encode: the two status
# marks of the `managers` table, and one border character of every rounded table.
UNENCODABLE_ON_CP1252 = ("✓", "✘", "╭", "─")


class FakeStream:
    """A stand-in for a standard stream, recording what it was reconfigured to.

    Driving the real `sys.stdout` is what the guard cannot do: every workflow
    exports `PYTHONIOENCODING=utf8`, so the streams a CI run hands the suite are
    already UTF-8 and the legacy path is never taken.
    """

    def __init__(self, encoding: str | None, *, refuse: bool = False) -> None:
        self.encoding = encoding
        self.refuse = refuse
        self.reconfigured: dict[str, str] = {}

    def reconfigure(self, **kwargs: str) -> None:
        if self.refuse:
            raise ValueError("stream refuses reconfiguration")
        self.reconfigured.update(kwargs)
        if "encoding" in kwargs:
            self.encoding = kwargs["encoding"]


@pytest.mark.parametrize("encoding", ("cp1252", "ascii", "latin-1", None))
def test_legacy_stream_is_promoted_to_utf8(monkeypatch, encoding):
    """A stream that cannot carry mpm's glyphs is reconfigured to UTF-8."""
    out, err = FakeStream(encoding), FakeStream(encoding)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)

    force_unicode_output()

    for stream in (out, err):
        assert stream.reconfigured == {"encoding": "UTF-8"}
        assert stream.encoding is not None
        for glyph in UNENCODABLE_ON_CP1252:
            glyph.encode(stream.encoding)


@pytest.mark.parametrize("encoding", ("utf-8", "UTF-8", "utf8"))
def test_utf8_stream_is_left_alone(monkeypatch, encoding):
    """Reconfiguration never fires on a stream that already speaks UTF-8,
    whatever spelling it reports."""
    out, err = FakeStream(encoding), FakeStream(encoding)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)

    force_unicode_output()

    assert out.reconfigured == {}
    assert err.reconfigured == {}


def test_a_refusing_stream_never_raises(monkeypatch):
    """A stream refusing reconfiguration is left as the platform made it, rather
    than taking the whole CLI down before it has printed anything."""
    out = FakeStream("cp1252", refuse=True)
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", FakeStream("utf-8"))

    force_unicode_output()

    assert out.encoding == "cp1252"


def test_a_stream_without_reconfigure_is_skipped(monkeypatch):
    """Not every object standing in for a stream carries `reconfigure`: a
    captured `io.StringIO` does not, and must not crash the entry point."""
    import io

    monkeypatch.setattr("sys.stdout", io.StringIO())
    monkeypatch.setattr("sys.stderr", io.StringIO())

    force_unicode_output()
