# -*- coding: utf-8 -*-
#
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

from boltons import strutils


class Token():
    """A token is a normalized word, persisting its lossless integer variant.

    Support natural comparison with `str` and `int` types.

    We mainly use them here to compare versions and package IDs.
    """

    string = None
    integer = None

    @staticmethod
    def str_to_int(string):
        """ Convert a string or an integer to a `(string, integer)` couple.

        Returns together the original string and its integer representation if
        convertion is successful and lossless. Else returns the original string
        and `None`."""
        try:
            integer = int(string)
        except ValueError:
            return str(string), None
        string = str(string)

        str_int = string
        if str_int != '0':
            str_int = string.lstrip('0')
        assert str(integer) == str_int

        return string, integer

    def __init__(self, value):
        """ Instantiates a Token from alphanumeric strings or non-negative
        integers.
        """
        # Check provided value.
        if isinstance(value, str):
            if not value.isalnum():
                raise TypeError('Only alphanumeric characters are allowed.')
        elif isinstance(value, int):
            if value < 0:
                raise TypeError('Negative integers not allowed.')
        else:
            raise TypeError('Only string and integer allowed.')

        # Parse user-value and stores its string and integer representations.
        self.string, self.integer = self.str_to_int(value)

    def __repr__(self):
        """ Prints internal string and number values for debug. """
        return '<Token:{}>'.format(','.join(
            ['{}={!r}'.format(k, v) for k, v in self.__dict__.items()]))

    def __str__(self):
        return self.string

    def __int__(self):
        return self.integer

    @property
    def isint(self):
        """ Does the Token got a pure integer representation? """
        return self.integer is not None

    """ In the best case, try to comparison Token to integers.

    If one or the two is an integer but not the other, we convert all to
    string to allow comparison.
    """

    def _match_type(self, other):
        """ Returns the safe type with which we can compare two values. """
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


def tokenize(string):
    """ Tokenize a string for user-friendly sorting, by ignoring case and
    splitting at each non-alphanumeric characters.

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
    tokens = []
    normalized_str = strutils.slugify(string, '-', ascii=True).decode()

    token = ''
    i = 0
    while i < len(normalized_str) + 1:

        char = ''
        if i < len(normalized_str):
            char = normalized_str[i]

        # If we already started accumulated characters, we continue to do so as
        # long as the token being constructed and the new character are of the
        # same kind.
        if char.isalnum():

            if not token:
                token += char
                i += 1
                continue

            if token.isdigit() and char.isdigit():
                token += char
                i += 1
                continue

            if token.isalpha() and char.isalpha():
                token += char
                i += 1
                continue

        # Token and char are not recognized (neither digit or alpha) or doesn't
        # share the same nature. Let's split to a new token.
        if token:
            # Save up the clean token in the list and reset it.
            tokens.append(Token(token))
            token = ''

        # Skip the current char from the iteration as it is not recognized.
        if not char.isalnum():
            i += 1

    return tuple(tokens)
