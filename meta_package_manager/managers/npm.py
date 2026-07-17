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

from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from click_extra.execution import TArg, TNestedArgs

    from ..package import Package


class NPM(PackageManager):
    """The Node.js package manager.

    mpm drives npm in global mode: every call forces ``--global`` so packages land
    in the shared prefix instead of the current working directory. Per-scope
    targeting and multi-binary discovery (several node versions through nvm) are
    tracked in `#1725
    <https://github.com/kdeldycke/meta-package-manager/issues/1725>`__. Command
    equivalences with the sibling JS managers are listed at
    https://github.com/antfu-collective/ni?tab=readme-ov-file#ni.

    Queries parse npm's ``--json`` output. Mutating operations are marked
    privileged so ``--sudo`` can escalate writes into a root-owned global prefix,
    though escalation stays dormant unless requested.

    .. note::
        npm enforces a supply-chain cooldown through its ``min-release-age``
        resolver option, refusing to resolve any release younger than the
        configured age. The version floor exists for it: ``min-release-age`` first
        shipped in ``11.10.0``, and older releases silently ignore the setting.

    .. caution::
        A fatal npm error (usually a local node version out of sync) is reported
        both on ``<stderr>`` and as a JSON blob on ``<stdout>``. The ``run_cli``
        override blanks that JSON so the failure surfaces once, through
        ``<stderr>``, rather than being parsed as a package listing.
    """

    name = "Node npm"

    homepage_url = "https://www.npmjs.com"

    brewfile_entry_type = "npm"

    platforms = ALL_PLATFORMS

    requirement = ">=11.10.0"
    """`11.10.0 <https://github.com/npm/cli/releases/tag/v11.10.0>`_ is the first
    version to ship ``min-release-age``, the purpose-built release-age gate mpm uses
    for the supply-chain cooldown (see :py:attr:`cooldown_env_var`). Older npm
    releases silently ignore the env var, so the floor avoids advertising a gate that
    does nothing.
    """

    cooldown_env_var = "npm_config_min-release-age"
    """npm honors a release-age cooldown through its ``min-release-age`` resolver
    option.

    npm maps any ``npm_config_<key>`` environment variable to a config setting, so
    ``npm_config_min-release-age`` sets ``min-release-age`` without touching the
    user's ``.npmrc``. Once set, npm refuses to resolve any package version younger
    than the configured age, which covers ``install`` and ``update`` along with their
    transitive dependencies. The hyphenated env var passes cleanly through Python's
    :py:class:`subprocess.Popen` ``env=`` mapping (shells that reject ``export
    foo-bar=baz`` are not involved).

    The ``cooldown_env_value()`` method below is overridden to emit an integer number of
    days, the unit ``min-release-age`` expects.

    See https://docs.npmjs.com/cli/v11/using-npm/config#min-release-age.
    """

    pre_args = (
        # Operates in "global" mode, so that packages are installed into the
        # prefix folder instead of the current working directory.
        "--global",
        # Suppress the progress bar.
        "--no-progress",
        # Suppress the update notification when using an older version of npm than
        # the latest.
        "--no-update-notifier",
        # Hide the message displayed at the end of each install that acknowledges
        # the number of dependencies looking for funding.
        "--no-fund",
        # Disable sending of audit reports to the configured registries.
        "--no-audit",
    )
    """
    .. code-block:: shell-session

        $ npm --version
        6.13.7
    """

    def cooldown_env_value(self) -> str:
        """Render :py:attr:`meta_package_manager.execution.CLIExecutor.cooldown` as an
        integer day count for npm's ``min-release-age``.

        Sub-day cooldowns round up so the gate over-protects rather than silently
        collapses to ``0`` (the "no cooldown" sentinel).
        """
        return self.cooldown_rounded_up(86400)

    def run_cli(self, *args: TArg | TNestedArgs, **kwargs: Any) -> str:
        """Like the common run_cli helper, but silence NPM's JSON output on error.

        NPM is prone to breakage if local node version is not in sync:

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                --json outdated
            {
              "error": {
                "code": "ERR_OUT_OF_RANGE",
                "summary": "The value of \"err\" is out of range. Received 536870212",
                "detail": ""
              }
            }
        """
        output = super().run_cli(*args, **kwargs)

        # NPM fatal errors are reported both in <stderr> output and as JSON. So we
        # silence the errors in JSON so they get reported in CLI output (as
        # they're already featured in self.cli_errors) without raising error
        # (unless the --stop-on-error option is provided).
        if "--json" in args and output and self.cli_errors:
            output = ""

        return output

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                --json --depth 0 list | jq
            {
              "name": "lib",
              "dependencies": {
                "@eslint/json": {
                  "version": "0.9.0",
                  "overridden": false
                },
                "@mermaid-js/mermaid-cli": {
                  "version": "10.8.0",
                  "overridden": false
                },
                "corepack": {
                  "version": "0.30.0",
                  "overridden": false
                },
                "google-closure-compiler": {
                  "version": "20240317.0.0",
                  "overridden": false
                },
                "npm": {
                  "version": "10.9.2",
                  "overridden": false
                },
                "raven": {
                  "version": "2.6.4",
                  "overridden": false
                },
                "wrangler": {
                  "version": "3.51.2",
                  "overridden": false
                }
              }
            }
        """
        output = self.run_cli("--json", "--depth", "0", "list", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg_id, pkg_infos in data.get("dependencies", {}).items():
                yield self.package(
                    id=pkg_id,
                    installed_version=pkg_infos["version"],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                --json outdated | jq
            {
              "my-linked-package": {
                "current": "0.0.0-development",
                "wanted": "linked",
                "latest": "linked",
                "location": "/Users/..."
              },
              "npm": {
                "current": "3.10.3",
                "wanted": "3.10.5",
                "latest": "3.10.5",
                "location": "/opt/homebrew/lib/node_modules/npm"
              }
            }
        """
        output = self.run_cli("--json", "outdated", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg_id, pkg_infos in data.items():
                if pkg_infos["wanted"] == "linked":
                    continue
                yield self.package(
                    id=pkg_id,
                    # It seems "current" is not always populated.
                    installed_version=pkg_infos.get("current"),
                    latest_version=pkg_infos["latest"],
                )

    @search_capabilities(exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        Doc: https://docs.npmjs.com/cli/search.html

        .. caution::
            Search does not supports exact matching.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                search --json python | jq
            [
              {
                "name": "python",
                "description": "Interact with a python child process",
                "maintainers": [
                  {
                    "username": "drderidder",
                    "email": "drderidder@gmail.com"
                  }
                ],
                "version": "0.0.4",
                "date": "2015-01-25T02:48:07.820Z"
              },
              {
                "name": "raven",
                "description": "A standalone (Node.js) client for Sentry",
                "maintainers": [
                  {
                    "username": "benvinegar",
                    "email": "ben@benv.ca"
                  },
                  {
                    "username": "lewisjellis",
                    "email": "me@lewisjellis.com"
                  },
                  {
                    "username": "mattrobenolt",
                    "email": "m@robenolt.com"
                  },
                  {
                    "username": "zeeg",
                    "email": "dcramer@gmail.com"
                  }
                ],
                "keywords": [
                  "raven",
                  "sentry",
                  "python",
                  "errors",
                  "debugging",
                  "exceptions"
                ],
                "version": "1.1.2",
                "date": "2017-02-09T02:54:07.723Z"
              },
              {
                "name": "brush-python",
                "description": "Python brush module for SyntaxHighlighter.",
                "maintainers": [
                  {
                    "username": "alexgorbatchev",
                    "email": "alex.gorbatchev@gmail.com"
                  }
                ],
                "keywords": [
                  "syntaxhighlighter",
                  "brush",
                  "python"
                ],
                "version": "4.0.0",
                "date": "2016-02-07T21:32:39.597Z"
              },
              (...)
            ]

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                search --json --no-description python | jq
        """
        search_args = []
        if not extended:
            search_args.append("--no-description")

        output = self.run_cli("search", "--json", search_args, query, must_succeed=True)

        data = self.parse_json(output)
        if data:
            for pkg_infos in data:
                yield self.package(
                    id=pkg_infos.get("name"),
                    description=pkg_infos.get("description"),
                    latest_version=pkg_infos.get("version"),
                )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                install markdown

            added 3 packages in 3s
        """
        # Marked privileged so --sudo / `[mpm.managers.npm] sudo = true` can escalate
        # global installs; dormant by default (npm's default_sudo is False).
        return self.run_cli("install", package_id, sudo=True)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                update
        """
        return self.build_cli("update", sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                upgrade raven
        """
        return self.build_cli("upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                uninstall raven
        """
        return self.run_cli("uninstall", package_id, sudo=True)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            $ npm --global --no-progress --no-update-notifier --no-fund --no-audit \
                cache clean --force
        """
        self.run_cli("cache", "clean", "--force")
