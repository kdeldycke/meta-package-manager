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

"""Helpers and utilities to parse and compare version numbers."""

from __future__ import annotations

import operator
import re
from copy import deepcopy
from functools import partial
from typing import Iterator

from boltons import strutils

ALNUM_EXTRACTOR = re.compile("(\\d+ | [a-z]+)", re.VERBOSE)


class Token:
    """A token is a normalized word, persisting its lossless integer variant.

    Support natural comparison with ``str`` and ``int`` types.

    We mainly use them here to compare versions and package IDs.
    """

    string: str
    integer: int | None = None

    def __hash__(self):
        """A Token is made unique by a tuple of its immutable internal data."""
        return hash((self.string, self.integer))

    @staticmethod
    def str_to_int(value: str | int) -> tuple[str, int | None]:
        """Convert a ``str`` or an ``int`` to a ``(string, integer)`` couple.

        Returns together the original string and its integer representation if
        conversion is successful and lossless. Else, returns the original value and
        ``None``.
        """
        try:
            integer = int(value)
        except ValueError:
            return str(value), None
        value = str(value)

        # Double-check the string <> integer lossless transform.
        str_int = value.lstrip("0")
        if not str_int:
            str_int = "0"
        if str(integer) != str_int:
            raise TypeError(
                f"{value!r} string is not equivalent to {integer!r} integer."
            )

        return value, integer

    def __init__(self, value: str | int) -> None:
        """Instantiates a ``Token`` from an alphanumeric string or a non-negative
        integer."""
        # Check provided value.
        if isinstance(value, str):
            if not value.isalnum():
                raise TypeError("Only alphanumeric characters are allowed.")
        elif isinstance(value, int):
            if value < 0:
                raise TypeError("Negative integers not allowed.")
        else:
            raise TypeError("Only string and integer allowed.")

        # Parse user-value and stores its string and integer representations.
        self.string, self.integer = self.str_to_int(value)

    def __repr__(self) -> str:
        """Prints internal string and number values for debug."""
        return "<Token:{}>".format(
            ",".join(f"{k}={v!r}" for k, v in self.__dict__.items())
        )

    def __str__(self) -> str:
        return self.string

    def __len__(self) -> int:
        return len(self.string)

    def __format__(self, format_spec) -> str:
        return self.string.__format__(format_spec)

    def __int__(self) -> int | None:
        return self.integer

    @property
    def isint(self) -> bool:
        """Does the ``Token`` got an equivalent pure integer representation?"""
        return self.integer is not None

    """ Compare the current ``Token`` instance to the other as integers if both can be losslessly interpreted as pure integers.

    If one at least is not an integer, we convert all of them to string to allow comparison.
    """

    def _match_type(self, other):
        """Returns the safe type with which we can compare the two values."""
        if self.isint:
            if isinstance(other, int):
                return int
            if isinstance(other, Token) and other.isint:
                return int
        return str

    def __eq__(self, other):
        return operator.eq(*map(self._match_type(other), [self, other]))

    def __ne__(self, other):
        return operator.ne(*map(self._match_type(other), [self, other]))

    def __gt__(self, other):
        return operator.gt(*map(self._match_type(other), [self, other]))

    def __lt__(self, other):
        return operator.lt(*map(self._match_type(other), [self, other]))

    def __ge__(self, other):
        return operator.ge(*map(self._match_type(other), [self, other]))

    def __le__(self, other):
        return operator.le(*map(self._match_type(other), [self, other]))


class TokenizedString:

    """Tokenize a string for user-friendly sorting.

    Essentially a wrapper around a list of ``Token`` instances.
    """

    separator: str = ""
    string: str
    tokens: tuple[Token, ...] = ()

    def __hash__(self):
        """A ``TokenizedString`` is made unique by its original string and tuple of
        parsed tokens."""
        return hash((self.string, self.separator, self.tokens))

    def __new__(cls, value, *args, **kwargs):
        """Return same object if a ``TokenizedString`` parameter is used at
        instantiation.

        .. hint::

            If :py:meth:`object.__new__` returns an instance of ``cls``, then the new instance's
            :py:meth:`object.__init__` method will be invoked.

        .. seealso::

            An alternative would be to `merge __init__ with __new__ <https://stackoverflow.com/a/53482003>`_.
        """
        if value is None:
            return None
        # Returns the instance as-is if of the same class. Do not reparse it.
        if value and isinstance(value, TokenizedString):
            return value
        # Create a brand new instance. __init__() will be auto-magiccaly called
        # after that.
        return super().__new__(cls)

    def __init__(self, value: str | int, separator: str = "-") -> None:
        """Parse and tokenize the provided raw ``value``."""
        if isinstance(value, TokenizedString):
            # Skip initialization for instance of the class, as this __init__() gets called
            # auto-magiccaly eveytime the __new__() method above returns a
            # TokenizedString instance.
            return
        # Our canonical __init__() starts here.
        if isinstance(value, int):
            self.string = str(value)
        elif isinstance(value, str):
            self.string = value.strip()
        else:
            raise TypeError(f"{type(value)} not supported")
        self.tokens = tuple(self.tokenize(self.string))
        self.separator = separator

    def __deepcopy__(self, memo):
        """Generic recursive deep copy of the current instance.

        This is required to make the :py:meth:`copy.deepcopy` called within
        :py:meth:`dataclasses.asdict` working, because the defaults implementation doesn't know how to
        handle the ``value`` parameter provided in the
        :py:meth:`meta_package_manager.version.TokenizedString.__init__` method above.

        .. seealso::

            https://stackoverflow.com/a/57181955
        """
        # Extract the class of the object
        cls = self.__class__
        # Create a new instance of the object based on extracted class
        instance = super().__new__(cls)
        memo[id(self)] = instance
        for k, v in self.__dict__.items():
            # Recursively copy the whole tree of objects.
            setattr(instance, k, deepcopy(v, memo))
        return instance

    def __repr__(self) -> str:
        return f"<TokenizedString {self.string} => {self.tokens}>"

    def __str__(self) -> str:
        return self.string

    def __len__(self) -> int:
        return len(self.string)

    def __format__(self, format_spec) -> str:
        return self.string.__format__(format_spec)

    def pretty_print(self) -> str:
        return self.separator.join(map(str, self.tokens))

    @classmethod
    def tokenize(cls, string: str) -> Iterator[Token]:
        """Tokenize a string: ignore case and split at each non-alphanumeric characters.

        Returns a list of ``Token`` instances.
        """
        normalized_str = strutils.asciify(string).lower().decode()

        for segment in ALNUM_EXTRACTOR.split(normalized_str):
            if segment.isalnum():
                yield Token(segment)

    """ ``TokenizedString`` can be compared as tuples as-is.

    Thanks to the ``Token`` subobject we can compare a mix of strings and integers.
    That way we get natural, user-friendly sorting of version numbers.

    Something we cannot have with simple Python types to compare versions:

    .. code-block:: python

        >>> '2019.0.1' > '9.3'
        False
        >>> ('2019', '0', '1') > ('9', '3')
        False
        >>> (2019, 0, 1) > (9, 3)
        True
    """

    def __iter__(self):
        """``TokenizedString`` are essentially a wrapper around a tuple of ``Token``
        objects."""
        return iter(self.tokens)

    def __eq__(self, other):
        if other is None:
            return False
        if isinstance(other, (TokenizedString, tuple)):
            return tuple(self) == tuple(other)
        return super().__eq__(other)

    def __ne__(self, other):
        if other is None:
            return True
        if isinstance(other, TokenizedString):
            return tuple(self) != tuple(other)
        return super().__ne__(other)

    def __gt__(self, other):
        if other is None:
            return True
        if isinstance(other, TokenizedString):
            return tuple(self) > tuple(other)
        return super().__gt__(other)

    def __lt__(self, other):
        if other is None:
            return False
        if isinstance(other, TokenizedString):
            return tuple(self) < tuple(other)
        return super().__lt__(other)

    def __ge__(self, other):
        if other is None:
            return True
        if isinstance(other, TokenizedString):
            return tuple(self) >= tuple(other)
        return super().__ge__(other)

    def __le__(self, other):
        if other is None:
            return False
        if isinstance(other, TokenizedString):
            return tuple(self) <= tuple(other)
        return super().__le__(other)


parse_version = partial(TokenizedString, separator=".")
""" Utility method tweaking ``TokenizedString`` for dot-based serialization. """
