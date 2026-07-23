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
"""Mac App Store parsing tests.

These tests cover the pure-Python JSON-stream parser. They do not invoke
`mas` and are platform-agnostic.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.mas import MAS


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param("", [], id="empty"),
        pytest.param("   \n\t\n", [], id="whitespace_only"),
        pytest.param(
            '{"adamID":1,"name":"Foo"}\n{"adamID":2,"name":"Bar"}\n',
            [{"adamID": 1, "name": "Foo"}, {"adamID": 2, "name": "Bar"}],
            id="newline_separated",
        ),
        pytest.param(
            '{"adamID":1,"name":"Foo"}{"adamID":2,"name":"Bar"}',
            [{"adamID": 1, "name": "Foo"}, {"adamID": 2, "name": "Bar"}],
            id="no_separator",
        ),
        pytest.param(
            '\n\n{"adamID":1,"name":"Foo"}\n\n\n{"adamID":2,"name":"Bar"}\n\n',
            [{"adamID": 1, "name": "Foo"}, {"adamID": 2, "name": "Bar"}],
            id="extra_whitespace",
        ),
        # Regression: `mas` does not escape literal newlines inside string
        # fields, so the previous `splitlines()`-based parser raised
        # `JSONDecodeError: Unterminated string` on records like this one.
        pytest.param(
            '{"adamID":1,"name":"Multi\nLine","version":"1.0"}\n'
            '{"adamID":2,"name":"Bar","version":"2.0"}',
            [
                {"adamID": 1, "name": "Multi\nLine", "version": "1.0"},
                {"adamID": 2, "name": "Bar", "version": "2.0"},
            ],
            id="embedded_newline_in_string",
        ),
        pytest.param(
            '{"adamID":1,"name":"Has \\"quotes\\" and {braces}"}',
            [{"adamID": 1, "name": 'Has "quotes" and {braces}'}],
            id="escaped_quotes_and_braces_in_string",
        ),
    ),
)
def test_parse_json_stream(output, expected):
    assert list(MAS._parse_json_stream(output)) == expected
