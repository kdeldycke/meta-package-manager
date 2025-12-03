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
"""Utilities to manage and resolve constraints from a set of package specifiers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property
from itertools import groupby
from operator import attrgetter

from packageurl import PackageURL

from .pool import pool
from .version import is_version, parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from typing import Final

    from .version import TokenizedString


VERSION_SEP: Final = "@"
"""Separator used by ``mpm`` to split package's ID from its version:

This has been chosen as a separator because it is shared by popular package managers
(like ``npm``) and pURLs.

..code-block::

    package_id@version
"""

PURL_MAP: dict[str, set[str] | None] = {
    "alpine": None,
    "alpm": {"pacman", "pacaur", "paru", "yay"},
    "android": None,
    "apache": None,
    "apk": None,
    "bitbucket": None,
    "bitnami": None,
    "bower": None,
    "buildroot": None,
    "cargo": {"cargo"},
    "carthage": None,
    "chef": None,
    "chocolatey": {"choco"},
    "clojars": None,
    "cocoapods": None,
    "composer": {"composer"},
    "conan": None,
    "conda": None,
    "coreos": None,
    "cpan": None,
    "cran": None,
    "crystal": None,
    "ctan": None,
    "deb": {"apt", "apt-mint"},
    "docker": None,
    "drupal": None,
    "dtype": None,
    "dub": None,
    "ebuild": {"emerge"},
    "eclipse": None,
    "elm": None,
    "gem": {"gem"},
    "generic": None,
    "gitea": None,
    "github": None,
    "gitlab": None,
    "golang": None,
    "gradle": None,
    "guix": None,
    "hackage": None,
    "haxe": None,
    "helm": None,
    "hex": None,
    "huggingface": None,
    "julia": None,
    "luarocks": None,
    "maven": None,
    "melpa": None,
    "meteor": None,
    "mlflow": None,
    "nim": None,
    "nix": None,
    "npm": {"npm", "yarn"},
    "nuget": None,
    "oci": None,
    "opam": None,
    "openwrt": {"opkg"},
    "osgi": None,
    "p2": None,
    "pear": None,
    "pecl": None,
    "perl6": None,
    "platformio": None,
    "pub": None,
    "puppet": None,
    "pypi": {"pip", "pipx", "uv"},
    "qpkg": None,
    "rpm": {"dnf", "dnf5", "yum", "zypper"},
    "rubygems": {"gem"},
    "sourceforge": None,
    "sublime": None,
    "swid": None,
    "terraform": None,
    "vagrant": None,
    "vim": None,
    "wordpress": None,
    "yocto": None,
}
"""Map pURL's types to MPM's manager IDs.

Keys are recognized pURL's types, and values are the set of MPM's manager IDs that can
handle the package type.

.. warning::

    There is no official list of ``pkg:<type>/...`` prefixes defined in the pURL
    specification.

    The only source we found lying around in the pURL literature is this `list of
    diverse aliases, examples and libraries
    <https://github.com/package-url/purl-spec/blob/master/PURL-TYPES.rst>`_. We use
    this document to compile the keys of this ``PURL_MAP`` mapping.

.. todo::

    Reuse the mapping that is proposed upstream to the `package-url Python
    project <https://github.com/package-url/packageurl-python/pull/188>`_.
"""


@dataclass(frozen=True)
class Specifier:
    """Lightweight representation of a package specification.

    Contains all parsed metadata to be used as constraints.
    """

    raw_spec: str
    """Original, un-parsed specifier string provided by the user."""

    package_id: str
    """ID is required and is the primary key used for specification."""

    manager_id: str | None = None

    version: str | None = None
    """Version string, a 1:1 copy of the one provided by the user."""

    @classmethod
    def parse_purl(cls, spec_str: str) -> tuple[Specifier, ...] | None:
        """Resolve a pURL into its corresponding manager candidates.

        Yields ``Specifier`` objects or returns ``None``.
        """
        # Try to parse specifier as a pURL.
        try:
            purl = PackageURL.from_string(spec_str)
        except ValueError as ex:
            logging.debug(f"{spec_str} is not a pURL: {ex}")
            return None

        manager_ids: set[str] | None = None
        # If the pURL type is recognized, it is used to find the corresponding manager.
        if purl.type in PURL_MAP:
            manager_ids = PURL_MAP.get(purl.type)
        # If the pURL type matches a manager, we use it as-is.
        elif purl.type in pool.all_manager_ids:
            manager_ids = {purl.type}
        if not manager_ids:
            msg = f"Unrecognized {purl.type} pURL type."
            raise ValueError(msg)

        # The pURL can be handled by one manager or more.
        return tuple(
            Specifier(
                raw_spec=spec_str,
                package_id=purl.name,
                manager_id=manager_id,
                version=purl.version,
            )
            for manager_id in manager_ids
        )

    @classmethod
    def from_string(cls, spec_str: str) -> tuple[Specifier, ...]:
        """Parse a string into a package specifier.

        Supports various formats:
        - plain ``package_id``
        - simple package ID with version: ``package_id@version``
        - package with multiple version separators: ``@eslint/json@0.9.0``
        - pURL: ``pkg:npm/left-pad@3.7``

        If a specifier resolves to multiple constraints (as it might be the case for
        pURL), we produce and returns all variations. That way the ``Solver`` below has
        all necessary details to resolve the constraints.

        Returns a tuple of ``Specifier``.
        """
        specs = cls.parse_purl(spec_str)
        if specs:
            return specs

        # Specifier contains a version separator.
        if VERSION_SEP in spec_str:
            # Extract the string after the last version separator and check it really
            # is a version string. This accounts for special cases like
            # @eslint/json@0.9.0.
            parts = spec_str.split(VERSION_SEP)
            package_id = VERSION_SEP.join(parts[:-1])
            version = parts[-1]
            if package_id and is_version(version):
                return (
                    cls(
                        raw_spec=spec_str,
                        package_id=package_id,
                        version=version,
                    ),
                )

        # The spec is the plain package ID.
        return (
            cls(
                raw_spec=spec_str,
                package_id=spec_str,
            ),
        )

    @cached_property
    def parsed_version(self) -> TokenizedString:
        return parse_version(self.version)  # type:ignore[arg-type]

    @cached_property
    def is_blank(self) -> bool:
        """Is considered blank a ``Specifier`` without any constraint on ``manager_id``
        or ``version``."""
        return not bool(self.manager_id or self.version)

    def __str__(self) -> str:
        """Human readable string of the spec.

        Dynamiccaly adds version, its separator and manage ID prefix (in pURL syntax).
        """
        string = self.package_id
        if self.version:
            string = f"{string}{VERSION_SEP}{self.version}"
        if self.manager_id:
            string = f"pkg:{self.manager_id}/{string}"
        return string


class EmptyReduction(Exception):
    """Raised by the solver if no constraint can't be met."""


class Solver:
    """Combine a set of ``Specifier`` and allow for the solving of the constraints they
    represent."""

    manager_priority: Sequence[str] = []

    spec_pool: set[Specifier] = set()

    def __init__(
        self,
        spec_strings: Iterable[str] | None = None,
        manager_priority=None,
    ) -> None:
        if spec_strings:
            self.populate_from_strings(spec_strings)
        if manager_priority:
            self.manager_priority = manager_priority

    def populate_from_strings(self, spec_strings: Iterable[str]):
        """Populate the solver with package specifiers parsed from provided strings."""
        # Deduplicate entries.
        for spec_str in set(spec_strings):
            new_specs = Specifier.from_string(spec_str)
            self.spec_pool = self.spec_pool.union(new_specs)

    def top_priority_manager(
        self,
        keep_managers: Iterable[str | None] | None = None,
    ) -> str | None:
        """Returns the top priority manager configured on the solver.

        ``keep_managers`` allows for filtering by discarding managers not in that list.
        """
        for manager_id in self.manager_priority:
            # Returns the first manager in the priority list if no filtering needs to
            # be performed.
            if not keep_managers:
                return manager_id
            # Returns the first matching manager in the priority list.
            elif manager_id in keep_managers:
                return manager_id
        # No single top-priority manager can selected.
        return None

    def reduce_specs(self, specs: Iterable[Specifier]) -> Specifier:
        """Reduce a collection of ``Specifier`` to its essential, minimal and unique
        form.

        This method assumes that all provided ``specs`` are of the same package (like
        ``resolve_package_specs()`` does).

        The reduction process consist of several steps. At each step, as soon as we
        managed to reduce the constraints to one ``Specifier``, we returns it.

        Filtering steps:
        1. We remove all constraints tied to all by the top priority manager if
            provided.
        2. If no manager priority is provided, we discard constraints not tied to a
            manager.
        3. We discard constraints not tied to a version.
        4. We only keep constraints tied to the highest version.

        If we ends up with more than one set of constraints after all this filtering, an
        error is raised to invite the developer to troubleshoot the situation and refine
        this process.
        """
        # Deduplicate specifiers.
        collection = set(specs)

        if len(collection) == 1:
            return collection.pop()

        # If constraints allows for multiple managers, only keep specs matching
        # the highest priority.
        target_manager_ids = {s.manager_id for s in collection}
        if len(target_manager_ids) > 1:
            if self.manager_priority:
                if target_manager_ids.isdisjoint(self.manager_priority):
                    logging.warning(
                        f"Requested target managers {target_manager_ids} "
                        f"don't match selected {self.manager_priority}.",
                    )
                    raise EmptyReduction
                top_priority_manager = self.top_priority_manager(target_manager_ids)
                collection = {
                    s for s in collection if s.manager_id == top_priority_manager
                }

            # If no manager priority has been set, discards specs not tied to any
            # manager.
            else:
                collection = {s for s in collection if s.manager_id}

        if len(collection) == 1:
            return collection.pop()

        # Only keep the subset with the higher version.
        max_version = max(s.parsed_version for s in collection)
        collection = {s for s in collection if s.parsed_version == max_version}

        if len(collection) == 1:
            return collection.pop()

        # Still too much constraints.
        msg = (
            f"Cannot reduce {collection} any further. More heuristics must be "
            "implemented."
        )
        raise ValueError(msg)

    def resolve_package_specs(self) -> Iterator[tuple[str, Specifier]]:
        """Regroup specs of the pool by package IDs, and solve their constraints.

        Return each package ID with its single, reduced spec, or ``None`` if it ha no
        constraints.
        """
        # Regroup specs by package IDs. Has the nice side effect of deduplicating specs.
        keyfunc = attrgetter("package_id")
        for package_id, package_specs in groupby(
            sorted(self.spec_pool, key=keyfunc),
            key=keyfunc,
        ):
            # Serialize because of reuse in log message below.
            specs = tuple(package_specs)

            # Reduce and cleanup each set of constraints.
            try:
                reduced_spec = self.reduce_specs(specs)
            except EmptyReduction:
                logging.warning(f"Skip package {package_id}.")
                continue

            # Print warning if specifiers were subject to a reduction.
            if len(specs) > 1:
                logging.warning(
                    f"{package_id} specifiers reduced from "
                    f"{', '.join(sorted(s.raw_spec for s in specs))} to {reduced_spec}",
                )

            yield package_id, reduced_spec

    def resolve_specs_group_by_managers(self) -> dict[str | None, set[Specifier]]:
        """Resolves package specs, and returns them grouped by managers."""
        packages_per_managers: dict[str | None, set[Specifier]] = {}
        for _package_id, spec in self.resolve_package_specs():
            manager_id = None
            if spec:
                manager_id = spec.manager_id
            packages_per_managers.setdefault(manager_id, set()).add(spec)

        return packages_per_managers
