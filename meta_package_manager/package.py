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
"""Manager-agnostic package data model, and its metadata companion.

{class}`meta_package_manager.package.Package` is the model.
{class}`meta_package_manager.package.PackageMetadata` augments it with data pulled from
sources outside the package manager itself.

Defines the lightweight representation of a package (ID, name, installed and latest
versions, architecture) that every manager operation yields, plus
{func}`meta_package_manager.package.packages_asdict` to serialize a subset of its
fields for output.

{class}`Package` is the inventory plane: what the package manager itself
reports through its native query commands. It backs every operation in
{mod}`meta_package_manager.manager`.

{class}`~meta_package_manager.package.PackageMetadata` is the enrichment plane:
licenses, supplier, checksums, declared dependency graph, on-disk per-package
SBOMs, and other facts gathered through extra queries (CLI sub-commands, on-disk
parsers, upstream registries). Populated by
{meth}`meta_package_manager.manager.PackageManager.package_metadata_batch`,
consumed by {mod}`meta_package_manager.sbom` today and reserved for any
future caller that wants more than the bare inventory.

Kept deliberately free of manager logic, so it can be imported without pulling in the
manager engine ({mod}`meta_package_manager.manager`).
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Literal, NamedTuple
from urllib.parse import quote, unquote, urlsplit

from .version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime
    from pathlib import Path

    from .version import TokenizedString


PURL_QUALIFYING_NAMESPACES = frozenset((
    "alpm",
    "apk",
    "cpan",
    "deb",
    "luarocks",
    "rpm",
))
"""pURL types whose namespace qualifies a package without being part of its ID.

For these types, the namespace names who distributes the package: the vendor for
`alpm`, `apk`, `deb` and `rpm`, the author's CPAN ID for `cpan`, the user manifest
for `luarocks`. {meth}`~meta_package_manager.specifier.Specifier.parse_purl` keeps
the name alone for them, where joining the two would ask `apt` for `debian/curl`.
Every other type reads the namespace as the part of the package ID before its last
slash: an npm scope, a Composer vendor, a Homebrew tap.

Each type's `namespace_definition` in the
[pURL type definitions](https://github.com/package-url/purl-spec/tree/5d57978402cf113c37b974330e553e2bcb91e9fa/types)
settles which side it falls on.
"""

_PURL_KEY_CHARS = frozenset(string.ascii_letters + string.digits + ".-_")
"""Characters a pURL type and a qualifier key are made of."""


class PurlType(NamedTuple):
    """The rules the definition of a registered pURL type sets on its components."""

    namespace: Literal["optional", "prohibited", "required"]
    """Whether a pURL of the type carries a namespace."""

    lowercase: tuple[str, ...] = ()
    """The components the type compares without case, which a parser lowercases."""

    qualifiers: tuple[str, ...] = ()
    """The keys of the qualifiers a pURL of the type requires."""


PURL_TYPES: dict[str, PurlType] = {
    "alpm": PurlType("required", lowercase=("namespace", "name")),
    "apk": PurlType("required", lowercase=("namespace", "name")),
    "bazel": PurlType("prohibited"),
    "bitbucket": PurlType("required", lowercase=("namespace", "name")),
    "bitnami": PurlType("prohibited", lowercase=("name",)),
    "brew": PurlType("optional", lowercase=("namespace", "name")),
    "cargo": PurlType("prohibited"),
    "chrome-extension": PurlType("prohibited", lowercase=("name",)),
    "cocoapods": PurlType("prohibited"),
    "composer": PurlType("required", lowercase=("namespace", "name")),
    "conan": PurlType("optional"),
    "conda": PurlType("prohibited"),
    "cpan": PurlType("optional"),
    "cran": PurlType("prohibited"),
    "deb": PurlType("required", lowercase=("namespace", "name")),
    "docker": PurlType("optional"),
    "gem": PurlType("prohibited"),
    "generic": PurlType("optional"),
    "git": PurlType("required"),
    "github": PurlType("required", lowercase=("namespace", "name")),
    "golang": PurlType("required"),
    "hackage": PurlType("prohibited"),
    "hex": PurlType("optional", lowercase=("namespace", "name")),
    "huggingface": PurlType("required", lowercase=("version",)),
    "julia": PurlType("prohibited", qualifiers=("uuid",)),
    "luarocks": PurlType("optional", lowercase=("namespace", "name")),
    "maven": PurlType("required"),
    "mlflow": PurlType("prohibited"),
    "npm": PurlType("optional"),
    "nuget": PurlType("prohibited"),
    "oci": PurlType("prohibited", lowercase=("name", "version")),
    "opam": PurlType("prohibited"),
    "otp": PurlType("prohibited", lowercase=("name",)),
    "pub": PurlType("prohibited", lowercase=("name",)),
    "pypi": PurlType("prohibited", lowercase=("name", "version")),
    "qpkg": PurlType("required", lowercase=("namespace",)),
    "rpm": PurlType("required", lowercase=("namespace",)),
    "swid": PurlType("optional", qualifiers=("tag_id",)),
    "swift": PurlType("required"),
    "vcpkg": PurlType("prohibited"),
    "vscode-extension": PurlType(
        "required", lowercase=("namespace", "name", "version")
    ),
    "yocto": PurlType("optional", lowercase=("namespace",)),
}
"""The registered pURL types, with the rules their definitions state.

Taken from the
[type definitions of purl-spec `v1.1.0`](https://github.com/package-url/purl-spec/tree/v1.1.0/types).
`tests/purl-spec/` holds a copy of them, and `tests/test_purl_spec.py` checks this
table against it.

Clause 5.7 of ECMA-427 2nd edition makes a pURL invalid when it breaks the rules
of its registered type. A pURL of a type outside this table is valid when its
syntax is.
"""

_CHROME_EXTENSION_NAME = re.compile(r"[a-p]{32}")
"""A Chrome extension ID: 32 letters from `a` to `p`."""

_CHROME_EXTENSION_VERSION = re.compile(r"\d+(\.\d+){0,3}")
"""A Chrome extension version: one to four integers, joined with dots."""


class PurlRuleError(ValueError):
    """A pURL with a valid syntax, which breaks a rule of the specification.

    {func}`parse_purl` raises it for a rule of a registered type, and for a
    qualifier key not in lowercase.
    """


def purl_parts(package_id: str) -> tuple[str | None, str]:
    """Split `package_id` into the namespace and the name of its pURL.

    Everything before the last slash is the namespace. The whole ID stays the name
    when the split would leave an empty segment, like an absolute path or a URL: a
    pURL parser drops empty segments, so the ID would not read back.

    {data}`PURL_QUALIFYING_NAMESPACES` plays no part here. A pURL mpm writes carries a
    manager ID as its type, and the managers whose ID is one of those types (`apk`,
    `cpan`, `luarocks`) never put a slash in a package ID, which
    `tests/test_docstring_corpus.py` holds across every documented package ID.
    """
    namespace, _, name = package_id.rpartition("/")
    if not namespace or not name or "" in namespace.split("/"):
        return None, package_id
    return namespace, name


def manager_purl(manager_id: str, package_id: str, version: str | None = None) -> str:
    """Render the pURL tying `package_id` to `manager_id`, the manager ID as its type.

    {meth}`~meta_package_manager.specifier.Specifier.parse_purl` reads it back to the
    same manager ID, package ID and version, so a command handed this pURL skips
    looking the package up.

    Rendered here, not by packageurl-python, which the default install does not carry.
    Its `PackageURL.to_string()` would also lowercase the name of some types, npm among
    them ([package-url/packageurl-python#230](https://github.com/package-url/packageurl-python/issues/230)),
    where the npm type definition keeps names case-sensitive, since packages
    published before 2015 may carry uppercase letters: `JSONStream` would come back as
    `jsonstream`. And it leaves a `/` unencoded in a name
    ([package-url/packageurl-python#123](https://github.com/package-url/packageurl-python/pull/123)).
    """
    namespace, name = purl_parts(package_id)
    return _encode_purl(manager_id, namespace, name, version)


def purl_quote(text: str) -> str:
    """Percent-encode one pURL segment, a `/` included, keeping `:` as is."""
    return quote(text, safe="").replace("%3A", ":")


class PurlParts(NamedTuple):
    """The parts of a pURL string that `mpm` reads, as {func}`parse_purl` splits them.

    Each part is percent-decoded, and normalized by the rules of its registered type.
    """

    type: str
    """The pURL type, lowercased."""

    namespace: str | None
    """The segments before the name, joined with `/`, or `None` without any."""

    name: str
    """The last segment of the path."""

    version: str | None
    """What follows the last `@`, or `None` without one."""


def parse_purl(purl: str, *, strict: bool = True) -> PurlParts:
    """Split `purl` into its parts, or raise {exc}`ValueError` if it is not a pURL.

    Refuses a string without the `pkg:` scheme, without a type or with a malformed
    one, without a name, or with a qualifier missing its `=` or carrying a malformed
    key. Takes the leading `@` of an `npm` path as the start of its scope. Splits off
    the qualifiers and the subpath with {func}`urllib.parse.urlsplit`: `mpm` reads
    neither, but for the rules below.

    Each part comes back percent-decoded, and normalized by the rules of its type in
    {data}`PURL_TYPES`: a part the type compares without case is lowercased. The type
    definitions state some rules in prose only, which the purl-spec test suite checks.
    A `pypi` name turns `_` into `-`. A `git` name is the whole repository path after
    the host. An `mlflow` name is lowercased when its `repository_url` is on
    Databricks.

    In `strict` mode, raises {exc}`PurlRuleError` for a pURL breaking the rules of
    its type: a namespace the type requires or prohibits, or a qualifier it requires.
    So does a `cpan` name holding `::`, a `chrome-extension` name other than 32 letters
    from `a` to `p` or a version of more than four numbers, a `swift` namespace
    without both the host and the owner, and a qualifier key not in lowercase. Outside
    `strict` mode, such a pURL comes back like a valid one.

    `tests/test_purl_spec.py` runs the purl-spec test suite against it.
    """
    if not purl.strip():
        msg = "A pURL string is required."
        raise ValueError(msg)
    scheme, sep, remainder = purl.partition(":")
    if not sep or scheme != "pkg":
        msg = f'pURL is missing the required "pkg" scheme component: {purl!r}.'
        raise ValueError(msg)
    purl_type, sep, remainder = remainder.strip().lstrip("/").partition("/")
    if not purl_type or not sep:
        msg = f"pURL is missing the required type component: {purl!r}."
        raise ValueError(msg)
    if not set(purl_type) <= _PURL_KEY_CHARS or purl_type[0] in string.digits:
        msg = f"pURL type is not valid: {purl_type!r}."
        raise ValueError(msg)
    purl_type = purl_type.lower()

    url_scheme, authority, path, query, _ = urlsplit(remainder)
    # `urlsplit()` reads a colon as the end of a scheme or an authority, where a
    # pURL allows one in its namespace and name: put the colons back.
    if authority:
        path = f"{authority}:{path}"
    if url_scheme:
        # `urlsplit()` lowercases the scheme, so take it from the string.
        path = f"{remainder.split(':', 1)[0]}:{path}"
    path = path.lstrip("/")

    namespace = ""
    if purl_type == "npm" and path.startswith("@"):
        namespace, _, path = path.partition("/")
    rest, sep, version = path.rpartition("@")
    if not sep:
        rest, version = version, ""

    segments = [seg for seg in rest.strip().strip("/").split("/") if seg.strip()]
    name = ""
    if not namespace and len(segments) > 1:
        # The name of a `git` pURL is the repository path after the host.
        split = 1 if purl_type == "git" else -1
        namespace = "/".join(segments[:split])
        name = "/".join(segments[split:])
    elif len(segments) == 1:
        name = segments[0]
    if not name:
        msg = f"pURL is missing the required name component: {purl!r}."
        raise ValueError(msg)

    qualifiers, keys = _purl_qualifiers(query)
    namespace = "/".join(map(unquote, namespace.split("/"))) if namespace else ""
    name = "/".join(map(unquote, name.split("/")))
    version = unquote(version)

    namespace, name, version = _normalize_purl_parts(
        purl_type, namespace, name, version, qualifiers
    )

    if strict:
        problem = _purl_rule_problem(purl_type, namespace, name, version, qualifiers)
        if any(key != key.lower() for key in keys):
            problem = "takes its qualifier keys in lowercase"
        if problem:
            msg = f"A {purl_type} pURL {problem}: {purl!r}."
            raise PurlRuleError(msg)
    return PurlParts(purl_type, namespace or None, name, version or None)


def render_purl(
    purl_type: str,
    namespace: str | None,
    name: str,
    version: str | None = None,
    qualifiers: dict[str, str] | None = None,
    subpath: str | None = None,
) -> str:
    """Render the canonical pURL string of its parts, or raise {exc}`ValueError`.

    The reverse of {func}`parse_purl` in strict mode: normalizes the parts by the rules
    of their type, and refuses those breaking a rule with {exc}`PurlRuleError`.
    Percent-encodes each segment of the namespace and the subpath, the name, the
    version and each qualifier value, keeping `:`. Sorts the qualifiers by key and
    drops those without a value, and drops the `.` and `..` segments of the subpath.

    `tests/test_purl_spec.py` runs the build cases of the purl-spec test suite against
    it.
    """
    if (
        not purl_type
        or not set(purl_type) <= _PURL_KEY_CHARS
        or purl_type[0] in string.digits
    ):
        msg = f"pURL type is not valid: {purl_type!r}."
        raise ValueError(msg)
    purl_type = purl_type.lower()
    if not name:
        msg = "pURL is missing the required name component."
        raise ValueError(msg)
    qualifiers = {key: value for key, value in (qualifiers or {}).items() if value}
    for key in qualifiers:
        if not key or not set(key) <= _PURL_KEY_CHARS or key[0] in string.digits:
            msg = f"pURL qualifier key is not valid: {key!r}."
            raise ValueError(msg)
    namespace, name, version = _normalize_purl_parts(
        purl_type, namespace or "", name, version or "", qualifiers
    )
    problem = _purl_rule_problem(purl_type, namespace, name, version, qualifiers)
    if any(key != key.lower() for key in qualifiers):
        problem = "takes its qualifier keys in lowercase"
    if problem:
        msg = f"A {purl_type} pURL {problem}."
        raise PurlRuleError(msg)
    return _encode_purl(purl_type, namespace, name, version, qualifiers, subpath)


def _encode_purl(
    purl_type: str,
    namespace: str | None,
    name: str,
    version: str | None = None,
    qualifiers: dict[str, str] | None = None,
    subpath: str | None = None,
) -> str:
    """Join the parts of a pURL into its string, percent-encoding each of them."""
    segments = namespace.split("/") if namespace else []
    # The name of a `git` pURL is a repository path, which keeps its slashes.
    segments += name.split("/") if purl_type == "git" else [name]
    purl = f"pkg:{purl_type}/{'/'.join(map(purl_quote, segments))}"
    if version:
        purl += f"@{purl_quote(version)}"
    if qualifiers:
        purl += "?" + "&".join(
            f"{key}={purl_quote(value)}" for key, value in sorted(qualifiers.items())
        )
    subpath_segments = [
        segment
        for segment in (subpath or "").split("/")
        if segment not in ("", ".", "..")
    ]
    if subpath_segments:
        purl += "#" + "/".join(map(purl_quote, subpath_segments))
    return purl


def _normalize_purl_parts(
    purl_type: str,
    namespace: str,
    name: str,
    version: str,
    qualifiers: dict[str, str],
) -> tuple[str, str, str]:
    """Normalize the decoded namespace, name and version of a pURL by its type."""
    rules = PURL_TYPES.get(purl_type)
    if rules:
        if "namespace" in rules.lowercase:
            namespace = namespace.lower()
        if "name" in rules.lowercase:
            name = name.lower()
        if "version" in rules.lowercase:
            version = version.lower()
    if purl_type == "pypi":
        name = name.replace("_", "-")
    elif purl_type == "mlflow":
        host = urlsplit(qualifiers.get("repository_url", "")).hostname or ""
        if host.endswith("azuredatabricks.net"):
            name = name.lower()
    return namespace, name, version


def _purl_qualifiers(query: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Read the qualifiers of a pURL, or raise {exc}`ValueError` for a malformed one.

    Returns the qualifiers by lowercased key, their values percent-decoded, and the
    keys as written. A pair with an empty key or value is dropped, not refused.
    """
    qualifiers: dict[str, str] = {}
    keys: list[str] = []
    if not query:
        return qualifiers, ()
    pairs = [pair.partition("=") for pair in query.split("&")]
    if any(not sep for _, sep, _ in pairs):
        msg = f"pURL qualifiers must be key=value pairs: {query!r}."
        raise ValueError(msg)
    for raw_key, _, value in pairs:
        key = raw_key.strip()
        if not key or not value.strip():
            continue
        if not set(key) <= _PURL_KEY_CHARS or key[0] in string.digits:
            msg = f"pURL qualifier key is not valid: {key.lower()!r}."
            raise ValueError(msg)
        keys.append(key)
        qualifiers[key.lower()] = unquote(value)
    return qualifiers, tuple(keys)


def _purl_rule_problem(
    purl_type: str,
    namespace: str,
    name: str,
    version: str,
    qualifiers: dict[str, str],
) -> str | None:
    """Say which rule of its registered type a pURL breaks, or `None` for none."""
    rules = PURL_TYPES.get(purl_type)
    if not rules:
        return None
    if rules.namespace == "required" and not namespace:
        return "requires a namespace"
    if rules.namespace == "prohibited" and namespace:
        return "prohibits a namespace"
    for key in rules.qualifiers:
        if key not in qualifiers:
            return f"requires the {key} qualifier"
    if purl_type == "cpan" and "::" in name:
        return "names a distribution, which holds no '::'"
    if purl_type == "chrome-extension":
        if not _CHROME_EXTENSION_NAME.fullmatch(name):
            return "names an extension ID of 32 letters from a to p"
        if version and not _CHROME_EXTENSION_VERSION.fullmatch(version):
            return "takes a version of one to four numbers"
    if purl_type == "swift" and "/" not in namespace:
        return "takes the host and the owner as its namespace"
    return None


@dataclass
class Package:
    """Lightweight representation of a package and its metadata."""

    id: str
    """ID is required and is the primary key used by the manager."""

    manager_id: str
    """Handy to backtrack whose manager this package belongs to.

    The manager ID is good enough and allows for no coupling with the parent manager
    object.
    """

    name: str | None = None
    """Optional human-readable display name. Falls back to `id` in output rendering,
    so only set this when the manager provides a name that differs from the package ID.
    """

    description: str | None = None

    installed_version: TokenizedString | str | None = None
    latest_version: TokenizedString | str | None = None
    """Installed and latest versions are optional: they're not always provided by the
    package manager.

    `installed_version` and `latest_version` are allowed to temporarily be strings
    between `__init__` and `__post_init__`. Once they reach the later, they're
    parsed and normalized into either `TokenizedString` or `None`. They can't be
    strings beyond that point, i.e. after the Package instance has been fully
    instantiated. We don't know how to declare this transient state with type hints,
    so we're just going to allow string type.
    """

    arch: str | None = None

    def __post_init__(self) -> None:
        # Make sure version strings are parsed into proper objects.
        self.installed_version = parse_version(self.installed_version)  # type: ignore[arg-type]
        self.latest_version = parse_version(self.latest_version)  # type: ignore[arg-type]

    @staticmethod
    @lru_cache(maxsize=64)
    def query_parts(query: str) -> frozenset[str]:
        """Split `query` into its contiguous alphanumeric segments.

        Contrary to {class}`meta_package_manager.version.TokenizedString`,
        does not split on collated number/alphabetic junctions.

        Canonical tokenizer behind {meth}`matches` and the
        `search`/`installed`/`outdated` query matching. Cached, since a run
        asks it the same question once per package of every manager.
        """
        return frozenset(p for p in re.split(r"\W+", query) if p)

    def matches(
        self,
        query: str,
        extended: bool = False,
        exact: bool = False,
    ) -> bool:
        """Tell whether this package matches the free-form `query`.

        Shared predicate behind the `search`, `installed` and `outdated`
        subcommands, so all three honor the same matching semantics:

        - **Fuzzy** (default): a case-insensitive, tokenized substring match.
          Any alphanumeric segment of `query` (see {meth}`query_parts`)
          found in the package ID or name counts as a match.
        - **Exact** (`exact=True`): the raw `query` must equal the package
          ID or name verbatim (case-sensitive, whole-string).
        - **Extended** (`extended=True`): also look into the package
          `description`. Only meaningful when the description is populated,
          as it is for `search` results.

        A query with no alphanumeric segment (empty or punctuation-only) never
        matches.
        """
        # Look by default into package ID and name.
        content = {self.id, self.name}

        # Reject fuzzy results: only keep packages strictly matching ID or name.
        if exact and query not in content:
            return False

        # Add description to the content to look into.
        if extended:
            content.add(self.description)

        serialized_content = "".join(s.lower() for s in content if s)
        return any(
            part.lower() in serialized_content for part in self.query_parts(query)
        )


def packages_asdict(packages: Iterable[Package], keep_fields: tuple[str, ...]):
    """Yield each package as a `dict` holding the `keep_fields` subset of its fields.

    The fields are read straight off the instance rather than through
    {func}`dataclasses.asdict`, which deep-copies every value: a version is an
    immutable {class}`~meta_package_manager.version.TokenizedString` that the
    renderers only read, and copying thousands of them per query cost more than
    the query's own parsing.
    """
    return ({field: getattr(p, field) for field in keep_fields} for p in packages)


class DependencyScope(StrEnum):
    """Maps loosely onto SPDX `RelationshipType` variants.

    SBOM renderers translate these into `RUNTIME_DEPENDENCY_OF`,
    `BUILD_DEPENDENCY_OF`, etc.; CycloneDX collapses everything to its
    flat `dependencies` graph. Future non-SBOM consumers can apply
    their own mapping or just expose the raw scope label.
    """

    RUNTIME = "runtime"
    BUILD = "build"
    DEV = "dev"
    OPTIONAL = "optional"
    TEST = "test"
    RECOMMENDED = "recommended"


class ChecksumAlgorithm(StrEnum):
    """Subset of algorithms shared by SPDX and CycloneDX schemas.

    Used by {class}`Checksum` to identify a content hash without
    coupling the data model to any specific SBOM library's enum.
    """

    MD5 = "MD5"
    SHA1 = "SHA1"
    SHA256 = "SHA256"
    SHA512 = "SHA512"
    SHA3_256 = "SHA3-256"
    SHA3_512 = "SHA3-512"
    BLAKE2B_256 = "BLAKE2b-256"
    BLAKE2B_512 = "BLAKE2b-512"


@dataclass(frozen=True)
class Checksum:
    """A single `(algorithm, value)` pair."""

    algorithm: ChecksumAlgorithm
    value: str


@dataclass(frozen=True)
class Supplier:
    """Distributor of the package.

    Distinct from the originator: the supplier is whoever served the bits
    (Homebrew, Debian, PyPI), the originator is the upstream author.
    """

    name: str
    url: str | None = None


@dataclass(frozen=True)
class Originator:
    """Upstream author or organization that produced the package."""

    name: str
    email: str | None = None
    is_organization: bool = False


@dataclass(frozen=True)
class Dependency:
    """A single edge in the package's declared dependency graph.

    `target_id` is the dependency's manager-native identifier (e.g.
    `openssl@3` for Homebrew). Renderers match it against the inventory's
    installed packages to decide whether to emit a relationship.
    """

    target_id: str
    scope: DependencyScope = DependencyScope.RUNTIME
    version_constraint: str | None = None


@dataclass(frozen=True)
class FileEntry:
    """An installed file shipped by the package.

    Only populated for managers that can cheaply enumerate file contents and
    hashes (dpkg `.md5sums`, pip `RECORD`). Omitted otherwise; the SBOM
    renderer leaves `filesAnalyzed=False` on the SPDX Package.
    """

    path: str
    sha256: str | None = None
    sha1: str | None = None
    md5: str | None = None


@dataclass
class PackageMetadata:
    """Maximalist metadata collected for a single installed package.

    Distinct from {class}`Package` in scope: where `Package` carries
    only what the package manager itself surfaces through its inventory
    commands (id, name, version, arch), `PackageMetadata` carries the
    augmentations gathered through extra queries (richer CLI sub-commands,
    on-disk parsing of dist-info or per-package SBOMs, upstream registry
    lookups). Today it powers the maximalist `mpm sbom --bundled`
    output; the structure is deliberately generic so a future search,
    audit, or info display can reuse it.

    All fields are optional. `extras` is the escape hatch for manager-
    native fields that don't fit the portable model: a Homebrew tap, a pip
    classifier list, an apt `Section`. SBOM renderers consult known
    keys and surface the rest as CycloneDX `properties`.
    """

    download_url: str | None = None
    homepage: str | None = None
    vcs_url: str | None = None
    issue_tracker_url: str | None = None
    distribution_url: str | None = None

    license_declared: str | None = None
    license_concluded: str | None = None
    copyright_text: str | None = None

    supplier: Supplier | None = None
    originator: Originator | None = None

    description: str | None = None
    summary: str | None = None
    cpe: str | None = None

    dependencies: tuple[Dependency, ...] = ()
    checksums: tuple[Checksum, ...] = ()
    files: tuple[FileEntry, ...] = ()
    files_analyzed: bool = False

    install_date: datetime | None = None
    build_date: datetime | None = None
    release_date: datetime | None = None

    external_sbom_path: Path | None = None
    """Path to an on-disk upstream SBOM document for this package.

    Brew formulae installed with `HOMEBREW_SBOM=1` write a per-formula
    SPDX 2.3 file at `<prefix>/sbom.spdx.json`. The Homebrew extractor
    sets this so the SBOM renderer can merge the upstream document into
    the aggregate output (or attach it by reference).
    """

    extra_purls: tuple[str, ...] = ()
    """Additional purls when the manager identifies the same package
    through multiple coordinate systems (multi-arch, multi-origin, or the
    upstream registry a recipe builds from).

    SBOM renderers emit them as extra package-manager references and index
    them as aliases of the package's own purl, so a vulnerability scan can
    query a coordinate an advisory database recognizes. Each is a string
    {func}`parse_purl` accepts, which the renderers normalize with
    packageurl-python.
    """

    extras: dict[str, object] = field(default_factory=dict)
    """Manager-native metadata that does not map cleanly to portable
    fields. SBOM renderers may surface entries as CycloneDX `properties`.
    """

    def is_empty(self) -> bool:
        """`True` if the extractor produced no meaningful metadata.

        Used by the SBOM renderers to short-circuit field-by-field gating
        and by the CLI to log which managers contributed enrichment.
        """
        return (
            not self.download_url
            and not self.homepage
            and not self.vcs_url
            and not self.issue_tracker_url
            and not self.distribution_url
            and not self.license_declared
            and not self.license_concluded
            and not self.copyright_text
            and self.supplier is None
            and self.originator is None
            and not self.description
            and not self.summary
            and not self.cpe
            and not self.dependencies
            and not self.checksums
            and not self.files
            and self.install_date is None
            and self.build_date is None
            and self.release_date is None
            and self.external_sbom_path is None
            and not self.extra_purls
            and not self.extras
        )


EMPTY_METADATA = PackageMetadata()
"""Sentinel returned by the default no-op extractor on the base
{class}`meta_package_manager.manager.PackageManager`. Consumers (the SBOM
renderers today) treat `EMPTY_METADATA` exactly like `--minimal` mode for
the package: no enrichment, no placeholders.
"""
