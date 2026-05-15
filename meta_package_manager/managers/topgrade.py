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

from extra_platforms import ALL_WINDOWS, BSD, LINUX_LIKE, MACOS

from ..base import PackageManager


class Topgrade(PackageManager):
    """A meta-meta-package-manager: ``topgrade`` wrapped by ``mpm``.

    ``topgrade`` is a Rust utility that auto-detects every package manager,
    runtime version manager, plugin manager and OS updater installed on the
    host, then runs each one in sequence. From ``mpm``'s vantage point it
    looks like a black-box upgrader: there is no notion of installed packages,
    no concept of outdated entries, no search index, no install or remove
    primitives. Only ``upgrade --all`` makes sense, and it is the only
    operation this class implements.

    Adding ``topgrade`` to ``mpm``'s pool is a knowing nod to
    `XKCD #927 <https://xkcd.com/927/>`_: ``mpm`` already wraps every
    package manager ``topgrade`` wraps, so routing through it is structurally
    redundant. The benefit is access to ``topgrade``'s broader catalog of
    runtime/plugin managers in the same ``mpm upgrade --all`` invocation
    (``mise``, ``rustup``, ``oh-my-zsh``, JetBrains plugins, vim/tmux plugin
    managers, etc.) without having to teach ``mpm`` each one.

    .. caution::
        ``mpm upgrade --topgrade`` runs ``topgrade --yes`` to skip the
        interactive prompts. If you also select other managers that
        ``topgrade`` itself drives (``brew``, ``apt``, ``pacman``, etc.),
        those will be upgraded twice in the same run.
    """

    name = "Topgrade"

    homepage_url = "https://github.com/topgrade-rs/topgrade"

    platforms = BSD, LINUX_LIKE, MACOS, ALL_WINDOWS

    requirement = ">=17.0.0"
    """Pinned to the ``17.x`` series, which matches the topgrade revision the
    benchmark page is calibrated against (see ``docs/benchmark.md``)."""

    version_regexes = (r"topgrade\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ topgrade --version
        topgrade 17.4.0
    """

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Upgrade every package manager ``topgrade`` knows about.

        ``--yes`` skips ``topgrade``'s "press enter to continue" prompts so the
        run completes unattended, matching the contract ``mpm`` expects from
        an ``upgrade_all_cli`` implementation.

        .. code-block:: shell-session

            $ topgrade --yes
        """
        return self.build_cli("--yes")
