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

import json
import re
from functools import cached_property

from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Yarn(PackageManager):
    """Virtual base shared by Yarn Classic and Yarn Berry.

    The two Yarn lines grew incompatible CLIs, so mpm models them as separate
    managers, {class}`YarnClassic` and {class}`YarnBerry`, both invoking the
    same `yarn` binary. The reported version decides which one is active: Classic
    claims the `1.x` range, Berry `2.x` and later. Only the shared cache-cleanup
    operation lives on this base.

    Command equivalences with the sibling JS managers are listed in
    [antfu-collective/ni](https://github.com/antfu-collective/ni?tab=readme-ov-file#ni).
    """

    homepage_url = "https://yarnpkg.com"
    logo = "yarn"

    platforms = ALL_PLATFORMS

    virtual = True

    def cleanup_cache(self) -> None:
        """Removes things we don't need anymore.

        See [`yarn cache clean`](https://yarnpkg.com/cli/cache/clean).

        ```{code-block} shell-session

        $ yarn cache clean --all
        yarn cache v1.22.19
        success Cleared cache.
        ✨  Done in 0.35s.
        ```
        """
        self.run_cli("cache", "clean", "--all")


class YarnClassic(Yarn):
    """Yarn Classic, the `1.x` line.

    mpm claims this class for any `yarn` binary reporting a `1.x` version and
    drives it through the `yarn global` command family, so installs, upgrades and
    removals target the global prefix. Its `--json` output is a stream of one JSON
    object per line, not a single document, so every query is parsed line by line.

    ```{note}
    Yarn has [no dedicated search command](https://github.com/yarnpkg/yarn/issues/778#issuecomment-253146299) by
    maintainer decision, so `search` is simulated with `yarn info` and only
    resolves exact package names.
    ```
    """

    maintenance_note = (
        "Yarn Classic (`1.x`) is [frozen](https://github.com/yarnpkg/yarn), taking "
        "only security fixes; the actively developed "
        "[Yarn Berry](https://github.com/yarnpkg/berry) line has a different CLI and "
        "is wrapped separately as the `yarn-berry` manager."
    )

    id = "yarn"

    name = "Yarn Classic"

    requirement = ">=1.20.0,<2.0.0"

    cli_names = ("yarn",)

    pre_args = ("--silent",)

    _INSTALLED_REGEXP = re.compile(
        r"^.+\"data\":\"\\\"(?P<package_id>\S+)"
        r"@(?P<version>\S+)\\\" has binaries:\"\}$",
        re.MULTILINE,
    )

    """
    ```{code-block} shell-session

    $ yarn --version
    1.22.11
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        ```{code-block} shell-session

        $ yarn --silent global --json list --depth 0
        {"type":"activityStart","data":{"id":0}}
        {"type":"activityTick","data":{"id":0,"name":"awesome-lint@^0.18.0"}}
        {"type":"activityTick","data":{"id":0,"name":"arrify@^2.0.1"}}
        {"type":"activityTick","data":{"id":0,"name":"case@^1.6.3"}}
        {"type":"activityTick","data":{"id":0,"name":"emoji-regex@^9.2.0"}}
        {"type":"activityEnd","data":{"id":0}}
        {"type":"progressStart","data":{"id":0,"total":327}}
        {"type":"progressTick","data":{"id":0,"current":1}}
        {"type":"progressTick","data":{"id":0,"current":2}}
        {"type":"progressTick","data":{"id":0,"current":3}}
        {"type":"progressTick","data":{"id":0,"current":4}}
        {"type":"progressTick","data":{"id":0,"current":5}}
        {"type":"progressFinish","data":{"id":0}}
        {"type":"info","data":"\"awesome-lint@0.18.0\" has binaries:"}
        {"type":"list","data":{"type":"bins-awesome-lint","items":["awesome-lint"]}}
        ```

        ```{code-block} console

        $ yarn global list --depth 0
        yarn global v1.22.19
        info "awesome-lint@0.18.0" has binaries:
           - awesome-lint
        ✨  Done in 0.13s.
        ```
        """
        output = self.run_cli(
            "global", "--json", "list", "--depth", "0", must_succeed=True
        )

        for package_id, version in self._INSTALLED_REGEXP.findall(output):
            yield self.package(id=package_id, installed_version=version)

    @cached_property
    def global_dir(self) -> str:
        """Locate the global directory.

        ```{code-block} shell-session

        $ yarn global dir
        ~/.config/yarn/global
        ```
        """
        return self.run_cli("global", "dir", force_exec=True).rstrip()

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        Yarn emits its `--json` output as a stream of one JSON object per line
        (the sample below elides the `info` color-legend object; the
        human-readable transcript further down shows it):

        ```{code-block} shell-session

        $ yarn --silent --json outdated --cwd ~/.config/yarn/global
        {"type":"warning","data":"package.json: No license field"}
        {"type":"table","data":{"head":["Package","Current","Wanted","Latest","Package Type","URL"],"body":[["markdown","0.4.0","0.4.0","0.5.0","dependencies","git://github.com/evilstreak/markdown-js.git"]]}}
        ```

        ```{code-block} console

        $ yarn outdated --cwd ~/.config/yarn/global
        yarn outdated v1.22.19
        warning package.json: No license field
        info Color legend :
        "<red>"    : Major Update backward-incompatible updates
        "<yellow>" : Minor Update backward-compatible features
        "<green>"  : Patch Update backward-compatible bug fixes
        Package  Current Wanted Latest Package Type URL
        markdown 0.4.0   0.4.0  0.5.0  dependencies git://github.com/.../md-js.git
        ✨  Done in 0.95s.
        ```
        """
        output = self.run_cli(
            "--json", "outdated", "--cwd", self.global_dir, must_succeed=True
        )
        if output:
            for line in output.splitlines():
                if not line:
                    continue
                obj = json.loads(line)
                if obj["type"] == "table":
                    for package in obj["data"]["body"]:
                        if package[2] == "linked":
                            continue
                        yield self.package(
                            id=package[0],
                            installed_version=package[1],
                            latest_version=package[3],
                        )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{warning}
        Yarn maintainers have [decided to not implement a dedicated search command](https://github.com/yarnpkg/yarn/issues/778#issuecomment-253146299).

        Search is simulated by a direct call to `yarn info`, and as a result only
        works for exact match.
        ```

        ```{code-block} shell-session

        $ yarn --silent --json info @bouzuya/borage
        {"type":"inspect","data":{"name":"@bouzuya/borage","description":"A GitHub Pages deployer for bouzuya/blog.bouzuya.net","dist-tags":{"latest":"3.1.2"},"versions":["3.1.2"],"maintainers":[{"name":"bouzuya","email":"m@bouzuya.net"}],"time":{"modified":"2022-06-12T15:26:55.277Z","created":"2017-05-21T23:27:30.332Z","3.1.2":"2017-05-21T23:27:30.332Z"},"homepage":"https://github.com/bouzuya/borage","keywords":["bouzuya","bbn"],"repository":{"type":"git","url":"git+https://github.com/bouzuya/borage.git"},"author":{"name":"bouzuya","email":"m@bouzuya.net","url":"http://bouzuya.net"},"bugs":{"url":"https://github.com/bouzuya/borage/issues"},"license":"MIT","readmeFilename":"README.md","version":"3.1.2","dependencies":{"aws-sdk":"^2.1.30","es6-promise":"^2.1.1","glob":"^5.0.9","mime":"^1.3.4"},"devDependencies":{"coffee-script":"^1.9.2","del":"^1.1.1","gulp":"^3.8.11","gulp-coffee":"^2.3.1","gulp-concat":"^2.5.2","gulp-espower":"^0.10.1","gulp-mocha":"^2.0.1","gulp-sourcemaps":"^1.5.2","gulp-uglify":"^1.2.0","gulp-util":"^3.0.4","gulp-watch":"^4.2.4","power-assert":"^0.11.0","run-sequence":"^1.1.0","sinon":"^1.14.1"},"main":"index.js","scripts":{"build":"gulp build","clean":"gulp clean","start":"gulp","test":"gulp test","watch":"gulp watch"},"gitHead":"0f45887778f89ccf9a17e0a097067ae085c515e5","dist":{"shasum":"9be1578d9d2859833cca435d3501d439f6f27489","tarball":"https://registry.npmjs.org/@bouzuya/borage/-/borage-3.1.2.tgz","integrity":"sha512-gBp5eS2+5VSQqqgHs7fBwesw+ZhbfwewPoiyaINPIchhiIkAjnJ8gPN7RsBqzUftZNXF04x5HuHZG9xe/PHptw==","signatures":[{"keyid":"SHA256:jl3bwswu80PjjokCgh0o2w5c2U4LhQAE57gj9cz1kzA","sig":"MEQCIBDqfLdL4pGDRKMfJ3HvGGE6tmWoM2uKV8jZWAVshLaKAiAhfqB0YTsKYVz2SUSa1Jz/ZiBPlkF3jAPGqV7UN+lpBw=="}]}}}
        ```
        """
        output = self.run_cli("--json", "info", query, must_succeed=True)

        if output:
            for line in output.splitlines():
                if not line:
                    continue
                result = json.loads(line)
                if result["type"] == "inspect":
                    package = result["data"]
                    yield self.package(
                        id=package["name"],
                        description=package["description"],
                        latest_version=package["version"],
                    )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        ```{code-block} shell-session

        $ yarn --silent global add awesome-lint
        yarn global v1.22.19
        [1/4] 🔍  Resolving packages...
        [2/4] 🚚  Fetching packages...
        [3/4] 🔗  Linking dependencies...
        [4/4] 🔨  Building fresh packages...

        success Installed "awesome-lint@0.18.0" with binaries:
            - awesome-lint
        ✨  Done in 16.15s.
        ```
        """
        return self.run_cli("global", "add", package_id)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all outdated packages.

        ```{code-block} shell-session

        $ yarn --silent global upgrade --latest
        yarn global v1.22.19
        [1/4] 🔍  Resolving packages...
        [2/4] 🚚  Fetching packages...
        [3/4] 🔗  Linking dependencies...
        [4/4] 🔨  Rebuilding all packages...
        success Saved lockfile.
        success Saved 271 new dependencies.
        info Direct dependencies
        ├─ awesome-lint@0.18.0
        └─ markdown@0.5.0
        info All dependencies
        ├─ @babel/code-frame@7.18.6
        ├─ @babel/helper-validator-identifier@7.18.6
        ├─ @nodelib/fs.scandir@2.1.5
        ├─ array-to-sentence@1.1.0
        ├─ array-union@2.1.0
        ├─ awesome-lint@0.18.0
        ├─ fs.realpath@1.0.0
        (...)
        └─ zwitch@1.0.5
        ✨  Done in 19.89s.
        ```
        """
        return self.build_cli("global", "upgrade", "--latest")

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the provided package.

        ```{code-block} shell-session

        $ yarn --silent global upgrade markdown --latest
        yarn global v1.22.19
        [1/4] 🔍  Resolving packages...
        [2/4] 🚚  Fetching packages...
        [3/4] 🔗  Linking dependencies...
        [4/4] 🔨  Rebuilding all packages...
        success Saved lockfile.
        success Saved 2 new dependencies.
        info Direct dependencies
        └─ markdown@0.5.0
        info All dependencies
        ├─ markdown@0.5.0
        └─ nopt@2.1.2
        ✨  Done in 1.77s.
        ```
        """
        return self.build_cli("global", "upgrade", package_id, "--latest")

    def remove(self, package_id: str) -> str:
        """Remove one package.

        ```{code-block} shell-session

        $ yarn --silent global remove awesome-lint
        yarn global v1.22.19
        [1/2] 🗑  Removing module awesome-lint...
        [2/2] 🔨  Regenerating lockfile and installing missing dependencies...
        success Uninstalled packages.
        ✨  Done in 0.21s.
        ```
        """
        return self.run_cli("global", "remove", package_id)


class YarnBerry(Yarn):
    """Yarn Berry, the `2.x` and later line.

    mpm claims this class for any `yarn` binary reporting a `2.x` or newer
    version.

    ```{warning}
    Yarn Berry removed the `yarn global` command family entirely: it has no
    notion of globally installed packages. Only `search` is available, while
    `installed`, `outdated`, `install`, `upgrade` and `remove` are all
    unsupported.
    ```

    ```{note}
    `search` is simulated with `yarn npm info` and only resolves exact
    package names.
    ```
    """

    id = "yarn-berry"

    name = "Yarn Berry"

    requirement = ">=2.0.0"

    cli_names = ("yarn",)

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        ```{warning}
        Search is simulated by a direct call to `yarn npm info`, and as a
        result only works for exact match.
        ```

        ```{code-block} shell-session

        $ yarn npm info @bouzuya/borage --json
        {"name":"@bouzuya/borage","description":"A GitHub Pages deployer for bouzuya/blog.bouzuya.net","dist-tags":{"latest":"3.1.2"},"versions":["3.1.2"],"readme":"![borage logo](https://cloud.githubusercontent.com/assets/1221346/17835500/a6087528-67aa-11e6-9370-9f16dd9988b0.png)\n\nborage is a deployer for [blog.bouzuya.net](http://blog.bouzuya.net).\n\nSee: [bouzuya/blog.bouzuya.net][]\n\n## Installation\n\n    $ npm install https://github.com/bouzuya/borage/archive/master.tar.gz\n\nor\n\n    $ npm install https://github.com/bouzuya/borage/archive/{VERSION}.tar.gz\n\n## License\n\n[MIT](LICENSE)\n\n## Author\n\n[bouzuya][user] &lt;[m@bouzuya.net][email]&gt; ([http://bouzuya.net][url])\n\n[user]: https://github.com/bouzuya\n[email]: mailto:m@bouzuya.net\n[url]: http://bouzuya.net\n[bouzuya/blog.bouzuya.net]: https://github.com/bouzuya/blog.bouzuya.net\n[bouzuya/grunt-tentacles]: https://github.com/bouzuya/grunt-tentacles\n[bouzuya/kraken]: https://github.com/bouzuya/kraken\n","maintainers":[{"name":"bouzuya","email":"m@bouzuya.net"}],"time":{"modified":"2022-06-12T15:26:55.277Z","created":"2017-05-21T23:27:30.332Z","3.1.2":"2017-05-21T23:27:30.332Z"},"homepage":"https://github.com/bouzuya/borage","keywords":["bouzuya","bbn"],"repository":{"type":"git","url":"git+https://github.com/bouzuya/borage.git"},"author":{"name":"bouzuya","email":"m@bouzuya.net","url":"http://bouzuya.net"},"bugs":{"url":"https://github.com/bouzuya/borage/issues"},"license":"MIT","readmeFilename":"README.md","version":"3.1.2","dependencies":{"aws-sdk":"^2.1.30","es6-promise":"^2.1.1","glob":"^5.0.9","mime":"^1.3.4"},"devDependencies":{"coffee-script":"^1.9.2","del":"^1.1.1","gulp":"^3.8.11","gulp-coffee":"^2.3.1","gulp-concat":"^2.5.2","gulp-espower":"^0.10.1","gulp-mocha":"^2.0.1","gulp-sourcemaps":"^1.5.2","gulp-uglify":"^1.2.0","gulp-util":"^3.0.4","gulp-watch":"^4.2.4","power-assert":"^0.11.0","run-sequence":"^1.1.0","sinon":"^1.14.1"},"main":"index.js","scripts":{"build":"gulp build","clean":"gulp clean","start":"gulp","test":"gulp test","watch":"gulp watch"},"gitHead":"0f45887778f89ccf9a17e0a097067ae085c515e5","dist":{"shasum":"9be1578d9d2859833cca435d3501d439f6f27489","tarball":"https://registry.npmjs.org/@bouzuya/borage/-/borage-3.1.2.tgz","integrity":"sha512-gBp5eS2+5VSQqqgHs7fBwesw+ZhbfwewPoiyaINPIchhiIkAjnJ8gPN7RsBqzUftZNXF04x5HuHZG9xe/PHptw==","signatures":[{"keyid":"SHA256:jl3bwswu80PjjokCgh0o2w5c2U4LhQAE57gj9cz1kzA","sig":"MEQCIBDqfLdL4pGDRKMfJ3HvGGE6tmWoM2uKV8jZWAVshLaKAiAhfqB0YTsKYVz2SUSa1Jz/ZiBPlkF3jAPGqV7UN+lpBw=="}]}}
        ```
        """
        output = self.run_cli("npm", "info", query, "--json")

        if output:
            package = json.loads(output)
            yield self.package(
                id=package["name"],
                description=package.get("description"),
                latest_version=package.get("dist-tags", {}).get("latest")
                or package.get("version"),
            )
