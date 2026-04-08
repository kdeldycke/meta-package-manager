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

from __future__ import annotations

import copy
import operator
import re

import pytest

from meta_package_manager.version import (
    Token,
    TokenizedString,
    VersionRange,
    diff_versions,
    is_version,
    parse_version,
)


def reverse_fixtures(table):
    """Utility method to reverse a tuple of tuples."""
    return tuple(map(tuple, map(reversed, table)))


@pytest.mark.parametrize("value", [0, 123, "0", "123", "abc", "ABC", "123abc"])
def test_token_allowed_instantiation(value):
    Token(value)


@pytest.mark.parametrize("value", [None, -1, "a-b-c", 1.0, True, False])
def test_token_unauthorized_instantiation(value):
    with pytest.raises(TypeError):
        Token(value)


eq_values = [
    (Token("2345"), Token("2345")),
    (Token("2345"), Token(2345)),
    (Token("02345"), Token(2345)),
    (Token("02345"), "02345"),
    (Token("2345"), 2345),
    (Token("2345"), "2345"),
    (Token("0"), "0"),
    (Token("0"), 0),
    (Token("000"), 0),
    (Token("abc"), "abc"),
    (Token("abc"), Token("abc")),
]


ne_values = [
    (Token("2345"), Token("45")),
    (Token("2345"), Token(45)),
    (Token("2345"), Token(0)),
    (Token("2345"), Token("0")),
    (Token("2"), -2),
    (Token("2"), 0),
    (Token("abc"), "def"),
    (Token("Z"), "z"),
    (Token("acb"), 123),
    # Mixed int/string tokens are never equal.
    (Token(0), Token("a")),
    (Token("beta"), Token(1)),
]


gt_values = [
    (Token("9999"), Token("12")),
    (Token("9999"), Token("000000099")),
    (Token(9999), Token("12")),
    (Token(9999), Token(12)),
    (Token(9999), "0"),
    (Token(9999), 0),
    (Token(0), -2),
    (Token("0"), -2),
    (Token("abc"), -2),
    (Token("abc"), "ab"),
    (Token("a"), "Z"),
    (Token("z"), "Z"),
    (Token("a"), Token("Z")),
    # Integer tokens always sort higher than string tokens.
    (Token(0), Token("z")),
    (Token(1), Token("beta")),
    (Token(42), Token("rc")),
]


lt_values = [
    (Token("12"), Token("9999")),
    (Token("0000012"), Token("9999")),
    (Token("12"), Token(9999)),
    (Token(12), Token(9999)),
    (Token("12"), 9999),
    (Token("0"), 9999),
    (Token("ab"), "abc"),
    (Token("Z"), "z"),
    # String tokens always sort lower than integer tokens.
    (Token("z"), Token(0)),
    (Token("beta"), Token(1)),
    (Token("rc"), Token(42)),
]


@pytest.mark.parametrize(("token", "value"), eq_values)
def test_token_eq(token, value):
    assert token == value


@pytest.mark.parametrize(("token", "value"), ne_values)
def test_token_ne(token, value):
    assert token != value


@pytest.mark.parametrize(("token", "value"), gt_values)
def test_token_gt(token, value):
    assert token > value


@pytest.mark.parametrize(("token", "value"), lt_values)
def test_token_lt(token, value):
    assert token < value


@pytest.mark.parametrize(("token", "value"), gt_values + eq_values)
def test_token_ge(token, value):
    assert token >= value


@pytest.mark.parametrize(("token", "value"), lt_values + eq_values)
def test_token_le(token, value):
    assert token <= value


def test_token_hash():
    assert hash(Token("9999")) == hash(Token("9999"))
    assert hash(Token("9999")) == hash(Token(9999))
    assert hash(Token(9999)) == hash(Token(9999))
    assert hash(Token("09999")) != hash(Token("9999"))
    assert hash(Token("09999")) != hash(Token(9999))


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (0, "0"),
        (123, "123"),
        ("abc", "abc"),
        ("ABC", "ABC"),
        ("0042", "0042"),
    ),
)
def test_token_str(value, expected):
    assert str(Token(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (0, 1),
        (123, 3),
        ("abc", 3),
        ("0042", 4),
        ("a", 1),
    ),
)
def test_token_len(value, expected):
    assert len(Token(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (0, 0),
        (123, 123),
        ("42", 42),
        ("0042", 42),
    ),
)
def test_token_int(value, expected):
    assert int(Token(value)) == expected  # type: ignore[call-overload]


@pytest.mark.parametrize("value", ("abc", "ABC", "123abc"))
def test_token_int_none_for_non_integers(value):
    """``Token.integer`` is ``None`` for non-integer tokens."""
    assert Token(value).integer is None


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (0, True),
        (123, True),
        ("42", True),
        ("0042", True),
        ("abc", False),
        ("ABC", False),
        ("123abc", False),
    ),
)
def test_token_isint(value, expected):
    assert Token(value).isint is expected


def test_token_repr():
    r = repr(Token(42))
    assert "Token" in r
    assert "42" in r


def test_token_format():
    assert f"{Token('abc'):>10}" == "       abc"
    assert f"{Token(42):>10}" == "        42"


def test_token_mixed_type_not_equal():
    """Integer and string tokens are never equal, even if the string is
    digit-like when compared cross-type."""
    assert Token(0) != Token("a")
    assert Token("beta") != Token(1)


@pytest.mark.parametrize(
    "value",
    (None, 0, 123, -1, "0", "1.2.3", "abc", "A-B-C", "123   a bc \n"),
)
def test_tokenized_string_allowed_instantiation(value):
    TokenizedString(value)


@pytest.mark.parametrize(
    "value",
    (1.0, [1, 2, 3], (1, 2, 3), {1, 2, 3}, {"a": 1, "b": 2}),
)
def test_tokenized_string_unauthorized_instantiation(value):
    with pytest.raises(TypeError):
        TokenizedString(value)


def test_tokenized_string_hash():
    assert hash(TokenizedString("1.2.3")) == hash(TokenizedString("1.2.3"))
    assert hash(TokenizedString(9999)) == hash(TokenizedString(9999))
    assert hash(TokenizedString("9999")) == hash(TokenizedString(9999))
    assert hash(TokenizedString("09999")) != hash(TokenizedString("9999"))
    assert hash(TokenizedString("09999")) != hash(TokenizedString(9999))
    # Different separators produce different hashes.
    assert hash(TokenizedString("1.2.3")) != hash(TokenizedString("1-2-3"))
    assert hash(TokenizedString("1.2.3")) != hash(TokenizedString("1_2_3"))


def test_tokenized_string_noop_instantiation():
    assert TokenizedString(None) is None  # type: ignore[arg-type]


def test_tokenized_string_idempotent_instantiation():
    tok1 = TokenizedString("1.2.3")
    tok2 = TokenizedString(tok1)  # type: ignore[arg-type]
    assert tok1 is tok2
    assert hash(tok1) == hash(tok2)
    assert tok1 == tok2


def test_tokenized_string_deepcopy():
    tok1 = TokenizedString("4.2.1-5666.3")
    tok2 = copy.deepcopy(tok1)
    assert tok1 is not tok2
    assert hash(tok1) == hash(tok2)
    assert tok1 == tok2
    assert tok1.separators == tok2.separators
    assert tok1.pretty_print() == tok2.pretty_print()


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("1.2.3", "1.2.3"),
        (" 1.2.3 ", "1.2.3"),
        (42, "42"),
        ("latest", "latest"),
    ),
)
def test_tokenized_string_str(value, expected):
    assert str(TokenizedString(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("1.2.3", 5),
        ("latest", 6),
        (42, 2),
        ("", 0),
    ),
)
def test_tokenized_string_len(value, expected):
    assert len(TokenizedString(value)) == expected


def test_tokenized_string_repr():
    r = repr(TokenizedString("1.2.3"))
    assert "TokenizedString" in r
    assert "1.2.3" in r


def test_tokenized_string_format():
    assert f"{TokenizedString('1.2.3'):>10}" == "     1.2.3"


def test_tokenized_string_iter():
    tokens = list(TokenizedString("1.2.3"))
    assert len(tokens) == 3
    assert all(isinstance(t, Token) for t in tokens)
    assert [str(t) for t in tokens] == ["1", "2", "3"]


def test_tokenized_string_from_integer():
    t = TokenizedString(42)
    assert t.tokens == (Token(42),)
    assert t.separators == ()
    assert str(t) == "42"


@pytest.mark.parametrize("value", ("", "...", "---", "___"))
def test_tokenized_string_empty_tokens(value):
    t = TokenizedString(value)
    assert t.tokens == ()
    assert t.separators == ()


def test_tokenized_string_comparison_edge_cases():
    """Comparison with ``None`` and unsupported types."""
    v = TokenizedString("1.0")
    # None is handled explicitly by every operator.
    assert v > None
    assert v >= None
    assert not (v < None)
    assert not (v <= None)
    assert v.__eq__(None) is False
    assert v.__ne__(None) is True
    # Unsupported types: __eq__/__ne__ fall back to identity.
    assert v != "1.0"
    assert v != "1.0"
    assert v != 42
    assert v != 42
    # Ordering operators raise TypeError for unsupported types.
    for op in (operator.gt, operator.lt, operator.ge, operator.le):
        with pytest.raises(TypeError):
            op(v, "1.0")


@pytest.mark.parametrize(
    ("v_string", "expected_seps"),
    (
        # Single token: no separators.
        ("latest", ()),
        ("42", ()),
        # Dot-separated.
        ("1.2.3", (".", ".")),
        ("0.0.0", (".", ".")),
        # Dash-separated.
        ("1-2-3", ("-", "-")),
        # Underscore-separated.
        ("1_2_3", ("_", "_")),
        # Mixed separators.
        ("4.2.1-5666.3", (".", ".", "-", ".")),
        ("1.3_1", (".", "_")),
        # Implicit separators at digit-letter boundaries.
        ("1.2beta5", (".", "", "")),
        ("r2917_1", ("", "_")),
        ("20190718-r0", ("-", "")),
        ("v0.9.4.3", ("", ".", ".", ".")),
        # Double/adjacent separators stored verbatim.
        ("4.2.1-5666..3", (".", ".", "-", "..")),
        ("4.2.1--5666.3", (".", ".", "--", ".")),
        # Plus separator (Gentoo/OpenWrt epochs).
        ("4.6.0+git+20160126-2", (".", ".", "+", "+", "-")),
        # Colon separator (Debian epochs).
        ("1:5.25-2ubuntu1", (":", ".", "-", "", "")),
        # Space separator.
        ("1 2 3", (" ", " ")),
        # Leading zeros preserved in pretty_print tokens.
        ("2020.03.24", (".", ".")),
        ("2.40.20161221.0239", (".", ".", ".")),
        # Empty string.
        ("", ()),
        # Original case preserved in pretty_print.
        ("4.2.1-ABC-5666.3", (".", ".", "-", "-", ".")),
        ("V0.9.4.3", ("", ".", ".", ".")),
    ),
)
def test_tokenized_string_separators_and_pretty_print(v_string, expected_seps):
    t = TokenizedString(v_string)
    assert t.separators == expected_seps
    assert t.pretty_print() == v_string


@pytest.mark.parametrize(
    ("v_string", "expected_seps", "expected_pp"),
    (
        # Leading separator is prefix in split, not stored.
        (".4.2.1", (".", "."), "4.2.1"),
        # Trailing separator is suffix in split, not stored.
        ("4.2.1.", (".", "."), "4.2.1"),
    ),
)
def test_tokenized_string_separators_and_lossy_pretty_print(
    v_string, expected_seps, expected_pp
):
    t = TokenizedString(v_string)
    assert t.separators == expected_seps
    assert t.pretty_print() == expected_pp


version_list = (
    ("r2917_1", ("r", 2917, 1)),
    (" r     29   \n  17   1 x  ", ("r", 29, 17, 1, "x")),
    ("2020.03.24", (2020, 3, 24)),
    ("4.2.1-5666.3", (4, 2, 1, 5666, 3)),
    ("4.2.1-5666..3", (4, 2, 1, 5666, 3)),
    ("4.2.1-5666.3.", (4, 2, 1, 5666, 3)),
    (".4.2.1-5666.3", (4, 2, 1, 5666, 3)),
    ("4.2.1--5666.3", (4, 2, 1, 5666, 3)),
    ("4.2.1-#-5666.3", (4, 2, 1, 5666, 3)),
    ("4.2.1-ABC-5666.3", (4, 2, 1, "abc", 5666, 3)),
    (
        "4.2.1-éèàçÇÉÈ²³¼ÀÁÂÃÄ—ÅËÍÑÒÖÜÝåïš™-5666.3",
        (4, 2, 1, "eeaccee", 231, 4, "aaaaae", "ainooeueyastm", 5666, 3),
    ),
    ("1.3_1", (1, 3, 1)),
    ("2.40.20161221.0239", (2, 40, 20161221, 239)),
    ("latest", ("latest",)),
    ("1.2beta5", (1, 2, "b", 5)),
    ("2.8.18-x86_64", (2, 8, 18, "x", 86, 64)),
    ("1.8.0_112-b16", (1, 8, 0, 112, "b", 16)),
    ("3.6.9_build_4685", (3, 6, 9, "build", 4685)),
    ("1.8.6-124-g6cd4c31", (1, 8, 6, 124, "g", "6cd4c31")),
    ("0.9999999", (0, 9999999)),
    ("0.0.0", (0, 0, 0)),
    ("1.0+git71+c79e264-r0", (1, 0, "git", 71, "c79e264", "r", 0)),
    ("20190718-r0", (20190718, "r", 0)),
    ("0.0.0-development", (0, 0, 0, "development")),
    ("v0.9.4.3", ("v", 0, 9, 4, 3)),
    ("6.0.1-0ubuntu1", (6, 0, 1, 0, "ubuntu", 1)),
    ("4.6.0+git+20160126-2", (4, 6, 0, "git", 20160126, 2)),
    ("1:5.25-2ubuntu1", (1, 5, 25, 2, "ubuntu", 1)),
    ("1.18.4ubuntu1.1", (1, 18, 4, "ubuntu", 1, 1)),
    ("20160104ubuntu1", (20160104, "ubuntu", 1)),
    ("3.113+nmu3ubuntu4", (3, 113, "nmu", 3, "ubuntu", 4)),
    (
        "13.0.2,8:d4173c853231432f001e99d882",
        (13, 0, 2, 8, "d4173c853231432f001e99d882"),
    ),
    ("1.01+20150706hgc3698e0+dfsg-2", (1, 1, 20150706, "hgc", 3698, "e", 0, "dfsg", 2)),
    # PEP 440 pre-release tags.
    ("1.0a1", (1, 0, "a", 1)),
    ("1.0rc1", (1, 0, "rc", 1)),
    ("1.0.post1", (1, 0, "post", 1)),
    ("1.0.dev456", (1, 0, "dev", 456)),
    # Calendar versioning.
    ("2024.1.15", (2024, 1, 15)),
    ("24.04", (24, 4)),
    # Long version chain.
    ("1.2.3.4.5.6.7.8.9.10", (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)),
    # Single digit.
    ("0", (0,)),
    ("9", (9,)),
    # Java build metadata.
    ("21.0.2+13", (21, 0, 2, 13)),
    # Linux kernel style.
    ("6.5.0-44-generic", (6, 5, 0, 44, "generic")),
    # Windows four-part version.
    ("10.0.19045.4529", (10, 0, 19045, 4529)),
    # Debian tilde separator.
    ("1.2.3~beta1", (1, 2, 3, "b", 1)),
    # Git describe output.
    ("v2.42.0-rc2-3-gabcdef1", ("v", 2, 42, 0, "rc", 2, 3, "gabcdef", 1)),
    # Large single number.
    ("99999999999999999", (99999999999999999,)),
    # Node.js semver.
    ("18.17.1", (18, 17, 1)),
    # Arch Linux pkgrel.
    ("5.15.90.1-2", (5, 15, 90, 1, 2)),
    # Snap revision style.
    ("2.60.4+git2.e7f88a7", (2, 60, 4, "git", 2, "e7f88a7")),
    # PEP 440 epoch — the ``!`` is a plain separator, epoch semantics lost.
    ("1!1.0", (1, 1, 0)),
    # PEP 440 local version — ``+`` is a plain separator.
    ("1.0+local", (1, 0, "local")),
    # Semver build metadata — ``+`` is a plain separator.
    ("1.0.0+build.123", (1, 0, 0, "build", 123)),
    # Semver pre-release with mixed identifiers.
    ("1.0.0-alpha.beta", (1, 0, 0, "a", "b")),
    # RPM release tag.
    ("1.0-1.fc38", (1, 0, 1, "fc", 38)),
    # Go pseudo-version.
    (
        "v0.0.0-20210101000000-abcdef123456",
        ("v", 0, 0, 0, 20210101000000, "abcdef", 123456),
    ),
)


@pytest.mark.parametrize(("v_string", "v_tuple"), version_list)
def test_version_tokenizer(v_string, v_tuple):
    assert TokenizedString(v_string) == v_tuple


@pytest.mark.parametrize(
    ("v_string", "expected"),
    (
        # Strings recognized as versions.
        *((v_string, True) for v_string, _ in version_list),
        # Not recognized as versions.
        ("left-pad", False),
        ("@eslint/json", False),
        ("my-package-name", False),
        ("foo_bar_baz", False),
        ("some-lib", False),
    ),
)
def test_is_version(v_string, expected):
    assert is_version(v_string) is expected


compared_gt = (
    ("1", None),
    ("2.0", "1.0"),
    ("0.1", "0"),
    ("0.1", "0.0"),
    ("0.1", "0.0.0.0.0"),
    ("0.1", "0.beta2"),
    ("2.0", "1"),
    ("3.1.10", "3.1.9"),
    ("9.52", "9d"),
    ("8.2p1_1", "8.2p1"),
    ("3.12.0a4", "3.7.0"),
    ("3.12.0", "3.12.0a4"),
    ("3.7.7", "3.7-beta2_1"),
    ("2.1.1", "2.1.1-git-23hfb2-foobar"),
    (20200313, 20190801),
    ("2020.03.24", "2019.11.28"),
    # Java version with build metadata hash — the comma/colon structure gets
    # tokenized into meaningless fragments. Would need format-specific parsing.
    # ("14.0.1,7:664493ef4a6946b186ff29eb326336a2",
    #  "14,36:076bab302c7b4508975440c56f6cc26a"),
    # Major version dominates even when minor/patch are larger.
    ("10.0.0", "9.99.99"),
    # Long version chain with trailing difference.
    ("1.0.0.0.0.1", "1.0.0.0.0.0"),
    # Single-segment integer comparison, not lexicographic.
    ("10", "9"),
    # Integer input.
    (20240101, 20231231),
    # Semver patch bump.
    ("1.0.1", "1.0.0"),
    # Calendar versioning.
    ("2024.1.15", "2023.12.31"),
    # Pre-release with higher base version.
    ("3.12.1", "3.12.0a4"),
    # Linux kernel versions.
    ("6.5.0", "5.15.90"),
    # PEP 440 post-release > release.
    ("1.0.post1", "1.0"),
    # PEP 440 pre-release chain: alpha < beta < rc < release.
    ("1.0b1", "1.0a1"),
    ("1.0rc1", "1.0b1"),
    ("1.0", "1.0rc1"),
    # PEP 440 dev within pre-release: release > dev.
    ("1.0a1", "1.0a1.dev1"),
    # Semver pre-release numeric ordering.
    ("1.0.0-alpha.2", "1.0.0-alpha.1"),
    # Semver more identifiers > fewer (longer is more specific).
    ("1.0.0-alpha.1", "1.0.0-alpha"),
    # RPM release bump.
    ("1.0-2.fc38", "1.0-1.fc38"),
    # Git describe commit count.
    ("1.8.6-125-g6cd4c31", "1.8.6-124-g6cd4c31"),
    # Go pseudo-version date comparison.
    (
        "v0.0.0-20210101000000-abcdef123456",
        "v0.0.0-20200101000000-abcdef123456",
    ),
)


@pytest.mark.parametrize(("ver1", "ver2"), compared_gt)
def test_version_comparison_gt(ver1, ver2):
    assert TokenizedString(ver1) > TokenizedString(ver2)


@pytest.mark.parametrize(("ver1", "ver2"), reverse_fixtures(compared_gt))
def test_version_comparison_lt(ver1, ver2):
    assert TokenizedString(ver1) < TokenizedString(ver2)


compared_eq = (
    # Identical strings.
    ("1.2.3", "1.2.3"),
    ("0", "0"),
    ("latest", "latest"),
    # Leading zeros: tokens compare as integers.
    ("01.02.03", "1.2.3"),
    ("2020.03.24", "2020.3.24"),
    # Trailing .0 is padding.
    ("6.2", "6.2.0"),
    ("1.0", "1.0.0.0.0"),
    # Different separators: comparison is token-based.
    ("1.2.3", "1-2-3"),
    ("1.2.3", "1_2_3"),
    ("4.2.1", "4-2-1"),
    # PEP 440 implicit zero on pre-release tag.
    ("1.0a", "1.0a0"),
    # Cosmetic ``v`` prefix ignored in comparison.
    ("v1.0", "1.0"),
    ("v0.9.4.3", "0.9.4.3"),
    # PEP 440 alias normalization.
    ("1.0alpha1", "1.0a1"),
    ("1.0c1", "1.0rc1"),
)


@pytest.mark.parametrize(("ver1", "ver2"), compared_eq)
def test_version_comparison_eq(ver1, ver2):
    assert TokenizedString(ver1) == TokenizedString(ver2)
    assert TokenizedString(ver1) == TokenizedString(ver2)
    assert TokenizedString(ver1) >= TokenizedString(ver2)
    assert TokenizedString(ver1) <= TokenizedString(ver2)
    assert not (TokenizedString(ver1) > TokenizedString(ver2))
    assert not (TokenizedString(ver1) < TokenizedString(ver2))


@pytest.mark.parametrize(
    "sequence",
    (
        [
            None,
            "r0",
            "r1",
            "r9_0",
            "r9_3",
            "r9_30",
            "r2917_1",
            "r02918_1",
            "r02920_0",
            "r02920_1",
            "r02920_20",
            "r02920_021",
        ],
        # Semver progression.
        [
            None,
            "0.1.0",
            "0.2.0",
            "0.10.0",
            "1.0.0",
            "1.0.1",
            "1.1.0",
            "1.10.0",
            "2.0.0",
            "10.0.0",
        ],
        # PEP 440 pre-release progression.
        [
            None,
            "1.0a1",
            "1.0a2",
            "1.0b1",
            "1.0rc1",
            "1.0",
            "1.0.1",
            "1.1",
            "2.0",
        ],
        # Calendar versioning progression.
        [
            None,
            "2019.11.28",
            "2020.03.24",
            "2020.12.01",
            "2024.1.15",
        ],
    ),
)
def test_version_sorting(sequence):
    sorted_version = list(map(TokenizedString, sequence))
    # Reverse to guarantee a different order from sorted (deterministic, no flakiness).
    reversed_order = list(reversed(sorted_version))
    assert sorted(reversed_order) == sorted_version


@pytest.mark.parametrize(
    ("spec", "version", "expected"),
    (
        # Bare version string acts as >=.
        ("1.0.0", "1.0.0", True),
        ("1.0.0", "2.0.0", True),
        ("1.0.0", "0.9.0", False),
        # Explicit >= operator.
        (">=1.0.0", "1.0.0", True),
        (">=1.0.0", "2.0.0", True),
        (">=1.0.0", "0.9.0", False),
        # Explicit > operator.
        (">1.0.0", "1.0.1", True),
        (">1.0.0", "1.0.0", False),
        # Explicit < operator.
        ("<2.0.0", "1.9.9", True),
        ("<2.0.0", "2.0.0", False),
        ("<2.0.0", "3.0.0", False),
        # Explicit <= operator.
        ("<=2.0.0", "2.0.0", True),
        ("<=2.0.0", "2.0.1", False),
        # Explicit == operator.
        ("==1.5.0", "1.5.0", True),
        ("==1.5.0", "1.5.1", False),
        # Explicit != operator.
        ("!=1.5.0", "1.5.0", False),
        ("!=1.5.0", "1.5.1", True),
        # Range with two constraints.
        (">=1.20.0,<2.0.0", "1.20.0", True),
        (">=1.20.0,<2.0.0", "1.22.19", True),
        (">=1.20.0,<2.0.0", "1.19.0", False),
        (">=1.20.0,<2.0.0", "2.0.0", False),
        (">=1.20.0,<2.0.0", "4.9.2", False),
        # Range with spaces around constraints.
        (">=1.0.0 , <3.0.0", "2.0.0", True),
        (">=1.0.0 , <3.0.0", "0.5.0", False),
        # Empty constraint parts are silently ignored.
        (",1.0.0,", "1.0.0", True),
        (",1.0.0,", "0.9.0", False),
        # Three constraints (range with exclusion).
        (">=1.0.0,<3.0.0,!=2.0.0", "1.5.0", True),
        (">=1.0.0,<3.0.0,!=2.0.0", "2.0.0", False),
        (">=1.0.0,<3.0.0,!=2.0.0", "0.5.0", False),
        # Tight pinning: lower == upper.
        (">=1.5.0,<=1.5.0", "1.5.0", True),
        (">=1.5.0,<=1.5.0", "1.5.1", False),
        # Single > boundary.
        (">0", "0.0.1", True),
        (">0", "0", False),
    ),
)
def test_version_range(spec, version, expected):
    assert (parse_version(version) in VersionRange(spec)) is expected


def test_version_range_empty_spec():
    """Empty spec has no constraints, so any version satisfies it."""
    r = VersionRange("")
    assert parse_version("1.0.0") in r
    assert parse_version("0") in r


@pytest.mark.parametrize(
    ("spec", "expected"),
    (
        (">=1.0.0,<2.0.0", "<VersionRange '>=1.0.0,<2.0.0'>"),
        ("1.0.0", "<VersionRange '1.0.0'>"),
    ),
)
def test_version_range_repr(spec, expected):
    assert repr(VersionRange(spec)) == expected


def test_parse_version_is_tokenized_string():
    """``parse_version`` is an alias for ``TokenizedString``."""
    assert parse_version is TokenizedString
    v = parse_version("1.2.3")
    assert isinstance(v, TokenizedString)
    assert v == TokenizedString("1.2.3")


def _strip_ansi(s: str) -> str:
    """Remove ANSI escape codes, returning plain text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


@pytest.mark.parametrize(
    ("old", "new", "expected_common", "expected_old", "expected_new"),
    (
        # Token boundary: diff includes separator + full diverging token.
        ("2.1.1774638290", "2.1.1774896198", "2.1", ".1774638290", ".1774896198"),
        # Patch bump.
        ("1.2.3", "1.2.4", "1.2", ".3", ".4"),
        # Minor bump.
        ("1.2.3", "1.3.0", "1", ".2.3", ".3.0"),
        # Major bump: no separator before first token.
        ("1.2.3", "2.0.0", "", "1.2.3", "2.0.0"),
        # Pre-release tag change.
        ("1.0.0-alpha", "1.0.0-beta", "1.0.0", "-alpha", "-beta"),
        # Year-based: first token differs, no common separator.
        ("2013.0523", "2024.0010", "", "2013.0523", "2024.0010"),
        # No common prefix at all.
        ("abc", "def", "", "abc", "def"),
        # No separators in either string.
        ("12345", "12399", "", "12345", "12399"),
        # Identical versions: everything is common.
        ("1.2.3", "1.2.3", "1.2.3", "", ""),
        # One side empty.
        ("", "1.0", "", "", "1.0"),
        ("1.0", "", "", "1.0", ""),
        # Both empty.
        ("", "", "", "", ""),
        # Alpha bump within pre-release.
        ("3.12.0a4", "3.12.0a5", "3.12", ".0a4", ".0a5"),
        # TokenizedString inputs.
        (TokenizedString("1.2.3"), TokenizedString("1.2.4"), "1.2", ".3", ".4"),
    ),
)
def test_diff_versions(old, new, expected_common, expected_old, expected_new):
    styled_old, styled_new = diff_versions(old, new)

    # Plain text must equal the full original string.
    assert _strip_ansi(styled_old) == (str(old) if old else "")
    assert _strip_ansi(styled_new) == (str(new) if new else "")

    # Verify the split point.
    full_old = str(old) if old else ""
    full_new = str(new) if new else ""
    assert full_old[: len(expected_common)] == expected_common
    assert full_old[len(expected_common) :] == expected_old
    assert full_new[: len(expected_common)] == expected_common
    assert full_new[len(expected_common) :] == expected_new


# --- Known limitations ---
#
# These tests document comparisons that the heuristic tokenizer gets wrong
# because it does not implement format-specific semantics. Each test is
# ``xfail(strict=True)`` so it fails loudly if the limitation is removed,
# letting us claim the fix.


@pytest.mark.parametrize(
    ("ver1", "ver2"),
    (
        # PEP 440: epoch outranks any base version.
        pytest.param("1!1.0", "2.0", id="pep440-epoch"),
        # Debian: epoch outranks any base version.
        pytest.param("2:1.0-1", "9.0", id="debian-epoch"),
        # Debian: revision (the part after the last ``-``) makes a version
        # newer, but the tokenizer treats string suffixes as pre-release.
        pytest.param("6.0.1-0ubuntu1", "6.0.1", id="debian-revision"),
    ),
)
@pytest.mark.xfail(strict=True, reason="Epoch semantics.")
def test_version_comparison_gt_known_failures(ver1, ver2):
    assert TokenizedString(ver1) > TokenizedString(ver2)


@pytest.mark.parametrize(
    ("ver1", "ver2"),
    (
        # PEP 440: dev releases precede all pre-releases.
        pytest.param("1.0.dev1", "1.0a1", id="pep440-dev-lt-alpha"),
        # Semver 11.4.4: numeric identifiers always have lower precedence
        # than alphanumeric identifiers in pre-release fields. Our
        # int-outranks-string rule is the exact opposite.
        pytest.param(
            "1.0.0-alpha.1",
            "1.0.0-alpha.beta",
            id="semver-numeric-lt-string",
        ),
    ),
)
@pytest.mark.xfail(strict=True, reason="Ordering inversion.")
def test_version_comparison_lt_known_failures(ver1, ver2):
    assert TokenizedString(ver1) < TokenizedString(ver2)


@pytest.mark.parametrize(
    ("ver1", "ver2"),
    (
        # PEP 440: local version equals base for ordering.
        pytest.param("1.0+local", "1.0", id="pep440-local-ignored"),
        # Semver: build metadata is ignored in precedence.
        pytest.param("1.0.0+build.123", "1.0.0", id="semver-build-metadata"),
        pytest.param(
            "1.0.0+build.123",
            "1.0.0+build.124",
            id="semver-build-metadata-diff",
        ),
        # Perl: floating-point versions treat ``1.1`` as ``1.100``.
        pytest.param("1.1", "1.10", id="perl-float-equal"),
        # Gentoo: three-digit-group conversion of Perl versions.
        pytest.param("1.020030", "1.20.30", id="gentoo-3digit-group"),
    ),
)
@pytest.mark.xfail(strict=True, reason="Format-specific normalization.")
def test_version_comparison_eq_known_failures(ver1, ver2):
    assert TokenizedString(ver1) == TokenizedString(ver2)
