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
"""Utilities and helper to organize, inspect and audit the capabilities of mpm and
package managers."""

from __future__ import annotations

import logging
from functools import wraps

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import ParamSpec, TypeVar

    from .base import Package, PackageManager

    P = ParamSpec("P")
    T = TypeVar("T")


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
                logging.warning(
                    f"{self.id} does not implement exact search operation.",
                )
            if extended and not extended_support:
                refilter = True
                logging.warning(
                    f"{self.id} does not implement extended search operation.",
                )
            if refilter:
                logging.warning("Refiltering of raw results has been activated.")

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
