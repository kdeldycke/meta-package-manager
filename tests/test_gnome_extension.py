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
bare `gjs` interpreter by {func}`test_gjs_unit_suite` when one is installed.
No CI runner running pytest installs `gjs`, so that wrapper is a convenience for
a developer who has one: in CI the same script is driven directly by the `gjs`
job of the `tests-gnome-extension.yaml` workflow.
"""

from __future__ import annotations

import ast
import importlib.util
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

pytestmark = pytest.mark.once
"""These assert on checked-in extension sources, not on the host: the
`once-tests` job runs them on a single runner instead of every matrix cell."""

PROJECT_ROOT = Path(__file__).parent.parent

EXTENSION_UUID = "mpm@kdeldycke.github.io"

EXTENSION_DIR = PROJECT_ROOT / "gnome-shell" / EXTENSION_UUID

SCHEMA_ID = "org.gnome.shell.extensions.mpm"

GJS_RUNNER = PROJECT_ROOT / "tests" / "gnome" / "run-tests.js"

EXPECTED_ICON_STATES = frozenset({"error", "unknown", "updates", "uptodate"})
"""Values of the `State` mapping in `extension.js`, each mapped by `STATE_ICONS`
to a stock symbolic icon name."""

PACK_DEFAULTS = frozenset({
    "extension.js",
    "metadata.json",
    "prefs.js",
    "schemas",
    "stylesheet.css",
})
"""Sources `gnome-extensions pack` bundles on its own.

`extension.js` and `metadata.json` are mandatory, `prefs.js` and the stylesheets
optional, and a `schemas/` folder is picked up automatically. Anything else needs
an explicit `--extra-source`, without which it silently never reaches the zip.
Documentation: [`gnome-extensions(1)` man
page](https://man.archlinux.org/man/extra/gnome-shell/gnome-extensions.1.en).
"""

PACKING_WORKFLOWS = ("release.yaml", "tests-gnome-extension.yaml")
"""Both workflows packing the extension: one produces the release asset, the
other the artifact round-tripped through `gnome-extensions install`."""


def _extension_source(*names: str) -> str:
    """Concatenate the content of the given extension source files."""
    return "\n".join(
        (EXTENSION_DIR / name).read_text(encoding="UTF-8") for name in names
    )


def _gschema() -> ElementTree.Element:
    """The `<schema>` element of the bundled GSettings schema."""
    schema_file = EXTENSION_DIR / "schemas" / f"{SCHEMA_ID}.gschema.xml"
    schema = ElementTree.parse(schema_file).getroot().find("schema")
    assert schema is not None
    return schema


def _state_icons() -> dict[str, str]:
    """The `STATE_ICONS` mapping of `extension.js`: state to stock icon name."""
    block = re.search(
        r"const STATE_ICONS = \{(.+?)\};",
        _extension_source("extension.js"),
        re.DOTALL,
    )
    assert block
    return dict(re.findall(r"(\w+):\s*'([^']+)'", block.group(1)))


def _gschema_keys() -> list[str]:
    """Key names declared in the GSettings schema, in file order."""
    return [key.attrib["name"] for key in _gschema().findall("key")]


def _install_argv(source: str) -> tuple[str, ...]:
    """The `INSTALL_ARGV` literal of a source file, JavaScript or Python.

    Both dialects spell it as a bracketed list of quoted strings, so one reader
    covers the two. Read as text rather than imported: this module stays free of
    package imports to keep its `once` marker from lowering the coverage slice.
    """
    literal = re.search(r"INSTALL_ARGV = [\[(](.+?)[\])]", source, re.DOTALL)
    assert literal
    return tuple(re.findall(r"['\"]([^'\"]+)['\"]", literal.group(1)))


def _extra_sources(workflow: str) -> set[str]:
    """Sources whitelisted with `--extra-source` by a workflow's pack step."""
    workflow_file = PROJECT_ROOT / ".github" / "workflows" / workflow
    content = workflow_file.read_text(encoding="UTF-8")
    return set(re.findall(r"--extra-source=(\S+)", content))


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
    schema = _gschema()
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
def test_state_maps_to_a_themed_icon(state):
    """Every panel state names a stock icon instead of bundled artwork.

    The shell resolves these against the user's icon theme, which is what lets
    it recolor them with the panel foreground and lets a theme (Yaru on Ubuntu)
    restyle them. The `-symbolic` suffix is what marks a name as themable.
    """
    icons = _state_icons()
    assert state in icons
    assert icons[state].endswith("-symbolic")


def test_no_orphan_icons():
    """The logo is the only artwork left, and the preferences window uses it."""
    shipped = {path.name for path in (EXTENSION_DIR / "icons").glob("*.svg")}
    assert shipped == {"mpm-logo.svg"}


def test_logo_matches_the_brand_mark():
    """The extension ships the brand mark itself, not a fork of it.

    `docs/brand_update.py` owns every artwork under `docs/assets/`, but not this
    copy: the extension bundles its own icons, and the flat redesign had to be
    carried over by hand. Byte-identity turns the next such drift into a failure.
    """
    bundled = (EXTENSION_DIR / "icons" / "mpm-logo.svg").read_text(encoding="UTF-8")
    brand = (PROJECT_ROOT / "docs" / "assets" / "icon.svg").read_text(encoding="UTF-8")
    assert bundled == brand


def test_install_bootstrap_matches_the_bar_plugin():
    """Both frontends offer the same command to install a missing `mpm`.

    The two menus are written in different languages against different toolkits,
    so nothing else holds their bootstrap offer together.
    """
    plugin = (PROJECT_ROOT / "meta_package_manager" / "bar_plugin.py").read_text(
        encoding="UTF-8"
    )
    assert _install_argv(_extension_source("mpm.js")) == _install_argv(plugin)


def test_pack_whitelists_are_identical():
    """Both packing workflows declare the same sources.

    They pack the same artifact: the tested zip stops being the shipped one the
    moment their whitelists diverge.
    """
    released, tested = (_extra_sources(name) for name in PACKING_WORKFLOWS)
    assert released == tested


def test_pack_whitelist_covers_every_source():
    """Every file of the extension directory reaches the packed zip.

    `gnome-extensions pack` packs from a whitelist, so a file added here but
    declared nowhere is dropped from the bundle without a word, and a declared
    file that was since removed breaks the pack. Both fail here instead.
    """
    # Hidden files belong to no bundle: .DS_Store and friends are not sources.
    shipped = {
        path.name
        for path in EXTENSION_DIR.iterdir()
        if not path.name.startswith(".")
    }
    assert shipped - PACK_DEFAULTS == _extra_sources(PACKING_WORKFLOWS[0])


def test_bundled_license_matches_the_project():
    """The extension carries its own copy of the license.

    The zip is distributed detached from the repository, on GitHub releases and
    extensions.gnome.org alike, and GNOME Shell extensions are derived works of
    a `GPL-2.0-or-later` codebase: the license text has to travel with it.
    """
    bundled = (EXTENSION_DIR / "license").read_text(encoding="UTF-8")
    assert bundled == (PROJECT_ROOT / "license").read_text(encoding="UTF-8")


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


def _capture_driver():
    """Load `docs/gnome_screenshots_update.py` by path, `docs` being no package."""
    spec = importlib.util.spec_from_file_location(
        "gnome_screenshots_update",
        PROJECT_ROOT / "docs" / "gnome_screenshots_update.py",
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_capture_driver_targets_this_extension():
    """The screenshot driver carries its own copy of the extension identity."""
    driver = _capture_driver()
    assert driver.EXTENSION_UUID == EXTENSION_UUID
    assert driver.SCHEMA_ID == SCHEMA_ID
    assert driver.EXTENSION_DIR == EXTENSION_DIR


def test_capture_settings_exist_in_the_schema():
    """Every extension setting the capture writes is declared in the schema.

    A renamed key would otherwise surface as a `gsettings set` failure minutes
    into a headless GNOME session, on a runner, instead of here.
    """
    source = (PROJECT_ROOT / "docs" / "gnome_screenshots_update.py").read_text("UTF-8")
    written = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "gsettings"
            and len(node.args) > 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "SCHEMA_ID"
            and isinstance(node.args[1], ast.Constant)
        ):
            written.add(node.args[1].value)
    assert written
    assert written <= set(_gschema_keys())


def test_captures_are_referenced_by_the_docs():
    """Each capture is shown on the extension's page, and none is an orphan.

    The images are written by a workflow and read by a page neither of which
    can see the other: a renamed shot leaves a broken image on the site and a
    stale file in the asset folder, and nothing else reports either.
    """
    driver = _capture_driver()
    page = (PROJECT_ROOT / "docs" / "gnome-shell.md").read_text("UTF-8")
    produced = {shot.path for shot in driver.SHOTS}
    for path in produced:
        assert f"assets/{path.name}" in page, path.name
    # Captured at MONITOR_SCALE, so displayed at its reciprocal: the two move
    # together or the images render at twice the size of everything else.
    assert page.count(f":scale: {100 // driver.MONITOR_SCALE}") == len(produced)
    # The same glob the capture workflow stages, so a committed file the driver
    # no longer produces is reported here rather than lingering.
    committed = set((PROJECT_ROOT / "docs" / "assets").glob("gnome-shell-*menu-*.png"))
    assert committed <= produced


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
