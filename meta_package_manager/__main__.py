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
"""Allow the module to be run as a CLI:

.. code-block:: shell-session

    $ python -m meta_package_manager
"""

from __future__ import annotations


def main():
    """Execute the CLI but force its name to not let Click defaults to:

    .. code-block:: shell-session
        $ python -m meta_package_manager --version
        python -m meta_package_manager, version 7.2.0

    Indirection via this ``main()`` method was `required to reconcile
    <https://github.com/python-poetry/poetry/issues/5981>`_:

        - plain inline package call: ``python -m meta_package_manager``,
        - ``pyproject.toml`` entry point: ``mpm = 'meta_package_manager.__main__:main``,
        - Nuitka's main module invocation requirement:
          ``python -m nuitka (...) meta_package_manager/__main__.py``

    That way we can deduce all three cases from the entry point.
    """
    # Register config-defined managers before importing the Click group, so the
    # dynamic --<id> selectors enumerate them as first-class flags alongside the
    # built-ins. Best-effort and local-only; the authoritative registration happens
    # during config loading (config.register_config_managers_from_context).
    from meta_package_manager.config import register_eager_config_managers
    from meta_package_manager.pool import pool

    register_eager_config_managers(pool)

    from meta_package_manager.cli import mpm

    mpm(prog_name=mpm.name)


if __name__ == "__main__":
    main()
