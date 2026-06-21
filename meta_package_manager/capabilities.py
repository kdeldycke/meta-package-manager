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
"""Declaration and inspection of the operations each package manager supports.

A concrete manager advertises what it can do by implementing operation methods and
annotating them with the helpers defined here:

- :py:func:`meta_package_manager.capabilities.search_capabilities` and
  :py:func:`meta_package_manager.capabilities.version_not_implemented` flag the
  refinements an operation does *not* natively support, letting the framework
  compensate (refiltering search results, warning about ignored version pins).
- :py:class:`meta_package_manager.capabilities.Delegate` and
  :py:class:`meta_package_manager.capabilities.DelegatedMethod` let a manager reuse
  another manager's CLI for an operation instead of reimplementing it.

Together they expose a uniform capability surface that
:py:func:`meta_package_manager.capabilities.implements` introspects and the CLI uses to
route each command only to the managers that support it. The
:py:class:`meta_package_manager.capabilities.Operations` enum is the vocabulary of those
routable actions.
"""

from __future__ import annotations

import logging
from enum import Enum
from functools import wraps

from .manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import ParamSpec, TypeVar

    from .package import Package

    P = ParamSpec("P")
    T = TypeVar("T")


class Operations(Enum):
    """Recognized operation IDs that are implemented by package manager with their
    specific CLI invocation.

    Each operation has its own CLI subcommand.
    """

    installed = "installed"
    outdated = "outdated"
    search = "search"
    install = "install"
    upgrade = "upgrade"
    upgrade_all = "upgrade_all"
    remove = "remove"
    sync = "sync"
    cleanup = "cleanup"

    def __str__(self) -> str:
        """Render as the bare operation name (``outdated``), not the enum repr."""
        return self.name

    def __format__(self, format_spec: str) -> str:
        """Make f-strings use the bare name across all supported Python versions."""
        return str(self)


def implements(manager: PackageManager | type[PackageManager], op: Operations) -> bool:
    """Inspect a manager's implementation to check for proper support of an operation.

    Accepts either a manager instance or its class; support is determined from the
    class hierarchy.
    """
    cls = manager if isinstance(manager, type) else type(manager)
    logging.debug(f"Does {cls} implements {op}?")

    # General case: the operation and the method implementing it shares the same ID.
    method_deps: tuple[set[str], ...] = ({op.name},)

    # Special case for single-package `upgrade`: we depends on `upgrade_one_cli()`.
    if op == Operations.upgrade:
        method_deps = ({"installed", "upgrade_one_cli"},)

    # For `upgrade_all`: we depends on eother `upgrade_all_cli()`, or we can
    # simulate the latter with a combination of `outdated()` and
    # `upgrade_one_cli()`.
    elif op == Operations.upgrade_all:
        method_deps = ({"upgrade_all_cli"}, {"outdated", "upgrade_one_cli"})

    # If none of the classes in the inheritance hierarchy up to the base one
    # implements the operation, then we can be certain the manager doesn't implement
    # the operation at all.
    for klass in cls.mro():
        if klass is PackageManager:
            return False
        # Presence of the operation function is not enough to rules out proper
        # implementation, as it can be a method that raises NotImplemented error
        # anyway. See for instance the upgrade_all_cli in pip.py:
        # https://github.com/kdeldycke/meta-package-manager/blob/4acc003/meta_package_manager/managers/pip.py#L271-L279
        for method_ids in method_deps:
            all_deps_found = method_ids.issubset(klass.__dict__)
            if all_deps_found:
                return True

    msg = f"Can't guess {cls} implementation of {op}."
    raise NotImplementedError(msg)


def search_capabilities(extended_support: bool = True, exact_support: bool = True):
    """Decorator factory to be used on ``search()`` operations to signal ``mpm``
    framework manager's capabilities."""

    def decorator(function):
        @wraps(function)
        def wrapper(
            self: PackageManager,
            query: str,
            extended: bool,
            exact: bool,
        ) -> Iterator[Package]:
            refilter = False
            if exact and not exact_support:
                refilter = True
                logging.info(
                    f"{self.id} does not implement exact search operation.",
                )
            if extended and not extended_support:
                refilter = True
                logging.info(
                    f"{self.id} does not implement extended search operation.",
                )
            if refilter:
                logging.debug("Refiltering of raw results has been activated.")

            return function(self, query, extended, exact)  # type: ignore

        return wrapper

    return decorator


def version_not_implemented(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to be used on ``install()`` or ``upgrade_one_cli()`` operations to
    signal that a particular operation does not implement (yet) the version specifier
    parameter."""

    @wraps(func)
    def print_warning(*args: P.args, **kwargs: P.kwargs) -> T:
        if kwargs.get("version"):
            logging.warning(
                f"{func.__qualname__} does not implement version parameter. "
                "Let the package manager choose the version.",
            )
        return func(*args, **kwargs)

    return print_warning


class DelegatedMethod:
    """Descriptor that delegates a method call to another manager's CLI.

    When accessed on an instance, returns a wrapper that sets
    ``_delegate_cli_path`` on the instance so that ``build_cli`` uses the
    target manager's binary instead of the host manager's own CLI.
    """

    def __init__(self, method: Callable, cli_name: str) -> None:
        self.method = method
        self.cli_name = cli_name
        self.__doc__ = method.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: PackageManager | None, objtype: type | None = None):
        if obj is None:
            return self

        method = self.method
        cli_name = self.cli_name

        @wraps(method)
        def wrapper(*args, **kwargs):
            cli_path = obj.which(cli_name)
            logging.debug(
                f"Delegating {obj.id}.{self.attr_name} to {cli_name} at {cli_path}.",
            )
            obj._delegate_cli_path = cli_path  # type: ignore[attr-defined]
            try:
                return method(obj, *args, **kwargs)
            finally:
                del obj._delegate_cli_path  # type: ignore[attr-defined]

        return wrapper


class Delegate:
    """Factory that creates :class:`DelegatedMethod` descriptors for delegating
    operations to another package manager's CLI.

    Typical usage in a manager class body:

    .. code-block:: python

        from .scoop import Scoop

        _scoop = Delegate(Scoop)
        install = _scoop.install
        remove = _scoop.remove
    """

    def __init__(self, source_class: type[PackageManager]) -> None:
        self.source_class = source_class
        self.cli_name = source_class.cli_names[0]

    def __getattr__(self, name: str) -> DelegatedMethod:
        method = getattr(self.source_class, name)
        if not callable(method):
            msg = f"{self.source_class.__name__}.{name} is not callable."
            raise TypeError(msg)
        return DelegatedMethod(method, self.cli_name)
