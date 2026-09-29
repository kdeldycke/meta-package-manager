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

"""Test suite of `mpm`.

Three behaviors of the CLI decide how a test can reach it:

- Spinners and progress bars draw on an interactive terminal only, so the
  non-TTY `CliRunner` of click-extra never emits them. Drive the CLI under
  {func}`pty.openpty` to exercise them. The `✓`/`✘` trail lines and finishers
  print on any stream: a `CliRunner` result or `capsys` reads them off
  `<stderr>`.
- `--dry-run` simulates every manager invocation, the read-only ones included.
  That covers the installed-package lookup by which `remove` and `upgrade` find
  their source managers, so a dry-run of those reports "not recognized" and
  never reaches their multi-manager path. Use a purl, which carries the manager
  and needs no lookup, or a unit fixture.
- `--plan` runs the reads and captures the writes, as
  `meta_package_manager.execution._MUTATING_OPERATIONS` documents. Test it
  against real reads or purls, and assert on `<stdout>`: the plan is plain
  `echo` there, and only the trail goes to `<stderr>`.

A module marked `once` runs on one runner and not on the matrix, so it imports
no package code beyond `__version__`: the matrix run holds the coverage floor,
and a test that covers `meta_package_manager` stays on it.
"""
