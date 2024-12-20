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
from functools import cached_property
from typing import TYPE_CHECKING, Final, Iterable, Iterator

from boltons.iterutils import unique
from click_extra import get_current_context
from click_extra.colorize import default_theme as theme
from more_itertools import peekable

from .managers.apm import APM
from .managers.apt import APT, APT_Mint
from .managers.cargo import Cargo
from .managers.chocolatey import Choco
from .managers.composer import Composer
from .managers.dnf import DNF, DNF5, YUM
from .managers.emerge import Emerge
from .managers.eopkg import EOPKG
from .managers.flatpak import Flatpak
from .managers.fwupd import FWUPD
from .managers.gem import Gem
from .managers.homebrew import Brew, Cask
from .managers.mas import MAS
from .managers.npm import NPM
from .managers.opkg import OPKG
from .managers.pacman import Pacaur, Pacman, Paru, Yay
from .managers.pip import Pip
from .managers.pipx import Pipx
from .managers.pkg import PKG
from .managers.scoop import Scoop
from .managers.snap import Snap
from .managers.steamcmd import SteamCMD
from .managers.uv import UV
from .managers.vscode import VSCode, VSCodium
from .managers.winget import WinGet
from .managers.yarn import Yarn
from .managers.zypper import Zypper

if TYPE_CHECKING:
    from .base import Operations, PackageManager

manager_classes = (
    APM,
    APT,
    APT_Mint,
    Brew,
    Cargo,
    Cask,
    Choco,
    Composer,
    DNF,
    DNF5,
    Emerge,
    EOPKG,
    Flatpak,
    FWUPD,
    Gem,
    MAS,
    NPM,
    OPKG,
    Pacaur,
    Pacman,
    Paru,
    Pip,
    Pipx,
    PKG,
    Scoop,
    Snap,
    SteamCMD,
    UV,
    VSCode,
    VSCodium,
    WinGet,
    Yarn,
    Yay,
    YUM,
    Zypper,
)
"""The list of all classes implementing the specific package managers.

Is considered valid package manager, definitions classes which:

#. are located in the :py:prop:`meta_package_manager.pool.ManagerPool.manager_subfolder`
    subfolder, and
#. are sub-classes of :py:class:`meta_package_manager.base.PackageManager`, and
#. are not :py:prop:`meta_package_manager.base.PackageManager.virtual` (i.e. have a
    non-null :py:prop:`meta_package_manager.base.PackageManager.cli_names` property).

These properties are checked and enforced in unittests.
"""


class ManagerPool:
    """A dict-like register, instantiating all supported package managers."""

    ALLOWED_EXTRA_OPTION: Final = frozenset(
        {"ignore_auto_updates", "stop_on_error", "dry_run", "timeout"},
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
        drop_inactive: bool = True,
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

        ``drop_inactive`` filters out managers that where not found on the system.

        ``implements_operation`` filters out managers which do not implements the
        provided operation.

        Finally, ``extra_options`` parameters are fed to manager objects to set some
        additional options.

        Returns a generator producing a manager instance one after the other.
        """
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
        selected_ids = (mid for mid in unique(keep) if mid not in drop)

        # Deduplicate managers IDs while preserving order, then remove excluded
        # managers.
        for manager_id in selected_ids:
            manager = self.register[manager_id]

            # Check if operation is not implemented before calling `.available`. It
            # saves one call to the package manager CLI.
            if implements_operation and not manager.implements(implements_operation):
                logging.warning(
                    f"{theme.invoked_command(manager_id)} "
                    f"does not implement {implements_operation}.",
                )
                continue

            # Filters out inactive managers.
            if drop_inactive and not manager.available:
                logging.info(
                    f"Skip unavailable {theme.invoked_command(manager_id)} manager.",
                )
                continue

            # Apply manager-level options.
            for param, value in extra_options.items():
                assert hasattr(manager, param)
                setattr(manager, param, value)

            yield manager

    def select_managers(self, *args, **kwargs) -> Iterator[PackageManager]:
        """Wraps ``_select_managers()`` to stop CLI execution if no manager are selected."""
        managers = peekable(self._select_managers(*args, **kwargs))
        try:
            managers.peek()
        except StopIteration:
            logging.critical("No manager selected.")
            get_current_context().exit(2)
        yield from managers


pool = ManagerPool()
