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

from meta_package_manager.sbom.base import writer_unavailable_reason

# No `importorskip` here on purpose, unlike every other SBOM test module: what
# this covers is the message shown when a writer library is missing or too old,
# so skipping it exactly when that is true would cover nothing.


def test_writer_unavailable_reason_separates_absent_from_outdated():
    """The two failure modes need opposite remedies, so they cannot share a
    message. A distribution shipping a writer library below the floor already
    satisfies `[sbom-offline]`, so telling its user to install that extra
    strands them: they install it again, nothing changes, and the only clue
    left is a symbol name belonging to no package they can name. NixOS carries
    exactly such a `cyclonedx-python-lib`.
    """
    absent = writer_unavailable_reason(
        "no-such-distribution", ImportError("No module named 'nope'")
    )
    assert "is not installed" in absent
    assert "--upgrade" not in absent

    # Any installed distribution stands in for the outdated case: the branch
    # turns on the distribution being present, not on which one it is.
    outdated = writer_unavailable_reason(
        "meta-package-manager",
        ImportError("cannot import name 'PredefinedLifecycle'"),
    )
    assert "is installed but too old" in outdated
    assert "PredefinedLifecycle" in outdated
    assert "--upgrade" in outdated
