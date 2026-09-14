# {octicon}`verified` SBOM: Software Bill of Materials

```{admonition} Context
The [Log4Shell vulnerability](https://en.wikipedia.org/wiki/Log4Shell) was present in the legacy stack of many companies and administrations. They had trouble finding where it was installed, and wrote custom detection scripts to scan their software artifacts.

As a response, [SBOM tools became a category of their own](https://en.wikipedia.org/wiki/Software_supply_chain). A [US executive order](https://bidenwhitehouse.archives.gov/briefing-room/presidential-actions/2021/05/12/executive-order-on-improving-the-nations-cybersecurity/) now requires the production of an SBOM to track the software supply chain.
```

`mpm` can export the list of installed packages as an SBOM in two standards and multiple formats:

| Standard  | [SPDX](https://spdx.dev) | [CycloneDX](https://cyclonedx.org) |
| --------- | :----------------------: | :--------------------------------: |
| JSON      |            ✅            |                 ✅                 |
| XML       |            ✅            |                 ✅                 |
| YAML      |            ✅            |                                    |
| RDF XML   |            ✅            |                                    |
| TAG VALUE |            ✅            |                                    |

SBOM export is the compliance corner of `mpm`'s inventory exports. For re-installable snapshots, see {doc}`dump`. For ad-hoc JSON or CSV piping of a listing, see {doc}`output-formats`.

For example:

```shell-session
$ mpm --brew --gem sbom --spdx --format yaml
291 packages total (brew: 229, gem: 62).
229/291 packages enriched with metadata.
```

```yaml
SPDXID: SPDXRef-DOCUMENT
creationInfo:
  created: '2024-07-30T15:48:45Z'
  creators:
  - 'Tool: meta-package-manager-5.18.0'
dataLicense: CC0-1.0
documentNamespace: https://github.com/kdeldycke/meta-package-manager/releases/tag/v5.18.0/dd72ff542938a2d40620dc249e91e35
name: macOS-Darwin-23.6.0-arm64
packages:
- SPDXID: SPDXRef-Package-brew-curl
  downloadLocation: https://www.example.com
  filesAnalyzed: false
  name: curl
  primaryPackagePurpose: INSTALL
  supplier: 'Organization: Homebrew Formulae'
  versionInfo: 8.9.0
- SPDXID: SPDXRef-Package-brew-ffmpeg
  downloadLocation: https://www.example.com
  filesAnalyzed: false
  name: ffmpeg
  primaryPackagePurpose: INSTALL
  supplier: 'Organization: Homebrew Formulae'
  versionInfo: 7.0.1
- SPDXID: SPDXRef-Package-brew-xz
  downloadLocation: https://www.example.com
  filesAnalyzed: false
  name: xz
  primaryPackagePurpose: INSTALL
  supplier: 'Organization: Homebrew Formulae'
  versionInfo: 5.6.2
(...)
- SPDXID: SPDXRef-Package-gem-bundler
  downloadLocation: https://www.example.com
  filesAnalyzed: false
  name: bundler
  primaryPackagePurpose: INSTALL
  supplier: 'Organization: RubyGems'
  versionInfo: 2.4.22
- SPDXID: SPDXRef-Package-gem-libxml-ruby
  downloadLocation: https://www.example.com
  filesAnalyzed: false
  name: libxml-ruby
  primaryPackagePurpose: INSTALL
  supplier: 'Organization: RubyGems'
  versionInfo: 4.1.2
(...)
relationships:
- relatedSpdxElement: SPDXRef-Package-brew-curl
  relationshipType: DESCRIBES
  spdxElementId: SPDXRef-DOCUMENT
- relatedSpdxElement: SPDXRef-Package-brew-ffmpeg
  relationshipType: DESCRIBES
  spdxElementId: SPDXRef-DOCUMENT
- relatedSpdxElement: SPDXRef-Package-brew-xz
  relationshipType: DESCRIBES
  spdxElementId: SPDXRef-DOCUMENT
(...)
- relatedSpdxElement: SPDXRef-Package-gem-bundler
  relationshipType: DESCRIBES
  spdxElementId: SPDXRef-DOCUMENT
- relatedSpdxElement: SPDXRef-Package-gem-libxml-ruby
  relationshipType: DESCRIBES
  spdxElementId: SPDXRef-DOCUMENT
(...)
spdxVersion: SPDX-2.3
```

To export only a subset of the installed packages, filter with `--query`. The match is fuzzy by default: case-insensitive and tokenized, the same semantics as `mpm search`. Pass `--exact` for a verbatim match on the package ID or name:

```shell-session
$ mpm --brew sbom --query openssl > openssl.spdx.json
```

## Scan mode: `--bundled` vs `--minimal`

`mpm sbom` defaults to bundled mode. Every manager that can is queried for per-package metadata: license, supplier, homepage, declared dependencies, source URL, checksums. Per-package upstream SBOM documents are merged into the aggregate, and the result is written into the rendered SPDX or CycloneDX document. Bundled mode is the default because `mpm sbom` collapses N different manager APIs into one self-contained file.

The `--minimal` flag short-circuits the metadata extractors and produces the bare output (name, version, purl):

```shell-session
$ mpm --brew sbom --minimal > inventory.spdx.json
```

Use `--minimal` for snapshot-style runs (cron jobs, drift detection). Use `--bundled`, the default, for compliance, supply-chain audit, and vulnerability-scanner ingestion.

## Layered SBOMs: aggregate + per-package upstream

Some package managers now publish their own per-package SBOM documents. Homebrew, for example, writes `<prefix>/Cellar/<formula>/<version>/sbom.spdx.json` on every source install. These are full SPDX 2.3 documents with the formula's complete dependency closure, real download URLs, and bottle checksums. `HOMEBREW_SBOM` was the opt-in that turned this on in `5.2.0`. Since `6.0.7` it is a hidden opt-out, so the files are there unless someone turned them off.

`mpm sbom --bundled` discovers those files and splices them into the aggregate document. Each one is recorded in `externalDocumentRefs` with its SHA1, so the merge is auditable. Transitive packages from the upstream document are renamed under a `SPDXRef-brew-<formula>-<dep>` namespace. This avoids collisions across formulae that share dependencies.

For the same data in CycloneDX, the per-formula file is attached to its component through an `externalReferences[type=bom]` entry.

Both formats also read one field out of the upstream document without merging it: the purl Homebrew derives from the formula's source URL. It names the package in its own registry. `mpm` indexes it as an alias of the formula's `pkg:brew/…` purl, which is what makes a formula scannable for vulnerabilities. See [§ Vulnerability scanning](#vulnerability-scanning).

The file can be missing: a `brew` older than `6.0.7`, a formula installed before it, a cask, or an opted-out install. There, `mpm` falls back to `brew info --json=v2` for the same fields. A reinstall writes one:

```shell-session
$ brew reinstall <formula>
$ mpm --brew sbom > deep.spdx.json
```

## Coverage matrix

| Capability         | [`brew`](managers/brew.md) | [`pip`](managers/pip.md) | [`npm`](managers/npm.md) | [`cargo`](managers/cargo.md) | [`gem`](managers/gem.md) | [`composer`](managers/composer.md) | Others |
| :----------------- | :-----------------------: | :----------------------: | :----------------------: | :--------------------------: | :----------------------: | :--------------------------------: | :----: |
| License            |            ✅             |            ✅             |                          |                              |                          |                                    |        |
| Homepage           |            ✅             |            ✅             |                          |                              |                          |                                    |        |
| Download URL       |            ✅             |                          |                          |                              |                          |                                    |        |
| Checksums          |            ✅             |                          |                          |                              |                          |                                    |        |
| Dependency graph   |            ✅             |            ✅             |                          |                              |                          |                                    |        |
| Per-package SBOM   |            ✅             |                          |                          |                              |                          |                                    |        |
| Vulnerabilities    |      ✅ (partial)         |      ✅ (`--network`)     |      ✅ (`--network`)     |        ✅ (`--network`)       |      ✅ (`--network`)     |          ✅ (`--network`)            |        |

Coverage will expand. Every manager exposes its metadata differently, and more extractors are added per manager over time.

The `Vulnerabilities` row tracks [OSV.dev's indexed ecosystems](https://ossf.github.io/osv-schema/#defined-ecosystems). A manager OSV does not index returns no advisories, and reports no error. That covers [`mas`](managers/mas.md), and the distro managers OSV needs a release qualifier for.

[`brew`](managers/brew.md) is the exception. OSV indexes no formula, but it does index the upstream package a formula builds from. Under `--network`, `mpm` queries that coordinate like the rest. Its cell is marked partial because only a formula built from a registry archive carries one.

For the `License` row, [Tern](https://github.com/tern-tools/tern) is a useful reference. It is a Python tool that derives per-package licenses across OS package managers, and it integrates ScanCode for file-level license detection. That is the data `mpm` would need to fill the `License` row beyond Homebrew and pip.

## How `mpm` compares to other SBOM tools

Other tools emit an SBOM too. Each reads a different part of the supply chain:

| Tool                                      | By              | Language   | License          | What it reads                                              |     SPDX      | CycloneDX |    purl    |
| :---------------------------------------- | :-------------- | :--------- | :--------------- | :--------------------------------------------------------- | :-----------: | :-------: | :--------: |
| `mpm`[^mpm]                               | this project    | Python     | GPL-2.0-or-later | the live package managers on a host, queried directly      |    ✅ 2.3     |  ✅ 1.7   |     ✅     |
| Syft[^syft]                               | Anchore         | Go         | Apache-2.0       | container images and filesystems (package DBs, lockfiles)  |    ✅ 2.3     |  ✅ 1.6   |     ✅     |
| Trivy[^trivy]                             | Aqua Security   | Go         | Apache-2.0       | images, filesystems, repositories, VMs, clusters           |    ✅ 2.3     |  ✅ 1.5   |     ✅     |
| Tern[^tern]                               | tern-tools      | Python     | BSD-2-Clause     | container image layers (runs package managers in a chroot) |      ✅       |    ✅     |            |
| cdxgen[^cdxgen]                           | OWASP CycloneDX | JavaScript | Apache-2.0       | project manifests and lockfiles; a live host via `obom`    |    ✅ 3.0     |  ✅ 1.7   |     ✅     |
| component-detection[^component-detection] | Microsoft       | C#         | MIT              | source-tree manifests and lockfiles (~30 detectors)        | via sbom-tool |           | own schema |
| sbom-tool[^sbom-tool]                     | Microsoft       | C#         | MIT              | build output and source tree (wraps component-detection)   |  ✅ 2.2, 3.0  |           |            |

Versions shown are each tool's current default. Syft and cdxgen can also emit older spec revisions on request. `mpm` is on the newest CycloneDX (1.7), and cdxgen and sbom-tool reach the newest SPDX (3.0). Tern's README states no spec versions or purl support for its output.

`mpm` differs from these tools in its data source. Syft and Trivy read packages at rest. They parse the package databases already written into a container image or filesystem: the `dpkg`, [`apk`](managers/apk.md), or `rpm` database, or a committed lockfile. cdxgen, component-detection, and sbom-tool parse a project's declared manifests and lockfiles.

`mpm` invokes the package managers' own command-line tools. It shells out to [`brew`](managers/brew.md), [`apt`](managers/apt.md), [`pip`](managers/pip.md), [`npm`](managers/npm.md), [`cargo`](managers/cargo.md), and the rest. It records what they report on the running host. That covers managers the file scanners do not model: Homebrew casks, [`mas`](managers/mas.md), [`flatpak`](managers/flatpak.md), [`snap`](managers/snap.md), [`mise`](managers/mise.md), and the others listed in {doc}`benchmark`.

The trade-off is symmetric. `mpm` needs the managers installed and runnable. Syft or Trivy can scan an image or a directory the host never executed.

This approach is not unique to `mpm`. CycloneDX's own [cargo-cyclonedx](https://github.com/CycloneDX/cyclonedx-rust-cargo) invokes Cargo instead of only parsing `Cargo.lock`. [Tern](https://github.com/tern-tools/tern) runs each container layer's package manager in a chroot instead of reading its on-disk database. Both reflect what the manager itself resolves. `mpm` applies that principle across every manager it drives, on the live host.

The tools are complementary. Reach for Syft, Trivy, or cdxgen to inventory a build artifact, a container, or a source repository. Reach for `mpm sbom` to inventory the software actually installed on a machine.

## Vulnerability scanning

By default `mpm sbom` works entirely offline. Pass the global `--network` flag to add known vulnerabilities to the document, looked up against [OSV.dev](https://osv.dev):

```shell-session
$ mpm --network sbom --cyclonedx > inventory.cdx.json
```

In CycloneDX output, each advisory appears once in the document's `vulnerabilities` array. It points, through `affects`, at every component it impacts. It carries the severity rating, the CVSS vector, the CWE ids, the aliases (the CVE behind a GHSA, for instance), and the advisory links.

SPDX 2.3 has no first-class vulnerability section. Each advisory is attached to its package as a `SECURITY`-category external reference of type `advisory`. The severity and fixed-version facts are folded into the reference comment.

Coverage tracks OSV's ecosystems. Language managers like pip, npm, cargo, gem, and composer resolve to OSV ecosystems and get scanned. A system manager's own coordinate is indexed nowhere, so its packages come back without advisories. Responses are cached on disk, under the OS user-cache directory, so repeat scans are fast and stay within OSV's rate limits.

[`brew`](managers/brew.md) reaches past that limit. Homebrew resolves each formula's source URL to the package's own registry and records the purl in that formula's `sbom.spdx.json`, across ten ecosystems from PyPI to CPAN. `mpm` reads it and queries OSV with it, then attributes whatever comes back to the formula. The ref first appeared in `6.0.18`, so a formula installed by an older `brew` carries none until it is reinstalled.

Only a formula built from a registry archive carries such a coordinate. That is a small share of any installation: 8 of the 246 formulae on the macOS host used to measure this. A formula built from a plain forge tarball stays unscanned for now.

Homebrew ships its own scanner, `brew vulns` (since `6.0.11`), reading the same OSV database. It covers the forge tarballs too, by querying OSV's `GIT` ecosystem with the repository URL and release tag. That reaches another 124 formulae on that same host. So run `brew vulns` for the most complete answer about Homebrew specifically. Run `mpm --network sbom` for one inventory spanning every manager on the machine.

Network failures do not stop the export. A missing extra, an unreachable OSV, or an unwritable cache logs a warning. The SBOM is still produced, without vulnerability data.

```{caution}
Running `--network` transmits the ecosystem coordinates of your installed packages (name, version, ecosystem) to OSV.dev. The offline default never makes network calls.
```

## Installation

SBOM export requires optional extras, split by usage:

- `[sbom-offline]` pulls the CycloneDX and SPDX writer libraries needed to render documents from local data. This is what `mpm sbom` needs for its default offline operation.
- `[sbom-online]` adds the HTTP client and cache used by `mpm --network sbom` for the OSV.dev vulnerability lookups described above.

```shell-session
$ uv tool install 'meta-package-manager[sbom-offline]'
```

For vulnerability scanning, install both:

```shell-session
$ uv tool install 'meta-package-manager[sbom-offline,sbom-online]'
```

Without `[sbom-offline]`, `mpm sbom` exits with an explanatory error pointing at this install step. Without `[sbom-online]`, the `--network` flag logs a warning and falls back to an offline document.

## See also

- {doc}`output-formats`: JSON and CSV table exports for ad-hoc piping of `installed`, `outdated`, `orphans`, and `search` results.
- {doc}`dump`: TOML manifest and Brewfile snapshots for re-installation workflows.
- {doc}`cooldown`: release-age gates that complement the SBOM workflow on the install side.

[^mpm]: [kdeldycke/meta-package-manager](https://github.com/kdeldycke/meta-package-manager)

[^syft]: [anchore/syft](https://github.com/anchore/syft)

[^trivy]: [aquasecurity/trivy](https://github.com/aquasecurity/trivy)

[^tern]: [tern-tools/tern](https://github.com/tern-tools/tern)

[^cdxgen]: [CycloneDX/cdxgen](https://github.com/CycloneDX/cdxgen)

[^component-detection]: [microsoft/component-detection](https://github.com/microsoft/component-detection)

[^sbom-tool]: [microsoft/sbom-tool](https://github.com/microsoft/sbom-tool)
