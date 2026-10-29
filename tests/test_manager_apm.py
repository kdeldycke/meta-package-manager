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

"""Atom package manager output tests.

These tests stub `run_cli` and replay the samples documented on
{class}`~meta_package_manager.managers.apm.APM`. They never call `apm`.
"""

from __future__ import annotations

import pytest

from meta_package_manager.managers.apm import APM

SEARCH_OUTPUT = """\
[
  {
    "name": "atom-python-run",
    "main": "./lib/atom-python-run.js",
    "version": "0.7.3",
    "description": "Run a python source file.",
    "keywords": [
      "python"
    ],
    "repository": "https://github.com/foreshadow/atom-python-run",
    "license": "MIT",
    "engines": {
      "atom": ">=1.0.0 <2.0.0"
    },
    "dependencies": {},
    "readme": "Blah blah",
    "downloads": 41379,
    "stargazers_count": 16
  },
  {
    "name": "build-python",
    "version": "0.6.3",
    "description": "Atom Build provider for python/python3",
    "repository": "https://github.com/idleberg/atom-build-python",
    "license": "MIT",
    "keywords": [
      "buildprovider",
      "compile",
      "python",
      "python3",
      "linter",
      "lint"
    ],
    "main": "lib/provider.js",
    "engines": {
      "atom": ">=1.0.0 <2.0.0"
    },
    "providedServices": {
      "builder": {
        "description": "Compiles Python",
        "versions": {
          "2.0.0": "provideBuilder"
        }
      }
    },
    "package-deps": [
      "build"
    ],
    "dependencies": {
      "atom-package-deps": "^4.3.1"
    },
    "devDependencies": {
      "babel-eslint": "^7.1.1",
      "coffeelint-stylish": "^0.1.2",
      "eslint": "^3.13.1",
      "eslint-config-atom-build": "^4.0.0",
      "gulp": "github:gulpjs/gulp#4.0",
      "gulp-coffeelint": "^0.6.0",
      "gulp-debug": "^3.0.0",
      "gulp-jshint": "^2.0.4",
      "gulp-jsonlint": "^1.2.0",
      "gulp-lesshint": "^2.1.0",
      "jshint": "^2.9.4"
    },
    "scripts": {
      "test": "gulp lint"
    },
    "readme": "Blah blah",
    "downloads": 2838,
    "stargazers_count": 0
  }
]"""
"""`apm search --json python | jq`, as the docstring of
{meth}`~meta_package_manager.managers.apm.APM.search` shows it, minus the `(...)`
marker that truncates the array there."""


@pytest.mark.parametrize(
    ("extended", "search_args"),
    (
        pytest.param(False, ["--no-description"], id="name-only"),
        pytest.param(True, [], id="extended"),
    ),
)
def test_search(capture_run_cli, extended, search_args):
    """Each result gives its name, description and version, and only an
    extended search lets `apm` match the descriptions.
    """
    manager = APM()
    calls = capture_run_cli(manager, SEARCH_OUTPUT)
    packages = [
        (p.id, p.description, str(p.latest_version))
        for p in manager.search("python", extended=extended, exact=False)
    ]
    assert packages == [
        ("atom-python-run", "Run a python source file.", "0.7.3"),
        ("build-python", "Atom Build provider for python/python3", "0.6.3"),
    ]
    assert calls == [("search", search_args, "--json", "python")]


@pytest.mark.parametrize("output", ("", "[]"))
def test_search_empty_answer(stub_run_cli, output):
    """No output and an empty array both mean no match."""
    manager = APM()
    stub_run_cli(manager, output)
    assert list(manager.search("python", extended=False, exact=False)) == []
