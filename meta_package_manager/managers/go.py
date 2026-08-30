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

from functools import cached_property
from pathlib import Path

from extra_platforms import ALL_PLATFORMS

from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Go(PackageManager):
    """The Go toolchain, wrapped for the binaries `go install` puts on the machine.

    A package here is a *command*, not a library: `go install <path>@<version>`
    compiles one and writes it into the toolchain's binary directory, where it
    stays until the file is deleted. Libraries are a module's own business and
    are scoped to the module that declares them, so they are outside what a
    system package manager can address.

    ```{note}
    The inventory is `go version -m`, not `go list`. Pointed at a directory,
    `go version` walks it recursively and reports the build information Go
    embeds in every binary it produced, which over the binary directory is
    exactly the set `go install` created. `go list` answers for the module in
    the working directory instead, so it reports nothing about the host.
    ```

    ```{caution}
    Go has no uninstall verb, in any scope: removing a command means deleting
    its file, which is not something a wrapper should do behind the tool's
    back. Nothing reports staleness either. Both absences are why
    [nao1215/gup](https://github.com/nao1215/gup) exists as a separate tool.
    ```

    Documentation: [go install](https://go.dev/ref/mod#go-install).
    """

    name = "Go"

    homepage_url = "https://go.dev"

    platforms = ALL_PLATFORMS

    requirement = ">=1.16.0"
    """`go install` only accepts a version suffix from Go `1.16`.

    Before it, the command built whatever the current directory's module
    resolved to, so a machine-wide install was not expressible. The release
    notes introduce the change as: "`go install` now accepts arguments with
    version suffixes (for example, `go install example.com/cmd@v1.0.0`). This
    causes `go install` to build and install packages in module-aware mode,
    ignoring the `go.mod` file in the current directory or any parent
    directory, if there is one."
    """

    cli_names = ("go",)

    version_regexes = (r"go\s+version\s+go(?P<version>\S+)\s",)
    """
    ```{code-block} shell-session

    $ go version
    go version go1.27.0 darwin/arm64
    ```
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        Each binary produces a multi-line record: a header naming the file, a
        `path` line carrying the import path `install` accepts, a `mod` line
        carrying the module that provided it with its version, then `build`
        settings and one `dep` line per transitive dependency.

        The id comes from `path` and the version from `mod`, which is why this
        cannot be one regex per line. The two agree whenever a module's main
        package sits at its root, as both samples below do, but a command
        installed from a subdirectory has a `path` ending in that subdirectory
        while `mod` stops at the module. `dep` lines are the dependency tree of
        the command rather than commands themselves, and are skipped.

        ```{code-block} shell-session

        $ go version -m /tmp/mpm-drive/go/bin
        /tmp/mpm-drive/go/bin/gup: go1.27.0
                path	github.com/nao1215/gup
                mod	github.com/nao1215/gup	v1.8.1	h1:An1c11EdZ36h40GDhtbx5NSRwbKvaEbjwOODwkBDjw4=
                dep	github.com/adrg/xdg	v0.5.3	h1:xRnxJXne7+oWDatRhR1JLnvuccuIeCoBu2rtuLqQB78=
                dep	github.com/cpuguy83/go-md2man/v2	v2.0.6	h1:XJtiaUW6dEEqVuZiMTn1ldk455QWwEIsMIJlo5vtkx0=
                dep	github.com/fatih/color	v1.19.0	h1:Zp3PiM21/9Ld6FzSKyL5c/BULoe/ONr9KlbYVOfG8+w=
                dep	github.com/gen2brain/beeep	v0.11.2	h1:+KfiKQBbQCuhfJFPANZuJ+oxsSKAYNe88hIpJuyKWDA=
                dep	github.com/hashicorp/go-version	v1.9.0	h1:CeOIz6k+LoN3qX9Z0tyQrPtiB1DFYRPfCIBtaXPSCnA=
                dep	github.com/jackmordaunt/icns/v3	v3.0.1	h1:xxot6aNuGrU+lNgxz5I5H0qSeCjNKp8uTXB1j8D4S3o=
                dep	github.com/mattn/go-colorable	v0.1.15	h1:+u9SLTRGnXv73cEsnsmoZBom+dMU88B2M0aDcWy0/jY=
                dep	github.com/mattn/go-isatty	v0.0.20	h1:xfD0iDuEKnDkl03q4limB+vH+GxLEtL/jb4xVJSWWEY=
                dep	github.com/nfnt/resize	v0.0.0-20180221191011-83c6a9932646	h1:zYyBkD/k9seD2A7fsi6Oo2LfFZAehjjQMERAvZLEDnQ=
                dep	github.com/russross/blackfriday/v2	v2.1.0	h1:JIOH55/0cWyOuilr9/qlrm0BSXldqnqwMsf35Ld67mk=
                dep	github.com/spf13/cobra	v1.10.2	h1:DMTTonx5m65Ic0GOoRY2c16WCbHxOOw6xxezuLaBpcU=
                dep	github.com/spf13/pflag	v1.0.9	h1:9exaQaMOCwffKiiiYk6/BndUBv+iRViNW+4lEMi0PvY=
                dep	go.yaml.in/yaml/v3	v3.0.4	h1:tfq32ie2Jv2UxXFdLJdh3jXuOzWiL1fo0bu/FbuKpbc=
                dep	golang.org/x/sys	v0.42.0	h1:omrd2nAlyT5ESRdCLYdm3+fMfNFE/+Rf4bDIQImRJeo=
                build	-buildmode=exe
                build	-compiler=gc
                build	DefaultGODEBUG=cryptocustomrand=1,tlssecpmlkem=0,tracebacklabels=0,urlstrictcolons=0,x509sslcertoverrideplatform=0
                build	CGO_ENABLED=1
                build	CGO_CFLAGS=
                build	CGO_CPPFLAGS=
                build	CGO_CXXFLAGS=
                build	CGO_LDFLAGS=
                build	GOARCH=arm64
                build	GOOS=darwin
                build	GOARM64=v8.0
        /tmp/mpm-drive/go/bin/hello: go1.27.0
                path	golang.org/x/example/hello
                mod	golang.org/x/example/hello	v0.0.0-20250915201037-7f05d217867b	h1:+gZE2jOdiscYByu0606Uw8Ldir2Cecd39Vq/3IEasRA=
                build	-buildmode=exe
                build	-compiler=gc
                build	DefaultGODEBUG=containermaxprocs=0,cryptocustomrand=1,decoratemappings=0,gotestjsonbuildtext=1,httpcookiemaxnum=0,httplaxcontentlength=1,httpmuxgo121=1,httpservecontentkeepheaders=1,multipathtcp=0,panicnil=1,randseednop=0,rsa1024min=0,tlsmlkem=0,tlssecpmlkem=0,tlssha1=1,tracebacklabels=0,updatemaxprocs=0,urlmaxqueryparams=0,urlstrictcolons=0,winreadlinkvolume=0,winsymlink=0,x509negativeserial=1,x509rsacrt=0,x509sha256skid=0,x509sslcertoverrideplatform=0,x509usepolicies=0
                build	CGO_ENABLED=1
                build	CGO_CFLAGS=
                build	CGO_CPPFLAGS=
                build	CGO_CXXFLAGS=
                build	CGO_LDFLAGS=
                build	GOARCH=arm64
                build	GOOS=darwin
                build	GOARM64=v8.0
        ```
        """
        package_id = None
        for line in self.run_cli("version", "-m", self.bin_dir).splitlines():
            # A record header names the file and carries no tab, so it both ends
            # the previous record and cannot be mistaken for a field line.
            if "\t" not in line:
                package_id = None
                continue
            # Leading whitespace is ignored rather than matched: the tool indents
            # every field line with one tab, but ruff rewrites a docstring's
            # indentation, so the sample above reaches the corpus with spaces.
            fields = line.strip().split("\t")
            if fields[0] == "path":
                package_id = fields[1]
            elif fields[0] == "mod" and package_id:
                yield self.package(id=package_id, installed_version=fields[2])
                package_id = None

    @cached_property
    def bin_dir(self) -> str:
        """Locate the directory `go install` writes commands into.

        `GOBIN` wins when it is set, and is empty on a stock installation,
        where the destination is the `bin` subdirectory of the first `GOPATH`
        entry instead.

        ```{code-block} shell-session

        $ go env GOBIN
        ```

        ```{code-block} shell-session

        $ go env GOPATH
        /tmp/mpm-drive/go
        ```
        """
        gobin = self.run_cli("env", "GOBIN", force_exec=True).strip()
        if gobin:
            return gobin
        gopath = self.run_cli("env", "GOPATH", force_exec=True).strip()
        return str(Path(gopath) / "bin")

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        The version suffix is mandatory outside a module, so an unpinned
        install asks for `@latest` explicitly rather than omitting it.

        ```{code-block} shell-session

        $ go install golang.org/x/example/hello@latest
        ```
        """
        return self.run_cli(
            "install", f"{package_id}@{version if version else 'latest'}"
        )
