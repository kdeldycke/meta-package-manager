# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

""" Utilities to manage and resolve constraints from a set of package specifiers.

..todo:: Could be made into a class and specific objects for cleaner code.
"""

from __future__ import annotations

import sys
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

if sys.version_info < (3, 8):
    from typing_extensions import Final
else:
    from typing import Final

if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    from boltons.cacheutils import cachedproperty as cached_property

from packageurl import PackageURL

from . import logger
from .pool import pool
from .version import parse_version

VERSION_SEP: Final = "@"
"""Separator used by ``mpm`` to split package's ID from its version:

This separator is popular convention among package managers and purl.

..code-block::

    package_id@version
"""


# 1:1 mapping between purl and mpm manager IDs.
PURL_MAP = {mid: {mid} for mid in pool.all_manager_ids}
# Manager IDs collected by looking at packageurl-python source code.
PURL_MAP.update(
    {
        "alpine": None,
        "bitbucket": None,
        "deb": {"apt", "apt-mint"},
        "docker": None,
        "generic": None,
        "github": None,
        "gitlab": None,
        "golang": None,
        "hackage": None,
        "maven": None,
        "nuget": None,
        "pypi": {"pip", "pipx"},
        "rpm": {"dnf", "yum", "zypper"},
        "rubygems": {"gem"},
        "sourceforge": None,
    }
)


class SkipPackage(Exception):
    pass


def reduce_contraints(
    specs_metadata: Iterable[Mapping[str, str]],
    manager_priority: Sequence[str] | None,
) -> dict[str, str] | None:
    """Reduce a complex set of constraints to their essential, minimal form.

    The reduction process consist in several steps. At each step, the remaining set is return if
    only one remains.

    1. Empty constraints are returned right away as ``None`` for nomalization.
    2. We remove all contraints tied to all by the top priority manager if provided.
    3. If no manager priority is provided, we discard constraints not tied to a manager.
    4. We discard constraints not tied to a version.
    5. We only keep constraints tied to the highest version.

    If we ends up with more than one set of constraints after all this filtering, an error is raised
    to invite the developer to troubleshoot the situation and refine this process.
    """
    # Build the set of metadata we will use as constraints.
    subset = []
    for metadata in specs_metadata:
        c = {}
        for k in {"manager_id", "version_str"}:
            v = metadata.get(k)
            if v:
                c[k] = v
        if c:
            subset.append(c)

    # Normalize un-constrained spec to None.
    if not subset:
        return None

    if len(subset) == 1:
        return subset.pop()

    # If constraints allows for multiple managers, only keep those matching the highest priority.
    target_manager_ids = {c.get("manager_id") for c in subset}
    if len(target_manager_ids) > 1:

        if manager_priority:
            if target_manager_ids.isdisjoint(manager_priority):
                logger.warning(
                    f"Requested target managers {target_manager_ids} don't match available {manager_priority}."
                )
                raise SkipPackage
            top_priority_manager = None
            for manager_id in manager_priority:
                if manager_id in target_manager_ids:
                    top_priority_manager = manager_id
                    break
            subset = [c for c in subset if c.get("manager_id") == top_priority_manager]

        # If no manager priority has been set, then only filters out specs not not tied to any manager.
        else:
            subset = [c for c in subset if c.get("manager_id")]

    if len(subset) == 1:
        return subset.pop()

    # Only keep the set with the higher version.
    for c in subset:
        # Parse all versions and store them in the subset.
        c.update({"version_obj": parse_version(c.get("version_str"))})
    max_version = max(c["version_obj"] for c in subset)
    subset2 = []
    for c in subset:
        if c["version_obj"] == max_version:
            c.pop("version_obj")
            subset2.append(c)
    subset = subset2

    if len(subset) == 1:
        return subset.pop()

    # Still too much constraints.
    raise ValueError(
        f"Cannot reduce {subset} any further. More heuristics must be implemented."
    )


def parse_specs(spec_strings: Iterable[str]) -> Iterator[dict[str, str]]:
    """Parse a mix of package specifiers.

    Supports various formats:
    - simple ``package_id``
    - simple package ID with version: ``package_id@version``
    - purl: ``pkg:npm/left-pad@3.7``

    If a specifier resolves to multiple constraints (as it might be the case for purl), we produce and returns all
    variations. Resolution of these specs is left for ``reduce_contraints()``.

    Returns a generator of dictionnaries containing parsed metadata to be used as constraints.
    """
    # Deduplicate entries.
    for spec in set(spec_strings):

        # Try to parse specifier as a purl.
        purl = None
        try:
            purl = PackageURL.from_string(spec)
        except ValueError as ex:
            logger.debug(f"{spec} is not a purl: {ex}")

        # Specifier is a purl, extract its metadata.
        if purl:
            manager_ids = PURL_MAP.get(purl.type)
            if not manager_ids:
                raise ValueError(f"Unrecognized {purl.type} purl type.")

            # The purl can be handled by one manager or more.
            for manager_id in manager_ids:
                constraint = {
                    "spec": spec,
                    "package_id": purl.name,
                    "manager_id": manager_id,
                }
                if purl.version:
                    constraint["version_str"] = purl.version
                yield constraint
            continue

        # Specifier contains a version.
        if VERSION_SEP in spec:
            package_id, version = spec.split(VERSION_SEP, 1)
            yield {
                "spec": spec,
                "package_id": package_id,
                "version_str": version,
            }
        # The spec is the package ID.
        else:
            yield {
                "spec": spec,
                "package_id": spec,
            }


def resolve_specs(
    spec_strings: Iterable[str], manager_priority: Sequence[str] | None
) -> Iterator[dict[str, str | None]]:
    """Parse package specifiers, regroup them by package IDs, collect their constraints and reduce them to their simplest expression."""
    spec_metadata = parse_specs(spec_strings)

    # Regroup specs by package IDs. Has the nice side effect of deduplucating entries.
    keyfunc = itemgetter("package_id")
    for package_id, metadata in groupby(
        sorted(spec_metadata, key=keyfunc), key=keyfunc
    ):
        metadata = tuple(metadata)

        # Reduce and cleanup each set of constraints.
        try:
            reduced = reduce_contraints(metadata, manager_priority)
        except SkipPackage:
            logger.warning(f"Skip package {package_id}.")
            continue

        # Print a warning if the specifiers of a package went trough a reduction step.
        package_specs = sorted(map(itemgetter("spec"), metadata))
        if len(package_specs) > 1:
            logger.warning(
                f"Specifiers for {package_id} have been collapsed from {package_specs} to {reduced}"
            )

        specs = {
            "package_id": package_id,
            "manager_id": None,
            "version_str": None,
        }
        if reduced:
            specs.update(reduced)
        yield specs
