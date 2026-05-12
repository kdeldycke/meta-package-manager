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

"""Configuration utilities for ``mpm``.

Hosts the schema of the ``[mpm]`` configuration section consumed by
:py:mod:`click_extra` and the per-manager attribute override mechanism driven by
``[mpm.managers.<id>]`` sections of the same configuration file.

The override mechanism keeps the pool and the configuration concerns separate:
:py:class:`meta_package_manager.pool.ManagerPool` owns the live manager instances
and the per-manager ``overridden_fields`` tracking dict, while this module owns the
schema (which fields are overridable, how to coerce values) and the application
logic. The pool is mutated through the :py:func:`apply_manager_overrides` helper,
keeping all configuration policy out of :py:mod:`meta_package_manager.pool`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Any, Final

    import click

    from .pool import ManagerPool


@dataclass
class MpmConfig:
    """Schema for ``mpm`` configuration files.

    Defines the recognized options for the ``[mpm]`` (or ``[tool.mpm]``)
    configuration section.  Each field corresponds to a CLI option on the root
    ``mpm`` group.

    .. note::
        Dynamic manager selectors (``brew = true``, ``pip = false``, etc.) and
        click-extra built-in options (``verbosity``, ``table_format``) are handled
        by the ``default_map`` pipeline and do not appear here.
    """

    all_managers: bool = False
    """Force evaluation of all managers, including unsupported and deprecated."""

    ignore_auto_updates: bool = True
    """Exclude auto-updating packages from outdated/upgrade results."""

    stop_on_error: bool = False
    """Stop on first manager CLI error instead of continuing."""

    dry_run: bool = False
    """Simulate CLI calls without performing any action."""

    timeout: int = 500
    """Maximum duration in seconds for each manager CLI call."""

    description: bool = False
    """Show package description in results."""

    sort_by: str = "manager_id"
    """Default field to sort results by."""

    stats: bool = True
    """Print per-manager package statistics."""


def _to_str(value: Any) -> str:
    """Validate that the value is a string."""
    if not isinstance(value, str):
        raise ValueError(f"expected a string, got {type(value).__name__}: {value!r}")
    return value


def _to_bool(value: Any) -> bool:
    """Validate that the value is a boolean."""
    if not isinstance(value, bool):
        raise ValueError(f"expected a boolean, got {type(value).__name__}: {value!r}")
    return value


def _to_int(value: Any) -> int:
    """Validate that the value is an integer.

    Rejects ``bool`` because :py:class:`bool` is a subclass of :py:class:`int`
    in Python, but configuration intent is unambiguous: a boolean is never an
    acceptable integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected an integer, got {type(value).__name__}: {value!r}")
    return value


def _to_str_tuple(value: Any) -> tuple[str, ...]:
    """Validate that the value is a list/tuple of strings, return a tuple."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"expected a list of strings, got {type(value).__name__}: {value!r}"
        )
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"expected all entries to be strings, "
                f"got {type(item).__name__}: {item!r}"
            )
    return tuple(value)


def _to_str_dict(value: Any) -> dict[str, str]:
    """Validate that the value is a mapping of strings to strings."""
    if not isinstance(value, dict):
        raise ValueError(
            f"expected a table of string-to-string, "
            f"got {type(value).__name__}: {value!r}"
        )
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(
                f"expected a table of string-to-string entries, "
                f"got {k!r} = {v!r}"
            )
    return dict(value)


OVERRIDABLE_FIELDS: Final[Mapping[str, Callable[[Any], Any]]] = {
    "cli_names": _to_str_tuple,
    "cli_search_path": _to_str_tuple,
    "deprecated": _to_bool,
    "dry_run": _to_bool,
    "extra_env": _to_str_dict,
    "ignore_auto_updates": _to_bool,
    "post_args": _to_str_tuple,
    "pre_args": _to_str_tuple,
    "pre_cmds": _to_str_tuple,
    "requirement": _to_str,
    "stop_on_error": _to_bool,
    "timeout": _to_int,
    "version_cli_options": _to_str_tuple,
    "version_regexes": _to_str_tuple,
}
"""Per-manager attributes a user is allowed to override from the ``[mpm.managers.<id>]``
configuration section.

Each entry maps a :py:class:`meta_package_manager.base.PackageManager` attribute name
to a converter that validates the raw TOML value and returns the value as the
attribute's expected runtime type. Lists are coerced into tuples to match the
attributes' tuple types.

.. note::
    ``id``, ``name``, ``platforms``, ``homepage_url`` and ``virtual`` are
    intentionally excluded: they are identity, lookup or platform-classification
    attributes that the pool's registration relies on. Phase 1 of TOML-driven
    configuration only exposes attributes whose runtime override is safe.
"""


INVALIDATED_CACHED_PROPS: Final[tuple[str, ...]] = (
    "available",
    "cli_path",
    "executable",
    "fresh",
    "supported",
    "version",
)
"""Cached properties on :py:class:`meta_package_manager.base.PackageManager` that may
have been computed from attributes covered by :data:`OVERRIDABLE_FIELDS`.

Any pre-computed values are popped from the manager instance's ``__dict__`` after an
override is applied so the next access recomputes them against the new attribute
values. Safe to pop even if nothing was cached.
"""


def apply_manager_overrides(
    pool: ManagerPool,
    overrides: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    """Apply per-manager attribute overrides parsed from the user's config file.

    Expects ``overrides`` to be a mapping of manager ID to a mapping of attribute
    name to its new value, as returned by ``conf["mpm"]["managers"]``. ``None`` and
    empty mappings are accepted as no-op shortcuts so callers can unconditionally
    forward whatever was parsed from the config file.

    For each ``(manager_id, field, value)`` triple:

    - Unknown manager IDs and unknown field names are logged at warning level and
      skipped: a typo in the config file should not crash the CLI.
    - Recognized values are validated and coerced through
      :data:`OVERRIDABLE_FIELDS` converters. A type mismatch raises
      :py:class:`ValueError` so the user is told to fix the config.
    - Each accepted override is applied as an instance attribute, shadowing the
      class default for the lifetime of the process. List-valued fields use
      *replace* semantics: the override fully supersedes the built-in default.
    - Each accepted override is also recorded in ``pool.overridden_fields`` so
      :py:meth:`meta_package_manager.pool.ManagerPool._select_managers` knows to
      skip the matching global ``--<flag>`` defaults for this manager.
    - After every accepted override, cached properties derived from the affected
      attributes (``cli_path``, ``version``, ``available``, etc.) are evicted from
      the instance ``__dict__`` so the next access recomputes them.
    """
    if not overrides:
        return

    if not isinstance(overrides, dict):
        logging.warning(
            f"Ignoring [mpm.managers] section: expected a table, "
            f"got {type(overrides).__name__}.",
        )
        return

    for manager_id, fields in overrides.items():
        if manager_id not in pool.register:
            logging.warning(
                f"Ignoring [mpm.managers.{manager_id}]: "
                f"unknown manager ID {manager_id!r}.",
            )
            continue
        if not isinstance(fields, dict):
            logging.warning(
                f"Ignoring [mpm.managers.{manager_id}]: "
                f"expected a table, got {type(fields).__name__}.",
            )
            continue

        manager = pool.register[manager_id]
        for field, raw_value in fields.items():
            converter = OVERRIDABLE_FIELDS.get(field)
            if converter is None:
                logging.warning(
                    f"Ignoring [mpm.managers.{manager_id}].{field}: "
                    f"unknown field. "
                    f"Allowed: {', '.join(sorted(OVERRIDABLE_FIELDS))}.",
                )
                continue
            try:
                value = converter(raw_value)
            except ValueError as ex:
                msg = f"[mpm.managers.{manager_id}].{field}: {ex}"
                raise ValueError(msg) from ex

            setattr(manager, field, value)
            pool.overridden_fields.setdefault(manager_id, set()).add(field)
            logging.debug(
                f"Applied override [mpm.managers.{manager_id}].{field} = {value!r}",
            )

        for prop in INVALIDATED_CACHED_PROPS:
            manager.__dict__.pop(prop, None)


def apply_manager_overrides_from_context(
    ctx: click.Context,
    pool: ManagerPool,
) -> None:
    """Read the ``[mpm.managers.<id>]`` sections from the loaded config and apply
    them to ``pool``.

    Reads ``ctx.meta["click_extra.conf_full"]`` (the full parsed config exposed by
    :py:mod:`click_extra` after configuration discovery) and forwards the
    ``["mpm"]["managers"]`` subtree to :py:func:`apply_manager_overrides`. Returns
    silently when no configuration file was loaded or when the section is absent.
    """
    conf_full = ctx.meta.get("click_extra.conf_full") or {}
    mpm_section = conf_full.get("mpm") if isinstance(conf_full, dict) else None
    overrides = mpm_section.get("managers") if isinstance(mpm_section, dict) else None
    apply_manager_overrides(pool, overrides)
