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
"""End-of-run summary printing for :command:`mpm` subcommands.

Every long-running subcommand (``installed``, ``outdated``, ``search``,
``dump``, ``sbom``) closes with a one-line summary written to stderr:

.. code-block:: text

    223 packages total (brew: 223).

Plus optional follow-up lines specific to that subcommand (the SBOM
writer surfaces upstream-document merge counts and dependency-graph
edge counts here). The whole summary is gated by the global
``--summary/--no-summary`` flag and respects the user's choice across
every subcommand uniformly.

Vocabulary note: "summary" describes the rendered text that lands on
stderr. "Stats" describes the raw numbers fed into it
(:py:meth:`meta_package_manager.sbom.base.SBOM.stats` returns a dict of
counts). The two terms stay distinct deliberately: the
flag/module/function name reflects what the user sees; the data-side
method keeps the unambiguous ``stats`` name.

This module is the single home of the summary contract:

- :py:func:`print_summary` is the renderer.
- :py:func:`package_counts` collapses the boilerplate
  ``Counter({manager_id: len(payload[manager_id]["packages"]) for ...})``
  pattern that ``installed``, ``outdated``, and ``search`` all share.
- :py:func:`sbom_summary` adapts
  :py:meth:`meta_package_manager.sbom.base.SBOM.stats` to the
  ``(counter, notes)`` shape :py:func:`print_summary` consumes, conditional
  on what the run actually did.

The renderer stays in this module rather than scattered across each
subcommand so the visual format is unique and obvious to find. The
adapters live here too because their job is to translate
subcommand-native shapes into the print contract, which is also
summary-domain logic.
"""

from __future__ import annotations

from collections import Counter
from typing import cast

from click_extra import echo

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .sbom.base import SBOM


def print_summary(
    counts: Counter,
    notes: Iterable[str] = (),
) -> None:
    """Print a one-line per-category count to stderr, plus optional follow-up notes.

    ``counts`` is a :py:class:`collections.Counter` keyed by an opaque
    category label. The label is usually a package manager id, but the
    ``dump --brewfile`` subcommand uses Brewfile entry types and any
    future caller is free to use whatever bucket makes sense. The
    parameter is named ``counts`` rather than ``manager_stats`` to
    avoid lying about the key's meaning.

    Prints something like:

    .. code-block:: text

        10 packages total (brew: 2, pip: 2, gem: 2, vscode: 2, npm: 2, composer: 0).

    ``notes`` is an iterable of follow-up lines printed verbatim under
    the count line. ``mpm sbom`` uses it to surface facts that don't
    fit the per-category-Counter shape: number of upstream SBOM
    documents merged into the aggregate, enrichment ratios,
    dependency-graph edge counts. Other subcommands today pass no
    notes; the count line is enough.

    Always writes to stderr so the call site is free to pipe stdout
    elsewhere (a generated SBOM document, a TOML manifest, a Brewfile)
    without the summary polluting the output. Gated upstream by the
    global ``--summary/--no-summary`` flag; this function itself is
    unconditional once called.
    """
    per_category = ""
    if counts:
        per_category = f" ({', '.join(f'{k}: {v}' for k, v in counts.most_common())})"
    total = counts.total()
    plural = "s" if total > 1 else ""
    echo(f"{total} package{plural} total{per_category}.", err=True)
    for note in notes:
        echo(note, err=True)


def package_counts(payload: Mapping[str, Mapping]) -> Counter[str]:
    """Build a per-manager ``Counter`` from a typical subcommand payload.

    ``installed``, ``outdated``, and ``search`` all stash their results
    in a ``{manager_id: {"packages": [...]}}`` dict. This helper turns
    that into the count-by-manager-id ``Counter`` that
    :py:func:`print_summary` accepts, eliminating the
    ``Counter({k: len(v["packages"]) for k, v in payload.items()})``
    boilerplate that appeared verbatim at three CLI call sites.

    Mismatched payloads (an extractor that stashes packages under a
    different key, the ``dump --brewfile`` line-counter pass) build
    their ``Counter`` inline rather than wedging this helper into
    serving every shape.
    """
    return Counter({k: len(v["packages"]) for k, v in payload.items()})


def sbom_summary(sbom: SBOM, bundled: bool) -> tuple[Counter, list[str]]:
    """Adapt :py:meth:`meta_package_manager.sbom.base.SBOM.stats` to the
    :py:func:`print_summary` shape.

    SBOM stats live on the renderer because the renderer knows what
    actually landed in the document (after dedup, after merge). This
    adapter flattens that structured dict into the count-line +
    follow-up-notes shape :py:func:`print_summary` consumes, conditioning
    each note on what the run actually did so ``--minimal`` scans,
    casks-only runs, and formats without a merge concept all stay
    tidy.

    The function lives in this module (rather than next to the SBOM
    renderers) because its job is translating between two different
    data shapes: SBOM stats on one side, the print contract on the
    other. Summary-domain glue, not SBOM-domain logic.
    """
    stats = sbom.stats()
    packages_per_manager = cast(
        "dict[str, int]", stats.get("packages_per_manager") or {}
    )
    counts: Counter[str] = Counter(packages_per_manager)

    notes: list[str] = []
    total_packages = counts.total()
    if bundled and total_packages:
        enriched_per_manager = cast(
            "dict[str, int]", stats.get("enriched_per_manager") or {}
        )
        total_enriched = sum(enriched_per_manager.values())
        notes.append(
            f"{total_enriched}/{total_packages} packages enriched with metadata."
        )

    merged = stats.get("merged_documents") or 0
    transitive = stats.get("transitive_packages_merged") or 0
    if merged:
        if transitive:
            notes.append(
                f"{merged} upstream SBOM documents merged, adding "
                f"{transitive} transitive packages."
            )
        else:
            notes.append(f"{merged} upstream SBOM documents merged.")

    bom_refs = stats.get("external_bom_references") or 0
    if bom_refs:
        notes.append(f"{bom_refs} per-package upstream SBOMs attached by reference.")

    dep_relationships = stats.get("dependency_relationships") or 0
    if dep_relationships:
        notes.append(f"{dep_relationships} dependency relationships emitted.")

    dep_edges = stats.get("dependency_edges") or 0
    if dep_edges:
        notes.append(f"{dep_edges} dependency edges emitted.")

    vulnerabilities = stats.get("vulnerabilities_total") or 0
    vulnerable_packages = stats.get("vulnerable_packages") or 0
    if vulnerabilities:
        notes.append(
            f"{vulnerabilities} vulnerabilities found across "
            f"{vulnerable_packages} packages."
        )

    return counts, notes
