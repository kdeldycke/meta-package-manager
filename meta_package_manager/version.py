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

""" Helpers and utilities to parse and compare version numbers. """

import operator
import re
from functools import partial

from boltons import strutils

ALNUM_EXTRACTOR = re.compile("(\\d+ | [a-z]+)", re.VERBOSE)


class Token:
    """A token is a normalized word, persisting its lossless integer variant.

    Support natural comparison with `str` and `int` types.

    We mainly use them here to compare versions and package IDs.
    """

    string = None
    integer = None

    def __hash__(self):
        """A Token is made unique by a tuple of its immutable internal data."""
        return hash((self.string, self.integer))

    @staticmethod
    def str_to_int(string):
        """Convert a string or an integer to a `(string, integer)` couple.

        Returns together the original string and its integer representation if
        convertion is successful and lossless. Else returns the original string
        and `None`."""
        try:
            integer = int(string)
        except ValueError:
            return str(string), None
        string = str(string)

        # Double-check the string <> integer lossless transform.
        str_int = string.lstrip("0")
        if not str_int:
            str_int = "0"
        if str(integer) != str_int:
            raise TypeError(
                f"{string!r} string is not equivalent to {integer!r} integer."
            )

        return string, integer

    def __init__(self, value):
        """Instantiates a Token from alphanumeric strings or non-negative
        integers.
        """
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

    def __repr__(self):
        """Prints internal string and number values for debug."""
        return "<Token:{}>".format(
            ",".join((f"{k}={v!r}" for k, v in self.__dict__.items()))
        )

    def __str__(self):
        return self.string

    def __int__(self):
        return self.integer

    @property
    def isint(self):
        """Does the Token got a pure integer representation?"""
        return self.integer is not None

    """ In the best case, try to comparison Token to integers.

    If one or the two is an integer but not the other, we convert all to
    string to allow comparison.
    """

    def _match_type(self, other):
        """Returns the safe type with which we can compare two values."""
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

    Essentially a wrapper around a tuple of `Token` instances.
    """

    separator = None
    string = None
    tokens = ()

    def __hash__(self):
        """A `TokenizedString` is made unique by its original string and tuple
        of parsed tokens."""
        return hash((self.string, self.separator, self.tokens))

    def __new__(cls, value, *args, **kwargs):
        """Return same object if a TokenizedString parameter is used at
        instanciation.
        """
        if isinstance(value, TokenizedString):
            return value
        return super(TokenizedString, cls).__new__(cls)

    def __init__(self, value, separator="-"):
        if isinstance(value, TokenizedString):
            # Skip initialization for instance of the class.
            return
        if isinstance(value, int):
            self.string = str(value)
        elif isinstance(value, str):
            self.string = value.strip()
        else:
            raise TypeError("{} not supported".format(type(value)))
        self.tokens = tuple(self.tokenize(self.string))
        self.separator = separator

    def __repr__(self):
        return f"<TokenizedString {self.string} => {self.tokens}>"

    def __str__(self):
        return self.string

    def pretty_print(self):
        return self.separator.join(map(str, self.tokens))

    @classmethod
    def tokenize(cls, string):
        """Tokenize a string: ignore case and split at each non-alphanumeric
        characters.

        Returns a tuple of Token instances. Which allows for comparison between
        strings and integers. That way we get natural, user-friendly sorting of
        version numbers. That we can get with simple Python, see:

            >>> '2019.0.1' > '9.3'
            False
            >>> ('2019', '0', '1') > ('9', '3')
            False
            >>> (2019, 0, 1) > (9, 3)
            True
        """
        normalized_str = strutils.asciify(string).lower().decode()

        for segment in ALNUM_EXTRACTOR.split(normalized_str):
            if segment.isalnum():
                yield Token(segment)

    """ TokenizedString can be compared as tuples. """

    def __iter__(self):
        """`TokenizedString` essentially are a wrapper around a tuple of
        `Token`.
        """
        return iter(self.tokens)

    def __eq__(self, other):
        if isinstance(other, (TokenizedString, tuple)):
            return tuple(self) == tuple(other)

    def __ne__(self, other):
        if isinstance(other, TokenizedString):
            return tuple(self) != tuple(other)

    def __gt__(self, other):
        if isinstance(other, TokenizedString):
            return tuple(self) > tuple(other)

    def __lt__(self, other):
        if isinstance(other, TokenizedString):
            return tuple(self) < tuple(other)

    def __ge__(self, other):
        if isinstance(other, TokenizedString):
            return tuple(self) >= tuple(other)

    def __le__(self, other):
        if isinstance(other, TokenizedString):
            return tuple(self) <= tuple(other)


""" Utility method tweaking TokenizedString for dot-based serialization. """
parse_version = partial(TokenizedString, separator=".")
