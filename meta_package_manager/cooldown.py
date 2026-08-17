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

"""Vocabulary and resolution of the release-age cooldown gate.

The cooldown is a supply-chain safeguard with two independent axes:

- the **window**: the minimum age a package version must reach before it can
  be installed or upgraded, expressed as a duration;
- the **policy**: what happens to managers that cannot natively enforce an
  active window ({class}`~meta_package_manager.cooldown.CooldownPolicy`).

The CLI spells both axes on the single `--cooldown` option (a duration, or
one of the policy keywords), while the configuration file spells them as the
two keys of the `[mpm.cooldown]` table (`period` and `policy`). Resolution
({func}`resolve_cooldown`) merges the two sources axis by axis: a value set
on one side only leaves the other axis to the configuration, so `--cooldown
best-effort` reuses the configured window, and `--cooldown 7d` reuses the
configured policy.

The gate itself (per-manager environment injection, the fail-closed skips)
lives in {mod}`meta_package_manager.execution` and
{func}`meta_package_manager.cli_maintenance.cooldown_permits`; this module
only owns the input grammar and the merge rules.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import click
from click_extra import Duration

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]


POLICY_CONFIG_KEYS = ("period", "policy")
"""Recognized keys of the `[mpm.cooldown]` configuration table.

`period` carries the window as a duration string, `policy` one of the
{class}`CooldownPolicy` keywords accepted in configuration files. Kept here
as the single enumeration both the parser and the error messages read."""


class CooldownPolicy(StrEnum):
    """Enforcement posture of an active release-age cooldown window.

    Only applies to managers without native release-age support; managers
    that can enforce the window natively always do, whatever the policy.
    The values double as the CLI keywords of the `--cooldown` option and
    (except {attr}`off`) as the `policy` values of the `[mpm.cooldown]`
    configuration table, so they spell exactly like the user types them.
    """

    enforce = "enforce"
    """Skip the managers that cannot enforce the window (fail-closed). The
    default posture: nothing slips in unguarded."""

    best_effort = "best-effort"
    """Run the managers that cannot enforce the window anyway, without the
    supply-chain safeguard."""

    off = "off"
    """Disable the gate entirely for this run, on every manager. A CLI-only
    keyword, equivalent to a `0` duration: the configuration expresses the
    same state with `period = "0"` (or no `period` at all)."""


class Cooldown(click.ParamType):
    """Parse the `--cooldown` value: a window duration or a policy keyword.

    Returns a {class}`datetime.timedelta` for a duration, a
    {class}`CooldownPolicy` for a keyword (`0` collapses to
    {attr}`CooldownPolicy.off`, matching the "zero disables the gate" rule
    of click-extra's {class}`~click_extra.Duration`), and `None` for an
    empty value, which reads as "unspecified": resolution then inherits
    both axes from the configuration.
    """

    name = "cooldown"

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> timedelta | CooldownPolicy | None:
        """Coerce `value` to a window, a policy, or `None` (unspecified).

        Already-parsed values flow through untouched so defaults and
        re-processing stay idempotent.
        """
        if value is None or isinstance(value, (timedelta, CooldownPolicy)):
            return value
        if not isinstance(value, str):
            self.fail(f"unexpected {type(value).__name__} value {value!r}", param, ctx)
        token = value.strip()
        if not token:
            return None
        for policy in CooldownPolicy:
            if token.casefold() == policy.value.casefold():
                return policy
        # Delegate the duration grammar (friendly, ISO 8601, RFC 3339) to
        # click-extra, which raises the canonical "not a valid duration"
        # error on anything else.
        duration = Duration().convert(token, param, ctx)
        # A zero duration and a future timestamp both collapse to "no
        # cutoff": spell that state as the off posture.
        return duration if duration is not None else CooldownPolicy.off


@dataclass(frozen=True)
class CooldownSettings:
    """The cooldown axes carried by the configuration, before merging.

    An axis left unset is `None`: resolution substitutes the default only
    after the CLI flag had a chance to override the other axis.
    """

    duration: timedelta | None
    """The configured window (`period` key), or `None` when unset or zero."""

    policy: CooldownPolicy | None
    """The configured posture (`policy` key), or `None` when unset."""

    legacy: bool = False
    """Whether the section used the deprecated `[mpm] cooldown = "<duration>"`
    top-level string spelling, accepted as the window for one migration
    window."""


def parse_policy_token(token: Any) -> CooldownPolicy | None:
    """Map `token` to a {class}`CooldownPolicy`, case-insensitively.

    Returns `None` when the token names no policy, so callers decide how to
    report the miss.
    """
    text = str(token).strip().casefold()
    for policy in CooldownPolicy:
        if text == policy.value.casefold():
            return policy
    return None


def _parse_period(raw: Any) -> timedelta | None:
    """Parse the `period` configuration value into a window.

    Accepts the same duration grammar as the `--cooldown` flag; a zero
    duration reads as "no window". Raises `ValueError` on anything the
    grammar rejects, with click-extra's own diagnostic in the message.
    """
    text = str(raw).strip()
    if not text:
        return None
    try:
        return Duration().convert(text, None, None)
    except click.BadParameter as exc:
        raise ValueError(str(exc)) from exc


def parse_cooldown_section(section: Any) -> CooldownSettings:
    """Parse the `[mpm.cooldown]` configuration section into settings.

    Accepts the table shape (`period` and `policy` keys) and, as a
    migration aid, the deprecated top-level string spelling, read as the
    window. Pure parsing: no logging, so the load-time validator and the
    runtime resolution can share it without duplicated diagnostics.

    :raises ValueError: on an unknown key, an unparsable `period`,
        a `policy` that is not `enforce` or `best-effort` (`off` is a
        CLI-only keyword), or a `policy` without a `period`, which would be
        a standing no-op gate.
    :raises TypeError: when the section is neither a table nor a string.
    """
    if section is None:
        return CooldownSettings(duration=None, policy=None)
    if isinstance(section, str):
        return CooldownSettings(
            duration=_parse_period(section), policy=None, legacy=True
        )
    if not isinstance(section, dict):
        raise TypeError(
            f"expected a table or a duration string, got {type(section).__name__}"
        )
    unknown = sorted(set(section) - set(POLICY_CONFIG_KEYS))
    if unknown:
        raise ValueError(
            f"unknown key(s) {', '.join(unknown)}; "
            f"accepted: {', '.join(POLICY_CONFIG_KEYS)}"
        )
    duration = _parse_period(section.get("period", ""))
    policy: CooldownPolicy | None = None
    raw_policy = section.get("policy")
    if raw_policy is not None and str(raw_policy).strip():
        policy = parse_policy_token(raw_policy)
        if policy is None:
            raise ValueError(
                f"unknown policy {raw_policy!r}; accepted: "
                f"{CooldownPolicy.enforce}, {CooldownPolicy.best_effort}"
            )
        if policy is CooldownPolicy.off:
            raise ValueError(
                "the off policy is a CLI-only keyword; drop the period "
                'key (or set it to "0") to disable the gate in configuration'
            )
        if duration is None:
            raise ValueError(
                f"policy {policy} requires a period: a posture without a "
                "window is a no-op gate"
            )
    return CooldownSettings(duration=duration, policy=policy)


def resolve_cooldown(
    flag: timedelta | CooldownPolicy | None,
    settings: CooldownSettings,
) -> tuple[timedelta | None, CooldownPolicy]:
    """Merge the parsed `--cooldown` flag with the configuration settings.

    Axis-by-axis precedence: a flag duration overrides the configured window
    but inherits the configured policy; a flag policy overrides the
    configured policy but inherits the configured window ({attr}`off`
    forces the window off too); an unset flag inherits both axes. Returns
    the effective `(window, policy)` pair, the policy defaulted to
    {attr}`CooldownPolicy.enforce` when neither side sets it.
    """
    configured_policy = settings.policy or CooldownPolicy.enforce
    if flag is None or isinstance(flag, timedelta):
        window = settings.duration if flag is None else flag
        return window, configured_policy
    if flag is CooldownPolicy.off:
        return None, CooldownPolicy.off
    return settings.duration, flag
