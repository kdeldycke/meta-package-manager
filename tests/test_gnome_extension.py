# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""Static invariants of the GNOME Shell extension.

The extension is GJS code the Python suite cannot import, so these tests pin the
contracts that keep its moving parts in sync: the `metadata.json` identity, the
GSettings schema, the stylesheet classes, the icon set and the argv builders.
The behavioral coverage lives in `tests/gnome/run-tests.js`, executed under a
bare `gjs` interpreter by {func}`test_gjs_unit_suite` when one is installed (CI
always has one, via the `tests-gnome-extension.yaml` workflow).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from shutil import which
from xml.etree import ElementTree

import pytest

from meta_package_manager import __version__

PROJECT_ROOT = Path(__file__).parent.parent

EXTENSION_UUID = "mpm@kdeldycke.github.io"

EXTENSION_DIR = PROJECT_ROOT / "gnome-shell" / EXTENSION_UUID

SCHEMA_ID = "org.gnome.shell.extensions.mpm"

GJS_RUNNER = PROJECT_ROOT / "tests" / "gnome" / "run-tests.js"

EXPECTED_ICON_STATES = frozenset({"error", "unknown", "updates", "uptodate"})
"""Values of the ``State`` mapping in ``extension.js``, each backed by a
``mpm-<state>-symbolic.svg`` icon."""


def _extension_source(*names: str) -> str:
    """Concatenate the content of the given extension source files."""
    return "\n".join(
        (EXTENSION_DIR / name).read_text(encoding="UTF-8") for name in names
    )


def _gschema_keys() -> list[str]:
    """Key names declared in the GSettings schema, in file order."""
    schema_file = EXTENSION_DIR / "schemas" / f"{SCHEMA_ID}.gschema.xml"
    tree = ElementTree.parse(schema_file)
    schema = tree.getroot().find("schema")
    assert schema is not None
    return [key.attrib["name"] for key in schema.findall("key")]


def test_metadata_well_formed():
    metadata = json.loads((EXTENSION_DIR / "metadata.json").read_text("UTF-8"))
    # The install directory must be named after the UUID.
    assert metadata["uuid"] == EXTENSION_UUID
    assert metadata["name"] == "Meta Package Manager"
    assert metadata["settings-schema"] == SCHEMA_ID
    assert metadata["gettext-domain"] == "meta-package-manager"
    assert metadata["url"] == "https://github.com/kdeldycke/meta-package-manager"
    # ESM-era GNOME releases only: 46 is the Ubuntu 24.04 LTS floor.
    assert metadata["shell-version"] == ["46", "47", "48", "49", "50"]
    # Kept in lockstep with the package by bump-my-version, like the
    # <xbar.version> header of the bar plugin.
    assert metadata["version-name"] == __version__


def test_gschema_well_formed():
    schema_file = EXTENSION_DIR / "schemas" / f"{SCHEMA_ID}.gschema.xml"
    tree = ElementTree.parse(schema_file)
    schema = tree.getroot().find("schema")
    assert schema is not None
    assert schema.attrib["id"] == SCHEMA_ID
    # The path is the schema ID with dots-to-slashes, per GSettings convention.
    assert schema.attrib["path"] == "/org/gnome/shell/extensions/mpm/"
    keys = _gschema_keys()
    # Repository-wide ordering convention: keys sorted alphabetically.
    assert keys == sorted(keys)
    # Every key documents itself.
    for key in schema.findall("key"):
        assert key.findtext("summary"), key.attrib["name"]
        assert key.findtext("description"), key.attrib["name"]


def test_settings_keys_in_sync():
    """Every key read in the JS sources exists in the schema, and vice versa.

    Guards against the drift arch-update ships with, where code defaults
    disagree with schema defaults or keys outlive their last reader.
    """
    source = _extension_source("extension.js", "prefs.js", "mpm.js")
    referenced = set(re.findall(r"get_(?:boolean|int|string)\('([a-z-]+)'\)", source))
    # The prefs rows take their key as first argument after settings.
    referenced.update(re.findall(r"Row\(settings, '([a-z-]+)'", source))
    assert referenced == set(_gschema_keys())


def test_css_classes_in_sync():
    """Every `.mpm-*` class referenced in JS is styled, and vice versa."""
    source = _extension_source("extension.js")
    # Settings keys share the mpm- prefix: filter them out of the literals.
    referenced = set(re.findall(r"'(mpm-[a-z-]+)'", source)) - set(_gschema_keys())
    stylesheet = (EXTENSION_DIR / "stylesheet.css").read_text("UTF-8")
    styled = set(re.findall(r"\.(mpm-[a-z-]+)", stylesheet))
    assert referenced == styled


def test_icon_states_in_sync():
    """The `State` mapping values match the bundled symbolic icon set."""
    source = _extension_source("extension.js")
    state_block = re.search(r"const State = \{(.+?)\};", source, re.DOTALL)
    assert state_block
    states = set(re.findall(r"'([a-z]+)'", state_block.group(1)))
    assert states == EXPECTED_ICON_STATES


@pytest.mark.parametrize("state", sorted(EXPECTED_ICON_STATES))
def test_symbolic_icon_exists(state):
    assert (EXTENSION_DIR / "icons" / f"mpm-{state}-symbolic.svg").is_file()


def test_no_orphan_icons():
    expected = {f"mpm-{state}-symbolic.svg" for state in EXPECTED_ICON_STATES}
    # The logo only appears in the preferences window.
    expected.add("mpm-logo.svg")
    shipped = {path.name for path in (EXTENSION_DIR / "icons").glob("*.svg")}
    assert shipped == expected


def test_runtime_argv_long_form():
    """The argv builders only emit long-form options.

    Same rule as for every argv `mpm` itself constructs at runtime (see the
    manager classes and `meta_package_manager/sudo.py`). The only tolerated
    short form is `sh -c`, which POSIX defines with no long equivalent.
    """
    source = _extension_source("mpm.js")
    short_flags = set(re.findall(r"'(-[^-'][^']*)'", source)) - {"-c"}
    assert not short_flags
    # The canonical long-form flags of the refresh cycle are all present.
    for flag in (
        "'--no-color'",
        "'--table-format'",
        "'--timeout'",
        "'--verbosity'",
        "'--all'",
    ):
        assert flag in source


def test_extension_js_shell_free_module():
    """`mpm.js` never imports shell modules, so it stays testable under gjs."""
    source = _extension_source("mpm.js")
    # Match import statements only: comments legitimately mention the scheme.
    assert not re.search(r"from ['\"]resource:", source)


def test_process_import_boundaries():
    """The two-process import rules of the extensions.gnome.org guidelines.

    The shell process must never load GTK libraries, and the preferences
    process must never load shell libraries.
    """
    shell_side = _extension_source("extension.js", "mpm.js")
    assert not re.search(r"gi://(?:Adw|Gdk|Gtk)", shell_side)
    prefs_side = _extension_source("prefs.js")
    assert not re.search(r"gi://(?:Clutter|Meta|Shell|St)\b", prefs_side)
    # The prefs process resource path is /org/gnome/Shell/Extensions/ (capital
    # S); the lowercase path below is the shell-process namespace.
    assert "resource:///org/gnome/shell/" not in prefs_side


@pytest.mark.skipif(not which("gjs"), reason="gjs interpreter not available")
def test_gjs_unit_suite():
    """Run the GJS unit suite against the shell-free `mpm.js` module."""
    env = os.environ.copy()
    # Homebrew's gjs ships a GjsPrivate typelib referencing libgjs.0.dylib by
    # bare name, which dyld cannot resolve on its own: point the fallback
    # search at the Homebrew library directory. No-op anywhere else.
    if sys.platform == "darwin":
        env["DYLD_FALLBACK_LIBRARY_PATH"] = "/opt/homebrew/lib:/usr/local/lib"
    process = subprocess.run(
        ("gjs", "-m", str(GJS_RUNNER)),
        capture_output=True,
        text=True,
        encoding="UTF-8",
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    assert process.returncode == 0, (
        f"gjs suite failed:\n{process.stdout}\n{process.stderr}"
    )
    assert "not ok" not in process.stdout
