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
"""Registration, indexing and caching of package manager supported by ``mpm``."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import cached_property

from boltons.iterutils import unique
from click_extra import Spinner, get_current_context
from click_extra.context import JOBS, VERBOSITY
from click_extra.theme import KO_GLYPH, OK_GLYPH, get_current_theme as theme

from .capabilities import implements
from .execution import SPINNER_DELAY
from .managers.apk import APK
from .managers.apm import APM
from .managers.apt import APT, APT_Mint
from .managers.asdf import ASDF
from .managers.cargo import Cargo
from .managers.chocolatey import Choco
from .managers.composer import Composer
from .managers.cpan import CPAN
from .managers.deb_get import Deb_Get
from .managers.dnf import DNF, DNF5, YUM
from .managers.emerge import Emerge
from .managers.eopkg import EOPKG
from .managers.flatpak import Flatpak
from .managers.fwupd import FWUPD
from .managers.gem import Gem
from .managers.guix import Guix
from .managers.homebrew import Brew, Cask
from .managers.macports import MacPorts
from .managers.mas import MAS
from .managers.mise import Mise
from .managers.nix import Nix
from .managers.npm import NPM
from .managers.opkg import OPKG
from .managers.pacman import Pacaur, Pacman, Paru, Yay
from .managers.pacstall import Pacstall
from .managers.pip import Pip
from .managers.pipx import Pipx
from .managers.pkg import PKG, Ports
from .managers.pwsh_gallery import PWSH_Gallery
from .managers.scoop import Scoop
from .managers.sdkman import SDKMAN
from .managers.sfsu import SFSU
from .managers.snap import Snap
from .managers.steamcmd import SteamCMD
from .managers.stew import Stew
from .managers.topgrade import Topgrade
from .managers.uv import UV, UVX
from .managers.vscode import VSCode, VSCodium
from .managers.winget import WinGet
from .managers.xbps import XBPS
from .managers.yarn import YarnBerry, YarnClassic
from .managers.zerobrew import ZeroBrew
from .managers.zypper import Zypper

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import Final

    from click_extra import Context

    from .capabilities import Operations
    from .manager import PackageManager


manager_classes = (
    APK,
    APM,
    APT,
    APT_Mint,
    ASDF,
    Brew,
    Cargo,
    Cask,
    Choco,
    Composer,
    CPAN,
    Deb_Get,
    DNF,
    DNF5,
    Emerge,
    EOPKG,
    Flatpak,
    FWUPD,
    Gem,
    Guix,
    MacPorts,
    MAS,
    Mise,
    Nix,
    NPM,
    OPKG,
    Pacaur,
    Pacman,
    Pacstall,
    Paru,
    Pip,
    Pipx,
    PKG,
    Ports,
    PWSH_Gallery,
    Scoop,
    SDKMAN,
    SFSU,
    Snap,
    SteamCMD,
    Stew,
    Topgrade,
    UV,
    UVX,
    VSCode,
    VSCodium,
    WinGet,
    XBPS,
    YarnBerry,
    YarnClassic,
    Yay,
    YUM,
    ZeroBrew,
    Zypper,
)
"""The list of all classes implementing the specific package managers.

Is considered valid package manager, definitions classes which:

#. are located in the :py:prop:`meta_package_manager.pool.ManagerPool.manager_subfolder`
    subfolder, and
#. are sub-classes of :py:class:`meta_package_manager.manager.PackageManager`, and
#. are not :py:prop:`meta_package_manager.manager.PackageManager.virtual` (i.e. have a
    non-null :py:prop:`meta_package_manager.manager.PackageManager.cli_names` property).

These properties are checked and enforced in unittests.
"""


# Concurrent dispatch
#
# Read-only operations query each manager independently, so they parallelize
# cleanly across a thread pool. These free functions own that policy: the
# sequential-fallback decision (:func:`effective_jobs`), the up-front availability
# warming used during selection (:func:`warm_availability`), and the spinner-wrapped
# batch runner the CLI's read-only subcommands drive (:func:`collect_from_managers`).


def effective_jobs(ctx: Context | None, count: int) -> int:
    """Resolve how many worker threads to use for a batch of ``count`` items.

    Returns the number of managers to process in parallel; ``1`` means run
    sequentially in the calling thread. Collapses to sequential when:

    - there is no active CLI context (programmatic or test use),
    - a single item leaves nothing to parallelize,
    - the user passed :option:`mpm --jobs` ``1``, or
    - verbosity is ``DEBUG``, where coherent per-manager log narration matters
      more than the speed-up (interleaved threads would scramble it).

    Otherwise the :option:`mpm --jobs` value wins, capped at ``count``: there is
    no point spinning up more workers than there are items.
    """
    if ctx is None or count <= 1:
        return 1
    if ctx.meta.get(VERBOSITY) == "DEBUG":
        return 1
    jobs = ctx.meta.get(JOBS, 1)
    return min(jobs, count) if jobs > 1 else 1


def warm_availability(managers: Iterable[PackageManager]) -> None:
    """Probe several managers' ``available`` concurrently.

    Reading ``available`` forces a manager's ``--version`` detection, whose
    result (and the ``cli_path`` / ``executable`` / ``version`` it depends on) is
    cached on the instance. Warming the candidate set up front turns the
    sequential string of probes into a single round bounded by the slowest one,
    shaving startup latency off any command that touches many managers.

    Each manager is a distinct instance with its own cached attributes and
    subprocess, so the probes are independent and thread-safe; the GIL is released
    while each waits. The executor barrier publishes every cached value before the
    caller reads it back.

    Sized by :func:`effective_jobs`: a no-op (leaving the probes to lazy,
    sequential evaluation) without an active context, at ``DEBUG`` verbosity, for a
    single candidate, or at :option:`mpm --jobs` ``1``.
    """
    candidates = list(managers)
    jobs = effective_jobs(get_current_context(silent=True), len(candidates))
    if jobs <= 1:
        return
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        # Reading `available` forces and caches the probe inside each worker.
        list(executor.map(lambda manager: manager.available, candidates))


def collect_from_managers(
    ctx: Context,
    label: str,
    done_label: str,
    managers: list[PackageManager],
    work: Callable[[PackageManager], tuple[str, dict]],
) -> list[tuple[str, dict]]:
    """Run ``work(manager)`` for every manager and return the results in order.

    Read-only operations query each manager independently, so they run
    concurrently across a thread pool sized by :func:`effective_jobs` (itself
    driven by :option:`mpm --jobs`). The work is subprocess I/O, during which the
    GIL is released, so threads parallelize it fully: a slow ``guix search`` no
    longer blocks the fast managers while it runs.

    Execution falls back to sequential when :func:`effective_jobs` returns ``1``
    (a single manager, :option:`mpm --jobs` ``1``, or ``DEBUG`` verbosity, where
    interleaved per-manager logs would be unreadable).

    In concurrent mode the per-manager spinners would garble each other on stderr,
    so they are suppressed in favor of a single aggregate spinner. While the batch
    runs it shows a live ``done/total`` count, and once it is actually drawing (a
    slow batch on a terminal) it leaves a ``✓``/``✗`` trail of each manager as it
    lands plus a persistent ``✓ Searched N managers (Ns)`` finisher. Fast, piped or
    serialized runs get none of this: :py:meth:`click_extra.Spinner.echo` and
    :py:meth:`click_extra.Spinner.ok` both write unconditionally, so every such
    call is gated on the spinner having been shown.

    :param label: present-tense verb shown in the running spinner ("Searching").
    :param done_label: past-tense verb for the persistent finisher ("Searched").
    :param managers: the already-selected managers, materialized so their version
        probes and per-manager option stamping happen up front, in this thread.
    :param work: returns this manager's ``(id, data)`` result; it must handle its
        own :py:class:`meta_package_manager.execution.CLIError` (each manager owns
        its subprocess and error list, so the call is thread-safe per manager). A
        truthy ``data["errors"]`` marks that manager's trail line with ``✗``.
    """
    jobs = effective_jobs(ctx, len(managers))
    if jobs <= 1:
        return [work(manager) for manager in managers]

    # Suppress the per-manager spinners (which would collide on stderr) and show a
    # single aggregate spinner for the whole concurrent batch instead.
    spinner_enabled = None if any(manager.progress for manager in managers) else False
    for manager in managers:
        manager.progress = False

    total = len(managers)
    results: list[tuple[str, dict]] = [("", {})] * total
    with Spinner(
        f"{label} 0/{total} managers",
        delay=SPINNER_DELAY,
        enabled=spinner_enabled,
        timer=True,
    ) as spinner:
        # Leave a ✓/✗ trail naming each manager (and whether it erred) as it lands,
        # so a slow batch shows which managers finished rather than a static total.
        # The trail only makes sense once the spinner is visible (a slow batch on a
        # terminal): echo() writes unconditionally, so a fast, piped or disabled run
        # must stay silent. But the spinner only appears after the show delay, by
        # which point the quickest managers have already finished — so buffer every
        # outcome and flush the backlog the moment the spinner first draws, then
        # stream the rest live. This keeps the ledger complete instead of dropping
        # whichever managers beat the delay.
        trail: list[tuple[str, dict]] = []

        def flush_trail() -> None:
            if not spinner.shown:
                return
            for manager_id, data in trail:
                glyph = (
                    theme().error(KO_GLYPH)
                    if data.get("errors")
                    else theme().success(OK_GLYPH)
                )
                spinner.echo(f"{glyph} {theme().invoked_command(manager_id)}")
            trail.clear()

        with ThreadPoolExecutor(max_workers=jobs) as executor:
            future_to_index = {
                executor.submit(work, manager): index
                for index, manager in enumerate(managers)
            }
            for done, future in enumerate(as_completed(future_to_index), 1):
                index = future_to_index[future]
                manager_id, data = future.result()
                results[index] = (manager_id, data)
                trail.append((manager_id, data))
                flush_trail()  # No-op until the spinner first draws.
                # `label` is safe to reassign while the spinner thread reads it.
                spinner.label = f"{label} {done}/{total} managers"
        # Drain any outcomes still buffered (the spinner may have first drawn only
        # after the last completion was checked), then leave a persistent
        # "✓ Searched N managers (Ns)" finisher. Both are gated on `shown`: ok()
        # writes unconditionally, so a fast, piped or serialized run gets neither.
        flush_trail()
        if spinner.shown:
            spinner.label = f"{done_label} {total} managers"
            spinner.ok()
    return results


class ManagerPool:
    """A dict-like register, instantiating all supported package managers."""

    ALLOWED_EXTRA_OPTION: Final = frozenset(
        {
            "cooldown",
            "dry_run",
            "ignore_auto_updates",
            "progress",
            "require_cooldown_support",
            "stop_on_error",
            "timeout",
        },
    )
    """List of extra options that are allowed to be set on managers during the use of
    the :py:func:`meta_package_manager.pool.ManagerPool.select_managers` helper
    below."""

    @cached_property
    def register(self) -> dict[str, PackageManager]:
        """Instantiate all supported package managers."""
        register = {}
        for klass in manager_classes:
            manager = klass()
            register[manager.id] = manager
        return register  # type: ignore[return-value]

    @cached_property
    def overridden_fields(self) -> dict[str, set[str]]:
        """Per-manager attribute names that the user explicitly overrode via
        ``[mpm.managers.<id>]``.

        Populated by :py:func:`meta_package_manager.config.apply_manager_overrides`.
        Read by ``_select_managers`` to skip the global ``--<flag>`` defaults
        for fields the user has explicitly set per manager. Tracked separately from
        instance ``__dict__`` membership so the global defaults can still refresh
        fields that were previously set by an earlier ``_select_managers`` call but
        were never user-overridden.
        """
        return {}

    # Emulates some dict methods.

    def __len__(self) -> int:
        return len(self.register)

    def __getitem__(self, key):
        return self.register[key]

    get = __getitem__

    def __iter__(self):
        yield from self.register

    def __contains__(self, key) -> bool:
        return key in self.register

    def values(self):
        return self.register.values()

    def items(self):
        return self.register.items()

    # Pre-compute all sorts of constants.

    @cached_property
    def all_manager_ids(self) -> tuple[str, ...]:
        """All recognized manager IDs.

        Returns a list of sorted items to provide consistency across all UI, and
        reproducibility in the order package managers are evaluated.
        """
        return tuple(sorted(self.register))

    @cached_property
    def maintained_manager_ids(self) -> tuple[str, ...]:
        """All manager IDs which are not deprecated."""
        return tuple(
            mid for mid in self.all_manager_ids if not self.register[mid].deprecated
        )

    @cached_property
    def default_manager_ids(self) -> tuple[str, ...]:
        """All manager IDs supported on the current platform and not deprecated.

        Must keep the same order defined by
        :py:prop:`meta_package_manager.pool.ManagerPool.all_manager_ids`.
        """
        return tuple(
            mid for mid in self.maintained_manager_ids if self.register[mid].supported
        )

    @cached_property
    def unsupported_manager_ids(self) -> tuple[str, ...]:
        """All manager IDs unsupported on the current platform but still maintained.

        Order is not important here as this list will be used to discard managers from
        selection sets.
        """
        return tuple(
            mid
            for mid in self.maintained_manager_ids
            if mid not in self.default_manager_ids
        )

    def _select_managers(
        self,
        keep: Iterable[str] | None = None,
        drop: Iterable[str] | None = None,
        keep_deprecated: bool = False,
        keep_unsupported: bool = False,
        drop_not_found: bool = True,
        implements_operation: Operations | None = None,
        **extra_options: bool | int,
    ) -> Iterator[PackageManager]:
        """Utility method to extract a subset of the manager pool based on selection
        list (``keep`` parameter) and exclusion list (``drop`` parameter) criterion.

        By default, only the managers supported by the current platform are selected.
        Unless ``keep_unsupported`` is set to ``True``, in which case all managers
        implemented by ``mpm`` are selected, regardless of their supported platform.

        Deprecated managers are also excluded by default, unless ``keep_deprecated`` is
        ``True``.

        ``drop_not_found`` filters out managers whose CLI was not found on the system.

        ``implements_operation`` filters out managers which do not implements the
        provided operation.

        Finally, ``extra_options`` parameters are fed to manager objects to set some
        additional options.

        Returns a generator producing a manager instance one after the other.
        """
        # Track whether the caller passed an explicit keep list so we can pick
        # informative log levels for downstream skip messages: explicit picks
        # the user made (``--<id>`` flags) get loud levels; implicit defaults
        # (``mpm outdated`` with no flags) get demoted to DEBUG to avoid
        # flooding the output with one line per platform-default manager.
        explicit_selection = keep is not None

        # Produce the default set of managers to consider if none have been
        # provided by the ``keep`` parameter.
        if keep is None:
            if keep_deprecated:
                keep = self.all_manager_ids
            elif keep_unsupported:
                keep = self.maintained_manager_ids
            else:
                keep = self.default_manager_ids
        if drop is None:
            drop = set()
        assert set(self.all_manager_ids).issuperset(keep)
        assert set(self.all_manager_ids).issuperset(drop)

        assert self.ALLOWED_EXTRA_OPTION.issuperset(extra_options)

        # Reduce the set to the user's constraints.
        selected_ids = [mid for mid in unique(keep) if mid not in drop]

        # Probe every candidate's availability (its --version detection) up front
        # and in parallel, so the sequential string of probes below becomes a single
        # round capped at the slowest manager. This shaves startup latency off any
        # command that touches many managers; the filter loop stays sequential, so
        # its skip / "does not implement" logging keeps its order.
        if drop_not_found:
            warm_availability(
                self.register[manager_id]
                for manager_id in selected_ids
                if not implements_operation
                or implements(self.register[manager_id], implements_operation)
            )

        # Deduplicate managers IDs while preserving order, then remove excluded
        # managers.
        for manager_id in selected_ids:
            manager = self.register[manager_id]

            # Check if operation is not implemented before calling `.available`. It
            # saves one call to the package manager CLI.
            if implements_operation and not implements(manager, implements_operation):
                logging.log(
                    logging.WARNING if explicit_selection else logging.DEBUG,
                    f"{theme().invoked_command(manager_id)} "
                    f"does not implement {implements_operation}.",
                )
                continue

            # Filters out managers whose CLI was not found.
            if drop_not_found and not manager.available:
                reason = manager.unavailable_reason or "unavailable"
                logging.log(
                    logging.INFO if explicit_selection else logging.DEBUG,
                    f"Skip {theme().invoked_command(manager_id)} manager: {reason}.",
                )
                continue

            # Apply manager-level options. Skip a field that the user explicitly
            # overrode via [mpm.managers.<id>] so the per-manager value keeps
            # precedence over the global default.
            user_overrides = self.overridden_fields.get(manager_id, set())
            for param, value in extra_options.items():
                assert hasattr(manager, param)
                if param in user_overrides:
                    continue
                setattr(manager, param, value)

            # Tag the operation this manager is about to perform so its CLI calls
            # can resolve a per-operation timeout when the user set no explicit one
            # (see CLIExecutor._resolve_timeout). The matching subcommand runs right
            # after the manager is yielded.
            manager._active_operation = (
                implements_operation.name if implements_operation else None
            )

            yield manager

    def select_managers(self, *args, **kwargs) -> Iterator[PackageManager]:
        """Wraps ``_select_managers()`` to stop CLI execution if no manager are selected."""
        managers = self._select_managers(*args, **kwargs)
        first = next(managers, None)
        if first is None:
            logging.critical("No manager selected.")
            get_current_context().exit(2)
        yield first
        yield from managers


pool = ManagerPool()
