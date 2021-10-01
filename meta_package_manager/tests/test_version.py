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

from random import shuffle

import pytest

from ..version import Token, TokenizedString, parse_version


def reverse_fixtures(table):
    """Utility method to reverse a tuple of tuples."""
    return tuple(map(tuple, map(reversed, table)))


@pytest.mark.parametrize("value", [0, 123, "0", "123", "abc", "ABC", "123abc"])
def test_token_allowed_instanciation(value):
    Token(value)


@pytest.mark.parametrize("value", [None, -1, "a-b-c", 1.0])
def test_token_unauthorized_instanciation(value):
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
]


@pytest.mark.parametrize("token,value", eq_values)
def test_token_eq(token, value):
    assert token == value


@pytest.mark.parametrize("token,value", ne_values)
def test_token_ne(token, value):
    assert token != value


@pytest.mark.parametrize("token,value", gt_values)
def test_token_gt(token, value):
    assert token > value


@pytest.mark.parametrize("token,value", lt_values)
def test_token_lt(token, value):
    assert token < value


@pytest.mark.parametrize("token,value", gt_values + eq_values)
def test_token_ge(token, value):
    assert token >= value


@pytest.mark.parametrize("token,value", lt_values + eq_values)
def test_token_le(token, value):
    assert token <= value


def test_token_hash():
    assert hash(Token("9999")) == hash(Token("9999"))
    assert hash(Token("9999")) == hash(Token(9999))
    assert hash(Token(9999)) == hash(Token(9999))
    assert hash(Token("09999")) != hash(Token("9999"))
    assert hash(Token("09999")) != hash(Token(9999))


@pytest.mark.parametrize(
    "value", (0, 123, -1, "0", "1.2.3", "abc", "A-B-C", "123   a bc \n")
)
def test_tokenized_string_allowed_instanciation(value):
    TokenizedString(value)


@pytest.mark.parametrize(
    "value", (None, 1.0, [1, 2, 3], (1, 2, 3), {1, 2, 3}, {"a": 1, "b": 2})
)
def test_tokenized_string_unauthorized_instanciation(value):
    with pytest.raises(TypeError):
        TokenizedString(value)


def test_tokenized_string_hash():
    assert hash(TokenizedString("1.2.3")) == hash(TokenizedString("1.2.3"))
    assert hash(TokenizedString(9999)) == hash(TokenizedString(9999))
    assert hash(TokenizedString("9999")) == hash(TokenizedString(9999))
    assert hash(TokenizedString("09999")) != hash(TokenizedString("9999"))
    assert hash(TokenizedString("09999")) != hash(TokenizedString(9999))
    assert hash(TokenizedString("1.2.3", separator=".")) != hash(
        TokenizedString("1.2.3", separator="_")
    )


def test_tokenized_string_idempotent_instanciation():
    tok1 = TokenizedString("1.2.3")
    tok2 = TokenizedString(tok1)
    assert tok1 is tok2
    assert hash(tok1) == hash(tok2)
    assert tok1 == tok2


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
    ("1.2beta5", (1, 2, "beta", 5)),
    ("2.8.18-x86_64", (2, 8, 18, "x", 86, 64)),
    ("1.8.0_112-b16", (1, 8, 0, 112, "b", 16)),
    ("3.6.9_build_4685", (3, 6, 9, "build", 4685)),
    ("1.8.6-124-g6cd4c31", (1, 8, 6, 124, "g", 6, "cd", 4, "c", 31)),
    ("0.9999999", (0, 9999999)),
    ("0.0.0", (0, 0, 0)),
    ("1.0+git71+c79e264-r0", (1, 0, "git", 71, "c", 79, "e", 264, "r", 0)),
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
        (13, 0, 2, 8, "d", 4173, "c", 853231432, "f", 1, "e", 99, "d", 882),
    ),
    ("1.01+20150706hgc3698e0+dfsg-2", (1, 1, 20150706, "hgc", 3698, "e", 0, "dfsg", 2)),
)


@pytest.mark.parametrize("v_string,v_tuple", version_list)
def test_version_tokenizer(v_string, v_tuple):
    assert TokenizedString(v_string) == v_tuple


compared_gt = (
    ("2.0", "1.0"),
    ("0.1", "0"),
    ("0.1", "0.0"),
    ("0.1", "0.0.0.0.0"),
    # ("0.1", "0.beta2"),
    ("2.0", "1.0"),
    ("2.0", "1"),
    ("3.1.10", "3.1.9"),
    # ("6.2", "6.2.0"),
    # ("9.52", "9d"),
    ("8.2p1_1", "8.2p1"),
    # ("3.7.7", "3.7-beta2_1"),
    # ("2.1.1", "2.1.1-git-23hfb2-foobar"),
    (20200313, 20190801),
    ("2020.03.24", "2019.11.28"),
    # ("14.0.1,7:664493ef4a6946b186ff29eb326336a2",
    #  "14,36:076bab302c7b4508975440c56f6cc26a"),
)


@pytest.mark.parametrize("ver1,ver2", compared_gt)
def test_version_comparison_gt(ver1, ver2):
    assert TokenizedString(ver1) > TokenizedString(ver2)
    assert parse_version(ver1) > parse_version(ver2)


@pytest.mark.parametrize("ver1,ver2", reverse_fixtures(compared_gt))
def test_version_comparison_lt(ver1, ver2):
    assert TokenizedString(ver1) < TokenizedString(ver2)
    assert parse_version(ver1) < parse_version(ver2)


@pytest.mark.parametrize(
    "sequence",
    (
        [
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
    ),
)
def test_version_sorting(sequence):
    sorted_version = list(map(TokenizedString, sequence))
    ramdom_order = sorted_version.copy()
    shuffle(ramdom_order)
    assert ramdom_order != sorted_version
    assert sorted(ramdom_order) == sorted_version
