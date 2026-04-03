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
"""Helpers and utilities to parse and compare version numbers.

``mpm`` wraps dozens of package managers, each with its own versioning
scheme: semver, PEP 440, calendar versioning, Debian epochs, Gentoo
suffixes, and others. Rather than implementing format-specific parsers,
this module provides a universal tokenizer that produces good-enough
ordering across all of them.

Design
------

The tokenizer splits version strings into alternating **digit** and
**letter** tokens at every digit/letter boundary and every
non-alphanumeric separator. Tokens that parse as integers are compared
numerically; the rest are compared as lowercase strings. This gives
natural sort order where ``(2019, 0, 1) > (9, 3)`` — something neither
pure-string nor pure-numeric comparison achieves.

Key rules:

- **Integers outrank strings.** A numeric token always sorts higher than
  a string token at the same position. This makes ``3.12.0 > 3.12.0a4``
  (release beats alpha) and ``0.1 > 0.beta2`` work without
  understanding PEP 440 or semver pre-release semantics.

- **Trailing zeros are padding.** ``6.2`` and ``6.2.0`` compare equal.
  When one token tuple is a prefix of the other and all extra tokens are
  zero integers, the versions are equivalent.

- **Pre-release suffixes lose.** When a release version is a prefix of a
  longer version whose first significant extra token is a string (e.g.,
  ``"alpha"``, ``"git"``), the shorter release is considered greater.

- **Hex hashes stay whole.** A contiguous run of 7+ hex characters with
  interleaved digits and letters (at least one letter-then-digit and one
  digit-then-letter adjacency) is kept as a single opaque token.
  Without this, ``g6cd4c31`` would shatter into
  ``("g", 6, "cd", 4, "c", 31)``. The 7-character floor matches
  ``git``'s default abbreviated hash length (``core.abbrev``, the de
  facto standard on GitHub/GitLab/Bitbucket). The interleaving
  requirement rejects coincidental hex strings like asciified Unicode
  (``eeaccee231``), that have only one transition direction.

- **Digit/letter splitting is essential.** Splitting ``ubuntu1`` into
  ``("ubuntu", 1)`` enables natural numeric ordering of embedded version
  numbers: ``a4 < a10`` compares correctly because ``4`` and ``10``
  become integer tokens. Without this split, ``"a4" > "a10"``
  lexicographically.

Limitations
-----------

This is a heuristic comparator, not a format-specific parser.

- **PEP 440 ordering** is richer than what we implement. Epochs
  (``1!``), ``.devN`` ordering relative to pre-releases, and
  post-release semantics are not handled. Use ``packaging.version`` for
  strict PEP 440 compliance.

- **Perl floating-point versions** (``1.1 == 1.10``) are treated as
  ``(1, 1)`` vs ``(1, 10)`` — not equal. The Gentoo three-digit-group
  conversion scheme is not implemented.

- **Format-specific separators** like Debian epochs (``:``), Java build
  metadata (``,``), or Perl-style floats (``.``) are treated as plain
  delimiters, which can produce wrong comparison results when the
  separator carries structural meaning.

References
----------

- `PEP 440 <https://peps.python.org/pep-0440/>`_ — Python's version
  identification spec. Defines ``a``/``b``/``rc`` suffix ordering that
  our integer-outranks-string rule approximates.

- `Falsehoods about versions
  <https://github.com/xenoterracide/falsehoods/blob/master/versions.md>`_
  — 25 assumptions that break in practice. Validates our approach of not
  assuming any single format (falsehoods 4, 8, 13) and handling mixed
  numeric/string tokens (falsehoods 2, 3).

- `Gentoo Perl version scheme
  <https://wiki.gentoo.org/wiki/Project:Perl/Version-Scheme>`_ —
  illustrates how two incompatible formats (dotted-decimal and
  floating-point) require careful mapping. A reminder that version
  comparison cannot be reduced to "split on dots, compare integers."
"""

from __future__ import annotations

import operator
import re
from copy import deepcopy

from boltons import strutils
from click_extra import style

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


_ALNUM_PATTERN = r"""(
    (?= [0-9a-f]* [a-f] [0-9] )
    (?= [0-9a-f]* [0-9] [a-f] )
    [0-9a-f]{7,}
    | \d+
    | [a-z]+
)"""
"""Tokenizer regex with three alternatives tried left-to-right:

1. Hex hash (7+ hex chars with interleaved digits and letters) — kept
   as one token.
2. Digit sequence.
3. Letter sequence.

The 7-character floor matches ``git``'s default abbreviated hash length
(``core.abbrev``), the de facto standard on GitHub, GitLab, and
Bitbucket. The two lookaheads require both a letter-then-digit and a
digit-then-letter adjacency, ensuring at least two transitions. This
keeps real hashes (``c79e264``, ``d4173c...``) whole while still
splitting version qualifiers (``ubuntu1``, ``beta5``) and rejecting
coincidental hex strings (``eeaccee231``) that have only one transition.
"""

ALNUM_EXTRACTOR = re.compile(_ALNUM_PATTERN, re.VERBOSE)

ALNUM_EXTRACTOR_CI = re.compile(_ALNUM_PATTERN, re.VERBOSE | re.IGNORECASE)
"""Case-insensitive variant used to split the original string and preserve case."""

TOKEN_ALIASES: dict[str, str] = {
    "alpha": "a",
    "beta": "b",
    "c": "rc",
    "preview": "rc",
}
"""Canonical short forms for pre-release tag spellings.

PEP 440 defines ``alpha``/``a``, ``beta``/``b``, and ``c``/``rc``/``preview``
as equivalent aliases. These appear across ecosystems: Debian uses ``~alpha``,
npm uses ``-alpha``, Homebrew uses ``alpha``/``beta``. The long forms are
always interchangeable with the short forms, so normalizing at tokenization
time is safe. Normalization only affects comparison tokens, not the original
string or ``pretty_print()`` output.
"""

POST_RELEASE_TAGS: frozenset[str] = frozenset({"patch", "post"})
"""Suffixes that indicate a version *newer* than the base release.

PEP 440 defines ``.postN`` as a post-release. ``patch`` carries the same
semantics in some ecosystems (e.g., ``1.0-patch1``). Without this set,
the prefix-comparison rule treats all string suffixes as pre-release
indicators, which wrongly makes ``1.0 > 1.0.post1``.

This set is deliberately small. Only tags with unambiguous "newer than
release" semantics across multiple ecosystems belong here. Candidates like
``rev`` or ``p`` are excluded because they can also mean "revision" (Gentoo
``-r0``) or "pre-release patchlevel" (FreeBSD ``p1``), depending on context.
"""


class Token:
    """A normalized word, persisting its lossless integer variant.

    Supports natural comparison with ``str`` and ``int`` types.
    Used to compare versions and package IDs.
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
            msg = f"{value!r} string is not equivalent to {integer!r} integer."
            raise TypeError(msg)

        return value, integer

    def __init__(self, value: str | int) -> None:
        """Instantiates a ``Token`` from an alphanumeric string or a non-negative
        integer."""
        # Check provided value.
        if isinstance(value, str):
            if not value.isalnum():
                msg = "Only alphanumeric characters are allowed."
                raise TypeError(msg)
        elif isinstance(value, int):
            if value < 0:
                msg = "Negative integers not allowed."
                raise TypeError(msg)
        else:
            msg = "Only string and integer allowed."  # type: ignore[unreachable]
            raise TypeError(msg)

        # Parse user-value and stores its string and integer representations.
        self.string, self.integer = self.str_to_int(value)

    def __repr__(self) -> str:
        """Prints internal string and number values for debug."""
        return "<Token:{}>".format(
            ",".join(f"{k}={v!r}" for k, v in self.__dict__.items()),
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

    # Compare as integers if both can be losslessly interpreted as pure
    # integers. Otherwise fall back to string comparison. When one Token
    # is an integer and the other a pure string, the integer always sorts
    # higher: numeric version segments outrank alphabetic pre-release
    # tags (e.g., ``1 > "beta"``).

    def _match_type(self, other):
        """Returns the safe type with which we can compare the two values."""
        if self.isint:
            if isinstance(other, int):
                return int
            if isinstance(other, Token) and other.isint:
                return int
        return str

    def _mixed_type_order(self, other):
        """Return ordering hint for mixed integer/string ``Token`` pairs.

        Returns ``1`` if ``self`` should sort higher (int vs str), ``-1`` if lower
        (str vs int), or ``0`` when both are the same kind and normal comparison
        applies.
        """
        if not isinstance(other, Token):
            return 0
        if self.isint and not other.isint:
            return 1
        if not self.isint and other.isint:
            return -1
        return 0

    def __eq__(self, other):
        if self._mixed_type_order(other):
            return False
        return operator.eq(*map(self._match_type(other), [self, other]))

    def __ne__(self, other):
        if self._mixed_type_order(other):
            return True
        return operator.ne(*map(self._match_type(other), [self, other]))

    def __gt__(self, other):
        order = self._mixed_type_order(other)
        if order:
            return order > 0
        return operator.gt(*map(self._match_type(other), [self, other]))

    def __lt__(self, other):
        order = self._mixed_type_order(other)
        if order:
            return order < 0
        return operator.lt(*map(self._match_type(other), [self, other]))

    def __ge__(self, other):
        order = self._mixed_type_order(other)
        if order:
            return order > 0
        return operator.ge(*map(self._match_type(other), [self, other]))

    def __le__(self, other):
        order = self._mixed_type_order(other)
        if order:
            return order < 0
        return operator.le(*map(self._match_type(other), [self, other]))


class TokenizedString:
    """Tokenize a string for user-friendly sorting.

    Essentially a wrapper around a list of ``Token`` instances.
    """

    string: str
    tokens: tuple[Token, ...] = ()
    separators: tuple[str, ...] = ()
    original_segments: tuple[str, ...] = ()
    """Original-case token strings for lossless ``pretty_print()``."""

    def __hash__(self):
        """A ``TokenizedString`` is made unique by its original string and tuple of
        parsed tokens."""
        return hash((self.string, self.separators, self.tokens))

    def __new__(cls, value, *args, **kwargs):
        """Return same object if a ``TokenizedString`` parameter is used at
        instantiation.

        .. hint::

            If :py:meth:`object.__new__` returns an instance of ``cls``, then the new
            instance's :py:meth:`object.__init__` method will be invoked.

        .. seealso::

            An alternative would be to `merge __init__ with __new__
            <https://stackoverflow.com/a/53482003>`_.
        """
        if value is None:
            return None
        # Returns the instance as-is if of the same class. Do not reparse it.
        if value and isinstance(value, TokenizedString):
            return value
        # Create a brand new instance. __init__() will be auto-magiccaly called
        # after that.
        return super().__new__(cls)

    def __init__(self, value: str | int) -> None:
        """Parse and tokenize the provided raw ``value``."""
        if isinstance(value, TokenizedString):
            # Skip initialization for instance of the class, as this __init__() gets
            # called auto-magiccaly eveytime the __new__() method above returns a
            # TokenizedString instance.
            return
        # Our canonical __init__() starts here.
        if isinstance(value, int):
            self.string = str(value)
        elif isinstance(value, str):
            self.string = value.strip()
        else:
            msg = f"{type(value)} not supported"  # type: ignore[unreachable]
            raise TypeError(msg)
        self.tokens, self.separators, self.original_segments = self.tokenize(
            self.string,
        )

    def __deepcopy__(self, memo):
        """Generic recursive deep copy of the current instance.

        This is required to make the :py:meth:`copy.deepcopy` called within
        :py:meth:`dataclasses.asdict` working, because the defaults implementation
        doesn't know how to handle the ``value`` parameter provided in the
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
        """Reconstruct the tokenized string using original-case segments and
        separators."""
        parts: list[str] = []
        for i, segment in enumerate(self.original_segments):
            parts.append(segment)
            if i < len(self.separators):
                parts.append(self.separators[i])
        return "".join(parts)

    @staticmethod
    def tokenize(
        string: str,
    ) -> tuple[tuple[Token, ...], tuple[str, ...], tuple[str, ...]]:
        """Tokenize a string: ignore case and split at each non-alphanumeric characters.

        Returns a tuple of ``Token`` instances, separator strings between consecutive
        tokens, and original-case segment strings for lossless display.

        ``re.split()`` with a capturing group alternates non-matching segments (even
        indices) and captured matches (odd indices)::

            ALNUM_EXTRACTOR.split("4.2.1-5666.3")
            ['', '4', '.', '2', '.', '1', '-', '5666', '.', '3', '']
             pre   m   sep   m   sep   m   sep    m     sep   m   suf
        """
        normalized_str = strutils.asciify(string).lower().decode()
        parts = ALNUM_EXTRACTOR.split(normalized_str)

        # Normalize well-known pre-release aliases to their canonical short
        # form so that ``1.0alpha1`` and ``1.0a1`` compare equal. The
        # replacement happens on the lowered split parts, before Token
        # creation. original_segments (used by pretty_print) are unaffected.
        tokens = tuple(
            Token(TOKEN_ALIASES.get(parts[i], parts[i]))
            for i in range(1, len(parts), 2)
        )
        separators = tuple(parts[i] for i in range(2, len(parts) - 1, 2))

        # Extract original-case segments for pretty_print(). When the input
        # is already ASCII lowercase (the common case), the normalized split
        # is identical and we skip the second regex.
        if normalized_str == string:
            orig_segments = tuple(parts[i] for i in range(1, len(parts), 2))
        else:
            orig_parts = ALNUM_EXTRACTOR_CI.split(string)
            orig_segments = tuple(orig_parts[i] for i in range(1, len(orig_parts), 2))
            # Asciify changed the split structure: fall back to normalized.
            if len(orig_segments) != len(tokens):
                orig_segments = tuple(str(t) for t in tokens)

        return tokens, separators, orig_segments

    # TokenizedString comparison delegates to Token tuples, giving natural
    # sort order: (2019, 0, 1) > (9, 3) — something neither pure-string
    # nor pure-integer tuple comparison achieves.

    def __iter__(self):
        """``TokenizedString`` are essentially a wrapper around a tuple of ``Token``
        objects."""
        return iter(self.tokens)

    @staticmethod
    def _strip_v(tokens: tuple[Token, ...]) -> tuple[Token, ...]:
        """Strip a cosmetic ``v`` prefix for comparison.

        The ``v`` prefix is a universal convention (git tags, Go modules,
        semver tooling) that carries no version semantics. A bare ``"v"``
        token immediately followed by an integer token (e.g., ``v1.0``)
        is always cosmetic. We only strip when the next token is an
        integer to avoid touching strings like ``"voodoo"`` or a lone
        ``"v"`` token.
        """
        if len(tokens) >= 2 and tokens[0].string == "v" and tokens[1].isint:
            return tokens[1:]
        return tokens

    @staticmethod
    def _compare_tuples(
        a: tuple[Token, ...],
        b: tuple[Token, ...],
    ) -> int:
        """Compare two token tuples with version-aware semantics.

        Returns ``-1``, ``0``, or ``1``.

        When one tuple is a prefix of the other, the first *significant* (non-zero)
        extra token in the longer tuple decides the outcome:

        - **Post-release tag** (``post``, ``patch``): the longer tuple is greater.
        - **Other string token** (pre-release tag): the shorter tuple is greater.
        - **Integer token** (additional version component): the longer tuple is greater.
        - **All trailing zeros**: the tuples are equal (trailing ``.0`` is padding).
        """
        # Strip cosmetic ``v`` prefix before comparison so that
        # ``v1.0`` and ``1.0`` compare equal.
        a = TokenizedString._strip_v(a)
        b = TokenizedString._strip_v(b)

        for ta, tb in zip(a, b):
            if ta > tb:
                return 1
            if ta < tb:
                return -1

        if len(a) == len(b):
            return 0

        # One tuple is a prefix of the other. Find the first non-zero
        # extra token to decide the outcome.
        shorter_len = min(len(a), len(b))
        longer = b if len(a) < len(b) else a
        first_significant = next(
            (t for t in longer[shorter_len:] if not (t.isint and t.integer == 0)),
            None,
        )

        if first_significant is None:
            return 0

        if first_significant.isint:
            # Additional numeric component: longer version is greater.
            longer_wins = 1
        elif first_significant.string in POST_RELEASE_TAGS:
            # Post-release suffix (e.g., ``post``, ``patch``): the
            # longer version is a post-release of the shorter, so
            # longer is greater. Without this, all string suffixes
            # would be treated as pre-release indicators.
            longer_wins = 1
        else:
            # Pre-release suffix (e.g., ``alpha``, ``beta``, ``rc``,
            # ``dev``, ``git``): the shorter version is the actual
            # release, so shorter is greater.
            longer_wins = -1
        return -longer_wins if len(a) < len(b) else longer_wins

    def __eq__(self, other):
        if other is None:
            return False
        if isinstance(other, TokenizedString):
            return self._compare_tuples(self.tokens, other.tokens) == 0
        if isinstance(other, tuple):
            return tuple(self) == tuple(other)
        return super().__eq__(other)

    def __ne__(self, other):
        if other is None:
            return True
        if isinstance(other, TokenizedString):
            return self._compare_tuples(self.tokens, other.tokens) != 0
        return super().__ne__(other)

    def __gt__(self, other):
        if other is None:
            return True
        if isinstance(other, TokenizedString):
            return self._compare_tuples(self.tokens, other.tokens) > 0
        return NotImplemented

    def __lt__(self, other):
        if other is None:
            return False
        if isinstance(other, TokenizedString):
            return self._compare_tuples(self.tokens, other.tokens) < 0
        return NotImplemented

    def __ge__(self, other):
        if other is None:
            return True
        if isinstance(other, TokenizedString):
            return self._compare_tuples(self.tokens, other.tokens) >= 0
        return NotImplemented

    def __le__(self, other):
        if other is None:
            return False
        if isinstance(other, TokenizedString):
            return self._compare_tuples(self.tokens, other.tokens) <= 0
        return NotImplemented


parse_version = TokenizedString
"""Alias for ``TokenizedString`` used in version-comparison contexts."""


RANGE_OPERATOR = re.compile(r"(?P<op>[><=!]=?|!=)\s*(?P<version>.+)")
"""Matches a comparison operator prefix followed by a version string."""

OPERATOR_MAP: dict[str, Callable[[TokenizedString, TokenizedString], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


class VersionRange:
    """A set of version constraints parsed from a comma-separated specifier string.

    Each constraint is an ``(operator, version)`` pair. A version satisfies the
    range only if it satisfies every constraint.

    Bare version strings (no operator prefix) are treated as ``>=``.
    """

    def __init__(self, spec: str) -> None:
        self.spec = spec
        self.constraints = tuple(self._parse(spec))

    @staticmethod
    def _parse(
        spec: str,
    ) -> Iterator[
        tuple[Callable[[TokenizedString, TokenizedString], bool], TokenizedString]
    ]:
        """Yield ``(operator, version)`` pairs from a comma-separated specifier."""
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            match = RANGE_OPERATOR.fullmatch(part)
            if match:
                op = OPERATOR_MAP[match.group("op")]
                version = parse_version(match.group("version"))
            else:
                # Bare version string is treated as >=.
                op = operator.ge
                version = parse_version(part)
            yield op, version

    def __contains__(self, version: TokenizedString) -> bool:
        """Return ``True`` if *version* satisfies all constraints."""
        return all(op(version, ver) for op, ver in self.constraints)

    def __repr__(self) -> str:
        return f"<VersionRange {self.spec!r}>"


def is_version(string: str) -> bool:
    """Returns ``True`` if the string looks like a version.

    Heuristics: at least one token is an integer, or there is only one
    non-integer token.
    """
    version = parse_version(string)

    # At least one of the token is an integer.
    if any(token.integer is not None for token in version):
        return True

    # There is only one non-integer token.
    return len(version.tokens) == 1


def diff_versions(
    old: str | TokenizedString,
    new: str | TokenizedString,
) -> tuple[str, str]:
    """Color the common prefix gray, the old suffix red, the new suffix green.

    The split point snaps to the nearest separator boundary so the full
    diverging token and its preceding separator are highlighted. For
    ``2.1.1774638290`` vs ``2.1.1774896198``, the common part is ``2.1``
    and the diff includes ``.1774638290`` / ``.1774896198``.
    """
    old = str(old)
    new = str(new)

    # Longest common character prefix.
    common = 0
    for a, b in zip(old, new):
        if a != b:
            break
        common += 1

    # Snap back to a separator boundary when the strings actually differ.
    if common and common < max(len(old), len(new)):
        snap = common
        # Walk back past the partial alnum token.
        while snap > 0 and old[snap - 1].isalnum():
            snap -= 1
        # Walk back past the separator itself.
        while snap > 0 and not old[snap - 1].isalnum():
            snap -= 1
        common = snap

    prefix = style(old[:common], fg="bright_black") if common else ""
    return (
        prefix + style(old[common:], fg="red") if old else "",
        prefix + style(new[common:], fg="green") if new else "",
    )
