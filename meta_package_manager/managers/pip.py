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

import email.message
import importlib.metadata
import re
import subprocess
import sys
from functools import cached_property
from pathlib import Path
from typing import cast

from extra_platforms import ALL_PLATFORMS

from ..capabilities import version_not_implemented
from ..execution import READ_ONLY_TIMEOUT, VERSION_PROBE
from ..manager import PackageManager
from ..package import (
    EMPTY_METADATA,
    Dependency,
    DependencyScope,
    Originator,
    PackageMetadata,
    Supplier,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator

    from ..package import Package
    from ..version import TokenizedString


_EXTERNALLY_MANAGED_PROBE = (
    "import os, sys, sysconfig; "
    "marker = os.path.join(sysconfig.get_path('stdlib'), 'EXTERNALLY-MANAGED'); "
    "print(1 if os.path.exists(marker) and sys.prefix == sys.base_prefix else 0)"
)
"""One-liner run inside a candidate interpreter to report whether {pep}`668` would
block `pip install` into its default scope.

Prints `1` when the interpreter is externally managed (an `EXTERNALLY-MANAGED`
marker sits in its `stdlib` directory) *and* is not a virtualenv
(`sys.prefix == sys.base_prefix`), the exact combination pip refuses to install
into without `--break-system-packages`. Prints `0` otherwise.
"""


_DEP_SPEC_SPLIT_REGEX = re.compile(
    r"^(?P<name>[A-Za-z0-9_.\-]+)(?P<extras>\[[^\]]+\])?(?P<rest>.*)$"
)


def _split_dep_spec(spec: str) -> tuple[str, str, str]:
    """Split a {pep}`508` requirement string into (name, extras, rest).

    Example: `"cryptography[ssh]>=42"` → `("cryptography", "[ssh]", ">=42")`.
    Used by {meth}`Pip._distribution_metadata` to extract just the
    dependency name for relationship resolution while preserving the
    version constraint as portable metadata.
    """
    match = _DEP_SPEC_SPLIT_REGEX.match(spec.strip())
    if not match:
        return "", "", ""
    return match["name"], match["extras"] or "", match["rest"].strip()


class Pip(PackageManager):
    """The pip package installer for Python, driven as a module (`python -m pip`)
    rather than through the `pip` executable.

    Calling the module through the interpreter lets `pip` upgrade itself, an
    advantage on Windows in particular
    (https://snarky.ca/why-you-should-use-python-m-pip/).

    Installed and outdated packages are read from pip's `list --format=json`
    output. The `outdated` query adds `--not-required` to report only
    top-level packages, since upgrading a transitive dependency can break its
    parent's version constraints ([#1214](https://github.com/kdeldycke/meta-package-manager/issues/1214)). There is
    no `search`: PyPI disabled its server-side search API in 2020 under
    unmanageable load, so `pip search` no longer works (see [pip issue 5216](https://github.com/pypa/pip/issues/5216#issuecomment-744605466)).

    ```{note}

    All operations target the default pip scope (system site-packages, or the
    active virtualenv). Per-scope targeting (system vs user vs venv) and
    multi-binary discovery (multiple pythons via pyenv) are tracked in
    [#1725](https://github.com/kdeldycke/meta-package-manager/issues/1725).
    ```

    ```{note}

    Interpreter discovery probes the running Python first, so an `mpm`
    installed inside a virtualenv manages that virtualenv, then the Python(s)
    on `PATH`. Two kinds are skipped so the manager only targets a scope
    the user can install into: `mpm`'s own distributor-managed bundle
    (Homebrew stages it under a `Cellar` prefix) and any
    externally-managed, non-virtualenv interpreter that {pep}`668` forbids
    `pip install` into. When every candidate is skipped, the manager
    reports as unavailable.
    ```

    ```{note}

    Installs, upgrades and removals are marked privileged, so a global
    install can escalate with `--sudo`, but escalation is off by default.
    The supply-chain cooldown needs pip `26.1`, the first release to honor
    `--uploaded-prior-to`; older pip silently ignores the release-age gate.
    ```
    """

    name = "Python pip"

    homepage_url = "https://pip.pypa.io"

    platforms = ALL_PLATFORMS

    requirement = ">=26.1.0"
    """[26.1](https://github.com/pypa/pip/releases/tag/26.1) is the first version to
    ship `--uploaded-prior-to`, the release-age gate mpm uses for the supply-chain
    cooldown (see {attr}`cooldown_env_var`). Older pip releases silently ignore
    `PIP_UPLOADED_PRIOR_TO`, so the floor avoids advertising a gate that does
    nothing.
    """

    cooldown_env_var = "PIP_UPLOADED_PRIOR_TO"
    """pip honors a release-age cooldown through its `--uploaded-prior-to` resolver
    option.

    pip maps any `PIP_<UPPER_SNAKE>` environment variable to a config setting, so
    `PIP_UPLOADED_PRIOR_TO` sets the option without touching the user's `pip.conf`.
    The flag excludes from resolution any distribution uploaded after the given
    instant, which covers `install` and `upgrade` (with transitive dependencies).
    pip parses the RFC 3339 timestamp produced by the default
    {meth}`meta_package_manager.execution.CLIExecutor.cooldown_env_value`.

    See https://github.com/pypa/pip/issues/13674.
    """

    # Targets `python3` CLI first to allow for some systems (like macOS) to keep the
    # default `python` CLI tied to the Python 2.x ecosystem.
    cli_names = ("python3", "python")

    pre_args = (
        "-m",
        "pip",  # Canonical call to Python's pip module.
        "--no-color",  # Suppress colored output.
    )

    version_cli_options = (*pre_args, "--version")
    version_regexes = (r"pip\s+(?P<version>\S+)",)
    """
    ```{code-block} shell-session

    $ python -m pip --no-color --version
    pip 2.0.2 from /usr/local/lib/python/site-packages/pip (python 3.7)
    ```
    """

    def search_all_cli(
        self,
        cli_names: Iterable[str],
        env=None,
    ) -> Generator[Path, None, None]:
        """Yield the Python interpreters the pip manager may target.

        The running interpreter is probed first, so an `mpm` installed into a
        virtualenv manages that virtualenv's own packages, then the Python(s)
        found on `PATH`. Two kinds of interpreter are skipped, so the pip
        manager only ever targets a scope the user can actually install into:

        - mpm's own distributor-managed bundle (see
          {meth}`_running_from_bundled_app`), and
        - any externally-managed, non-virtualenv interpreter {pep}`668` would
          forbid `pip install` into (see {meth}`_pip_install_blocked`).

        When every candidate is skipped the manager is left with no
        {attr}`cli_path` and reports as unavailable, which is correct: there
        is no user-managed pip environment to act on.

        ```{todo}

        Evaluate [findpython](https://github.com/frostming/findpython) (the
        maintained MIT rewrite of `pythonfinder`) to replace the discovery
        loop here. It would only cover discovery: the eligibility filters
        ({meth}`_running_from_bundled_app`, {meth}`_pip_install_blocked`)
        stay mpm's job, since findpython locates interpreters but does not
        judge whether `pip install` is allowed into one.
        ```
        """
        current_python = None
        current_exec = sys.executable
        # Skip the running interpreter when it is mpm's own bundled environment:
        # probing it would shadow the user's real Python and surface mpm and its
        # pinned dependencies as bogus pip upgrades.
        if current_exec and not self._running_from_bundled_app():
            current_python = Path(current_exec)
            # Still track it for the dedup below even when PEP 668 blocks it.
            if not self._pip_install_blocked(current_python):
                yield current_python

        # Return the rest of the Python executables found on the system as usual,
        # skipping the one already covered above and any externally-managed,
        # non-virtualenv interpreter pip could not install into.
        for py_path in super().search_all_cli(cli_names=cli_names, env=env):
            if py_path == current_python or self._pip_install_blocked(py_path):
                continue
            yield py_path

    @staticmethod
    def _running_from_bundled_app() -> bool:
        """Is `mpm` running from its own distributor-managed application bundle?

        Some distributors ship `mpm` inside a private virtualenv they own and
        manage, instead of installing it into a Python environment the user
        drives with pip. Homebrew is the canonical case: its formula stages
        `meta-package-manager` and every dependency under a `Cellar` prefix
        via `brew`, in a `--without-pip --system-site-packages` virtualenv
        whose interpreter {meth}`search_all_cli` would otherwise probe first.

        Treating that bundle as a pip scope is wrong twice over: it shadows the
        user's real Python (so `mpm --pip` reports only mpm's own closure), and
        it surfaces `meta-package-manager` itself, its pinned dependencies, and
        unrelated `--system-site-packages` leakage as outdated pip packages
        whose upgrade command would mutate the bundle behind the distributor's
        back. When this returns `True`, {meth}`search_all_cli` skips the
        running interpreter and falls through to the Python(s) on `PATH`.

        Detection keys on Homebrew's two independent fingerprints, either of
        which is conclusive on its own:

        - `sys.prefix` sits under a `Cellar` directory (covering the
          `/opt/homebrew`, `/usr/local` and Linuxbrew prefixes), or
        - `meta-package-manager`'s `INSTALLER` dist-info record is `brew`.

        ```{note}

        Other standalone-app installers (`pipx`, `uv tool`) also place
        `mpm` in a private virtualenv, but are not detected here: they
        leave an `INSTALLER` of `pip` or `uv` and live outside
        `Cellar`, so these signals alone cannot tell them apart from a
        deliberate user install. See [#1767](https://github.com/kdeldycke/meta-package-manager/issues/1767).
        ```
        """
        if "/Cellar/" in sys.prefix:
            return True
        try:
            installer = (
                importlib.metadata.distribution("meta-package-manager").read_text(
                    "INSTALLER",
                )
                or ""
            )
        except importlib.metadata.PackageNotFoundError:
            return False
        return installer.strip().lower() == "brew"

    def _pip_install_blocked(self, python_path: Path) -> bool:
        """Would {pep}`668` block `pip install` into `python_path`'s default scope?

        Runs the candidate interpreter with {data}`_EXTERNALLY_MANAGED_PROBE` to
        decide whether it is an externally-managed, non-virtualenv interpreter: the
        kind a system or distribution package manager owns, where pip refuses to
        install. {meth}`search_all_cli` drops such interpreters so the pip manager
        only ever targets a Python the user can actually install into, instead of
        surfacing that environment's distro-managed packages as outdated pip upgrades
        whose installation pip would reject.

        The probe inherits the `--timeout` override when one is set, else the
        {data}`~meta_package_manager.execution.READ_ONLY_TIMEOUT` read-only cap.

        Errs on the side of keeping a candidate: a probe that times out, crashes, or
        prints anything unexpected returns `False`, leaving discovery untouched
        rather than hiding a usable interpreter.
        """
        timeout = self.timeout if self.timeout is not None else READ_ONLY_TIMEOUT
        try:
            result = subprocess.run(
                (str(python_path), "-c", _EXTERNALLY_MANAGED_PROBE),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.stdout.strip() == "1"

    @cached_property
    def version(self) -> TokenizedString | None:
        """Print Python's own version before Pip's.

        This gives much more context to the user about the environment when a Python
        executable is found but Pip is not.

        Runs:

        ```{code-block} shell-session

        $ python --version --version
        Python 3.10.10 (Feb  8 2023, 05:34) [Clang 14.0.0 (clang-1400.0.29.202)]
        ```
        """
        if self.executable:
            # Tag this as a version probe so it inherits the short read-only timeout
            # rather than the long mutating default, matching the base `version`
            # property. `python --version` should never need the conservative cap.
            self._active_operation = VERSION_PROBE
            self.run_cli(
                ("--version", "--version"),
                auto_pre_cmds=False,
                auto_pre_args=False,
                auto_post_args=False,
                force_exec=True,
            )

        # XXX The sentence below gets modernized with `super().version` by ruff.
        # See: https://beta.ruff.rs/docs/rules/#pyupgrade-up
        # But we're explicitly using the old syntax to bypass `cached_property`.
        return super(Pip, self).version  # noqa: UP008

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ python -m pip --no-color list --format=json --verbose --quiet
        [
         {
            "version": "1.3",
            "name": "backports.functools-lru-cache",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
          },
          {
            "version": "0.9999999",
            "name": "html5lib",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
          },
          {
            "name": "setuptools",
            "version": "46.0.0",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": ""
          },
          {
            "version": "2.8",
            "name": "Jinja2",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": ""
          }
        ]
        ```
        """
        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            "list", "--format=json", "--verbose", "--quiet", must_succeed=True
        )

        data = self.parse_json(output)
        if data:
            for package in data:
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                )

    def package_metadata_batch(
        self,
        packages: Iterable[Package],
    ) -> Iterator[tuple[Package, PackageMetadata]]:
        """Enrich installed pip packages via {mod}`importlib.metadata`.

        Each installed distribution exposes its `METADATA` file (the
        `Core Metadata` from {pep}`621`) plus `RECORD`, `WHEEL`,
        and `INSTALLER` files in its `.dist-info` directory. This
        method reads them in-process: no shell-outs, no network, fast
        enough to enumerate hundreds of distributions in a fraction of a
        second.

        Maps `Home-page` / `Project-URL` lines into the portable
        `homepage` / `vcs_url` / `issue_tracker_url` slots, walks
        `Requires-Dist` into typed {class}`meta_package_manager.package.Dependency`
        edges, and promotes the upstream author or maintainer to
        {class}`meta_package_manager.package.Originator`.
        """
        package_list = list(packages)
        if not package_list:
            return

        for package in package_list:
            try:
                dist = importlib.metadata.distribution(package.id)
            except importlib.metadata.PackageNotFoundError:
                yield package, EMPTY_METADATA
                continue
            try:
                yield package, self._distribution_metadata(dist)
            except Exception:  # noqa: BLE001
                yield package, EMPTY_METADATA

    @staticmethod
    def _distribution_metadata(
        dist: importlib.metadata.Distribution,
    ) -> PackageMetadata:
        """Translate an `importlib.metadata.Distribution` into
        {class}`PackageMetadata`.
        """
        # `Distribution.metadata` returns an `email.message.Message` at
        # runtime, but the typeshed protocol omits `.get()` on the older
        # Python versions we still support.
        meta = cast("email.message.Message", dist.metadata)

        homepage = meta.get("Home-page") or None
        vcs_url = None
        issue_tracker_url = None
        # PEP 621 split the legacy Home-page header into the Project-URL
        # multi-value field with a `label, url` payload. The exact
        # labels vary across PyPI projects, so match on conventional
        # substrings while staying case-insensitive.
        for raw in meta.get_all("Project-URL") or ():
            if "," not in raw:
                continue
            label, _, url = raw.partition(",")
            label_key = label.strip().lower()
            url = url.strip()
            if not url:
                continue
            if not homepage and label_key in {"home", "homepage", "documentation"}:
                homepage = url
            if not vcs_url and label_key in {
                "source",
                "repository",
                "source code",
                "code",
                "github",
            }:
                vcs_url = url
            if not issue_tracker_url and label_key in {
                "issues",
                "issue tracker",
                "bug tracker",
                "tracker",
                "bugs",
            }:
                issue_tracker_url = url

        license_str = meta.get("License") or None
        if license_str and "\n" in license_str:
            # Some projects dump the full license text here. Truncate to
            # the first line so the SPDX parser has a fighting chance.
            license_str = license_str.splitlines()[0].strip()

        author_name = meta.get("Author") or meta.get("Maintainer") or None
        author_email = meta.get("Author-email") or meta.get("Maintainer-email") or None
        originator = None
        if author_name:
            # `Author-email` can carry a `"Name <email>"` payload.
            email_match = None
            if author_email and "<" in author_email and ">" in author_email:
                email_match = author_email.split("<", 1)[1].split(">", 1)[0].strip()
            elif author_email:
                email_match = author_email
            originator = Originator(name=author_name, email=email_match)

        # Requires-Dist lines look like `cryptography>=42.0; python_version<'3.13'`.
        # Strip environment markers and version constraints to land just
        # the dependency name in `target_id`; the version_constraint
        # column carries the rest for any downstream consumer that wants
        # it.
        deps: list[Dependency] = []
        for raw in meta.get_all("Requires-Dist") or ():
            if ";" in raw:
                spec, _, _marker = raw.partition(";")
            else:
                spec = raw
            spec = spec.strip()
            name, _, constraint = _split_dep_spec(spec)
            if name:
                deps.append(
                    Dependency(
                        target_id=name,
                        scope=DependencyScope.RUNTIME,
                        version_constraint=constraint or None,
                    )
                )

        extras: dict[str, object] = {}
        for keyword_header in ("Keywords",):
            value = meta.get(keyword_header)
            if value:
                extras[f"pip.{keyword_header.lower()}"] = value
        classifiers = meta.get_all("Classifier") or ()
        if classifiers:
            extras["pip.classifiers"] = list(classifiers)

        return PackageMetadata(
            download_url=meta.get("Download-URL") or None,
            homepage=homepage,
            vcs_url=vcs_url,
            issue_tracker_url=issue_tracker_url,
            license_declared=license_str,
            license_concluded=license_str,
            supplier=Supplier(name="PyPI", url="https://pypi.org"),
            originator=originator,
            summary=meta.get("Summary") or None,
            description=meta.get("Summary") or None,
            dependencies=tuple(deps),
            extras=extras,
        )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        ```{note}

        The `--not-required` flag filters out transitive dependencies,
        restricting results to top-level packages only. Upgrading transitive
        dependencies can break version constraints of their parent packages.
        See [#1214](https://github.com/kdeldycke/meta-package-manager/issues/1214).
        ```

        ```{code-block} shell-session

        $ python -m pip --no-color list --format=json --outdated \
        > --not-required --verbose --quiet
        [
          {
            "latest_filetype": "wheel",
            "version": "0.7.9",
            "name": "alabaster",
            "latest_version": "0.7.10",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
          },
          {
            "latest_filetype": "wheel",
            "version": "0.9999999",
            "name": "html5lib",
            "latest_version": "0.999999999",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
           },
          {
            "latest_filetype": "wheel",
            "version": "2.8",
            "name": "Jinja2",
            "latest_version": "2.9.5",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
           },
          {
            "latest_filetype": "wheel",
            "version": "0.5.3",
            "name": "mccabe",
            "latest_version": "0.6.1",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
           },
          {
            "latest_filetype": "wheel",
            "version": "2.2.0",
            "name": "pycodestyle",
            "latest_version": "2.3.1",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": "pip"
           },
          {
            "latest_filetype": "wheel",
            "version": "2.1.3",
            "name": "Pygments",
            "latest_version": "2.2.0",
            "location": "/usr/local/lib/python3.7/site-packages",
            "installer": ""
           }
        ]
        ```
        """
        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            "list",
            "--format=json",
            "--outdated",
            "--not-required",
            "--verbose",
            "--quiet",
            must_succeed=True,
        )

        data = self.parse_json(output)
        if data:
            for package in data:
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                    latest_version=package["latest_version"],
                )

    # No search operation: PyPI disabled its server-side search API in 2020 because of
    # unmanageable load, so `pip search` no longer works.
    # See https://github.com/pypa/pip/issues/5216#issuecomment-744605466.

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ python -m pip --no-color install arrow
        Collecting arrow
          Using cached arrow-1.1.1-py3-none-any.whl (60 kB)
        Collecting python-dateutil>=2.7.0
          Using cached python_dateutil-2.8.2-py2.py3-none-any.whl (247 kB)
        Requirement already satisfied: six>=1.5 in python3.9/site-packages (1.16.0)
        Installing collected packages: python-dateutil, arrow
        Successfully installed arrow-1.1.1 python-dateutil-2.8.2
        ```
        """
        # Marked privileged so --sudo / `[mpm.managers.pip] sudo = true` can escalate
        # global installs; dormant by default (pip's default_sudo is False).
        return self.run_cli("install", package_id, sudo=True)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        ```{code-block} shell-session

        $ python -m pip --no-color install --upgrade six
        Collecting six
          Using cached six-1.15.0-py2.py3-none-any.whl (10 kB)
        Installing collected packages: six
          Attempting uninstall: six
            Found existing installation: six 1.14.0
            Uninstalling six-1.14.0:
              Successfully uninstalled six-1.14.0
        Successfully installed six-1.15.0
        ```

        ```{note}

        Pip lacks support of a proper full upgrade command. Raising an error let the
        parent class upgrade packages one by one.

        See: https://github.com/pypa/pip/issues/59
        ```
        """
        return self.build_cli("install", "--upgrade", package_id, sudo=True)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ python -m pip --no-color uninstall --yes arrow
        ```
        """
        return self.run_cli("uninstall", "--yes", package_id, sudo=True)

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore.

        ```{code-block} shell-session

        $ python -m pip --no-color cache purge
        ```
        """
        self.run_cli("cache", "purge")

    def doctor_cli(self) -> tuple[str, ...]:
        """Generates the CLI running the native self-diagnosis.

        `check` verifies that installed packages have compatible dependencies,
        reporting conflicts on `<stdout>` and exiting non-zero on any.

        ```{code-block} shell-session

        $ python -m pip --no-color check
        No broken requirements found.
        ```
        """
        return self.build_cli("check")
