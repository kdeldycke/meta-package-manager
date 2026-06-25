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
"""Parsing of release-age durations for the :option:`mpm --cooldown` option.

Defines :py:class:`Duration`, the :py:class:`click_extra.ParamType` that turns a
friendly duration, an ISO 8601 duration, or an RFC 3339 timestamp into a
:py:class:`datetime.timedelta`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from click_extra import ParamType

TYPE_CHECKING = False
if TYPE_CHECKING:
    from click import Context as ClickContext
    from click_extra import Parameter


class Duration(ParamType):
    """Parse a cooldown spec into a :py:class:`datetime.timedelta`.

    Accepts three input shapes:

    - **Friendly duration**: ``7 days``, ``1 week``, ``12h``, ``30m``, ``45s``,
      or a bare number of days like ``7``.
    - **ISO 8601 duration**: ``P7D``, ``PT12H``, ``P1WT6H``. Case-insensitive.
    - **RFC 3339 absolute timestamp**: ``2024-05-01T00:00:00Z`` or with an
      offset like ``+02:00``. Converted at parse time to ``now - timestamp``;
      a timestamp in the future disables the cooldown.

    A zero duration or empty input parses to ``None``, which disables the cooldown
    (handy to override a value set in the configuration file).

    .. note::
       Durations resolve to a fixed number of seconds, assuming a day is 24
       hours. The local time zone, DST transitions, and calendar boundaries are
       ignored. Calendar units (months, years) are rejected for the same
       reason: 28-31 days and 365-366 days make them unsuitable for a precise
       release-age cutoff. Use ``days`` or ``weeks`` instead.
    """

    name = "duration"

    _UNIT_SECONDS: ClassVar[dict[str, int]] = {
        "": 86400,
        "s": 1,
        "sec": 1,
        "secs": 1,
        "second": 1,
        "seconds": 1,
        "m": 60,
        "min": 60,
        "mins": 60,
        "minute": 60,
        "minutes": 60,
        "h": 3600,
        "hr": 3600,
        "hrs": 3600,
        "hour": 3600,
        "hours": 3600,
        "d": 86400,
        "day": 86400,
        "days": 86400,
        "w": 604800,
        "week": 604800,
        "weeks": 604800,
    }
    """Number of seconds each recognized unit represents (empty unit means days)."""

    _CALENDAR_UNITS = frozenset({
        "mo",
        "mon",
        "month",
        "months",
        "y",
        "yr",
        "yrs",
        "year",
        "years",
    })
    """Calendar units rejected for ambiguity: months span 28-31 days, years 365-366."""

    _FRIENDLY_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-z]*)")
    _ISO8601_PATTERN = re.compile(
        r"P"
        r"(?:(?P<years>\d+(?:\.\d+)?)Y)?"
        r"(?:(?P<months>\d+(?:\.\d+)?)M)?"
        r"(?:(?P<weeks>\d+(?:\.\d+)?)W)?"
        r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
        r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
        r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
        r")?",
    )

    _EXAMPLES = (
        "'7 days', '1 week', '12h', '30m', 'P7D', 'PT12H', "
        "or an RFC 3339 timestamp like '2024-05-01T00:00:00Z'"
    )
    _CALENDAR_REJECT = (
        "calendar units (months, years) are rejected because their length is "
        "ambiguous: months span 28-31 days, years 365-366. Use days or weeks "
        "instead, like '30 days' or '4 weeks'."
    )

    def convert(
        self,
        value: object,
        param: Parameter | None,
        ctx: ClickContext | None,
    ) -> timedelta | None:
        """Coerce ``value`` to a :py:class:`datetime.timedelta` (or ``None``)."""
        if value is None or isinstance(value, timedelta):
            return value
        text = str(value).strip()
        if not text:
            return None
        # RFC 3339 absolute timestamp: starts with a 4-digit year and a dash.
        if len(text) >= 5 and text[:4].isdigit() and text[4] == "-":
            return self._parse_timestamp(text, value, param, ctx)
        # ISO 8601 duration: starts with 'P' (case-insensitive).
        if text[:1] in ("P", "p"):
            return self._parse_iso8601(text.upper(), value, param, ctx)
        # Friendly duration.
        return self._parse_friendly(text.lower(), value, param, ctx)

    def _parse_timestamp(
        self,
        text: str,
        value: object,
        param: Parameter | None,
        ctx: ClickContext | None,
    ) -> timedelta | None:
        normalized = text.upper().replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(normalized)
        except ValueError:
            self.fail(
                f"{value!r} looks like an RFC 3339 timestamp but cannot be "
                f"parsed. Accepted: {self._EXAMPLES}.",
                param,
                ctx,
            )
        if ts.tzinfo is None:
            self.fail(
                f"{value!r} is missing a time zone. Use a fully qualified "
                "RFC 3339 timestamp with 'Z' or an offset like '+00:00'.",
                param,
                ctx,
            )
        delta = datetime.now(tz=timezone.utc) - ts.astimezone(timezone.utc)
        return delta if delta.total_seconds() > 0 else None

    def _parse_iso8601(
        self,
        text: str,
        value: object,
        param: Parameter | None,
        ctx: ClickContext | None,
    ) -> timedelta | None:
        match = self._ISO8601_PATTERN.fullmatch(text)
        if not match or not any(match.groups()):
            self.fail(
                f"{value!r} is not a valid ISO 8601 duration "
                f"(examples: 'P7D', 'PT12H', 'P1WT6H'). Accepted: {self._EXAMPLES}.",
                param,
                ctx,
            )
        groups = match.groupdict()
        if groups["years"] or groups["months"]:
            self.fail(f"{value!r}: {self._CALENDAR_REJECT}", param, ctx)
        seconds = (
            float(groups["weeks"] or 0) * 604800
            + float(groups["days"] or 0) * 86400
            + float(groups["hours"] or 0) * 3600
            + float(groups["minutes"] or 0) * 60
            + float(groups["seconds"] or 0)
        )
        return timedelta(seconds=seconds) if seconds else None

    def _parse_friendly(
        self,
        text: str,
        value: object,
        param: Parameter | None,
        ctx: ClickContext | None,
    ) -> timedelta | None:
        match = self._FRIENDLY_PATTERN.fullmatch(text)
        if match:
            unit = match["unit"]
            if unit in self._CALENDAR_UNITS:
                self.fail(f"{value!r}: {self._CALENDAR_REJECT}", param, ctx)
            if unit in self._UNIT_SECONDS:
                seconds = float(match["value"]) * self._UNIT_SECONDS[unit]
                return timedelta(seconds=seconds) if seconds else None
        self.fail(
            f"{value!r} is not a valid duration (examples: {self._EXAMPLES}).",
            param,
            ctx,
        )
