# {octicon}`verified` SBOM: Software Bill of Materials

```{admonition} Context
The [Log4Shell vulnerability](https://en.wikipedia.org/wiki/Log4Shell) debacle was a wake-up call for the industry. This dependency was deeply embedded in the legacy stack of companies and administrations. They all had huge difficulty to identify its presence, writing custom detection scripts and scanning their software artifacts.

As a response to this crisis, [SBOM tools have now became a category of their own](https://en.wikipedia.org/wiki/Software_supply_chain). To the point that [a US executive order has also been released](https://bidenwhitehouse.archives.gov/briefing-room/presidential-actions/2021/05/12/executive-order-on-improving-the-nations-cybersecurity/) to modernize cybersecurity practices and enforce the production of SBOM to track the software supply chain.
```

`mpm` can export the list of installed packages as a SBOM in two standards and multiple formats:

| Standard  | [SPDX](https://spdx.dev) | [CycloneDX](https://cyclonedx.org) |
| --------- | :----------------------: | :--------------------------------: |
| JSON      |            ✓             |                 ✓                  |
| XML       |            ✓             |                 ✓                  |
| YAML      |            ✓             |                                    |
| RDF XML   |            ✓             |                                    |
| TAG VALUE |            ✓             |                                    |

SBOM export is the compliance corner of `mpm`'s inventory exports: for re-installable snapshots see {doc}`dump`, and for ad-hoc JSON or CSV piping of a listing see {doc}`output-formats`.

For example:

```shell-session
$ mpm --brew --gem sbom --spdx --format yaml
info: User selection of managers by priority: > brew > gem
info: Managers dropped by user: None
info: Print SPDX export to <stdout>
info: Exporting packages from brew...
info: Exporting packages from gem...
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

## Scan mode: `--bundled` vs `--minimal`

`mpm sbom` defaults to **bundled mode**: every manager that knows how is queried for richer per-package metadata (license, supplier, homepage, declared dependencies, source URL, checksums), per-package upstream SBOM documents are merged into the aggregate, and the result lands in the rendered SPDX or CycloneDX document. Bundled mode is the default because the magic of `mpm sbom` is collapsing N different manager APIs into one self-contained file.

When I only need a fast inventory pass, the `--minimal` flag short-circuits the metadata extractors and produces today's bare output (name, version, purl):

```shell-session
$ mpm --brew sbom --minimal > inventory.spdx.json
```

Use `--minimal` for snapshot-style runs (cron jobs, drift detection) and `--bundled` (the default) for compliance, supply-chain audit, and vulnerability-scanner ingestion.

## Layered SBOMs: aggregate + per-package upstream

Some package managers now publish their own per-package SBOM documents. Homebrew, for example, writes `<prefix>/Cellar/<formula>/<version>/sbom.spdx.json` when a formula is installed under `HOMEBREW_SBOM=1` (added in `5.2.0`). These are full SPDX 2.3 documents with the formula's complete dependency closure, real download URLs, and bottle checksums.

`mpm sbom --bundled` discovers those files, **splices them into the aggregate document**, and records each one in `externalDocumentRefs` with its SHA1 so the merge is auditable. Transitive packages from the upstream document are renamed under a `SPDXRef-brew-<formula>-<dep>` namespace to avoid collisions across formulae that share dependencies.

For the same data in CycloneDX, the per-formula file is attached to its component via an `externalReferences[type=bom]` entry.

If `HOMEBREW_SBOM=1` was never set, the file does not exist and `mpm` falls back silently to `brew info --json=v2` for the same fields.

To get the deepest data possible:

```shell-session
$ HOMEBREW_SBOM=1 brew reinstall <formula>
$ mpm --brew sbom > deep.spdx.json
```

## Coverage matrix

| Manager  | License | Homepage | Download URL | Checksums | Dependency graph | Per-package SBOM |
| -------- | :-----: | :------: | :----------: | :-------: | :--------------: | :--------------: |
| Homebrew |    ✓    |    ✓     |      ✓       |     ✓     |        ✓         |    ✓ (opt-in)    |
| pip      |    ✓    |    ✓     |              |           |        ✓         |                  |
| Others   |         |          |              |           |                  |                  |

Coverage will expand: every manager exposes its metadata differently, and richer extractors land per manager over time.

For the `license` column specifically, [Tern](https://github.com/tern-tools/tern) is a useful reference: a Python tool that derives per-package licenses across OS package managers and integrates ScanCode for file-level license detection, the data `mpm` would need to fill licenses beyond Homebrew and pip.

## How `mpm` compares to other SBOM tools

`mpm` is not the only tool that emits an SBOM. The widely-used ones each occupy a different spot in the supply-chain landscape:

| Tool                                                                    | By              | Language   | License          | What it reads                                              |     SPDX      | CycloneDX | purl       |
| :---------------------------------------------------------------------- | :-------------- | :--------- | :--------------- | :--------------------------------------------------------- | :-----------: | :-------: | :--------- |
| [`mpm`](https://github.com/kdeldycke/meta-package-manager)              | this project    | Python     | GPL-2.0-or-later | the live package managers on a host, queried directly      |     ✓ 2.3     |   ✓ 1.7   | ✓          |
| [Syft](https://github.com/anchore/syft)                                 | Anchore         | Go         | Apache-2.0       | container images and filesystems (package DBs, lockfiles)  |     ✓ 2.3     |   ✓ 1.6   | ✓          |
| [Trivy](https://github.com/aquasecurity/trivy)                          | Aqua Security   | Go         | Apache-2.0       | images, filesystems, repositories, VMs, clusters           |     ✓ 2.3     |   ✓ 1.5   | ✓          |
| [Tern](https://github.com/tern-tools/tern)                              | tern-tools      | Python     | BSD-2-Clause     | container image layers (runs package managers in a chroot) |       ✓       |     ✓     |            |
| [cdxgen](https://github.com/CycloneDX/cdxgen)                           | OWASP CycloneDX | JavaScript | Apache-2.0       | project manifests and lockfiles; a live host via `obom`    |     ✓ 3.0     |   ✓ 1.7   | ✓          |
| [component-detection](https://github.com/microsoft/component-detection) | Microsoft       | C#         | MIT              | source-tree manifests and lockfiles (~30 detectors)        | via sbom-tool |           | own schema |
| [sbom-tool](https://github.com/microsoft/sbom-tool)                     | Microsoft       | C#         | MIT              | build output and source tree (wraps component-detection)   |  ✓ 2.2, 3.0   |           |            |

Versions shown are each tool's current default; Syft and cdxgen can also emit older spec revisions on request. `mpm` is on the newest CycloneDX (1.7), and cdxgen and sbom-tool reach the newest SPDX (3.0). Tern's README states no spec versions or purl support for its output.

`mpm` differs from these tools in its data source, not its output format. Syft and Trivy read packages at rest: they parse the package databases already written into a container image or filesystem (the `dpkg`, `apk`, or `rpm` database, or a committed lockfile). cdxgen, component-detection, and sbom-tool parse a project's declared manifests and lockfiles.

`mpm` invokes the package managers' own command-line tools. It shells out to `brew`, `apt`, `pip`, `npm`, `cargo`, and the rest, and records what they report on the running host. That covers managers the file scanners do not model: Homebrew casks, `mas`, `flatpak`, `snap`, `mise`, and the others listed in {doc}`benchmark`. The trade-off is symmetric: `mpm` needs the managers installed and runnable, while Syft or Trivy can scan an image or directory the host never executed.

This invoke-the-real-tool approach is not unique to `mpm`. CycloneDX's own [cargo-cyclonedx](https://github.com/CycloneDX/cyclonedx-rust-cargo) invokes Cargo rather than only parsing `Cargo.lock`, and [Tern](https://github.com/tern-tools/tern) runs each container layer's package manager in a chroot rather than reading its on-disk database. Both reflect what the manager itself resolves. `mpm` applies that principle across every manager it drives, on the live host.

The tools are complementary. Reach for Syft, Trivy, or cdxgen to inventory a build artifact, container, or source repository; reach for `mpm sbom` to inventory the software actually installed on a machine.

## Installation

SBOM export is an optional extra. `pip install meta-package-manager` does not pull the CycloneDX and SPDX dependencies; install the `[sbom]` extra to enable the `mpm sbom` subcommand:

```shell-session
$ pip install meta-package-manager[sbom]
```

Or with `uv`:

```shell-session
$ uv tool install 'meta-package-manager[sbom]'
```

Without the extra, `mpm sbom` exits with an explanatory error pointing at this install step.

## See also

- {doc}`output-formats` — JSON and CSV table exports for ad-hoc piping of `installed`, `outdated`, and `search` results.
- {doc}`dump` — TOML manifest and Brewfile snapshots for re-installation workflows.
- {doc}`cooldown` — release-age gates that complement the SBOM workflow on the install side.

## `meta_package_manager.sbom` API

```{eval-rst}
.. automodule:: meta_package_manager.sbom.base
   :members:
   :show-inheritance:
   :undoc-members:

.. automodule:: meta_package_manager.sbom.cyclonedx
   :members:
   :show-inheritance:
   :undoc-members:

.. automodule:: meta_package_manager.sbom.spdx
   :members:
   :show-inheritance:
   :undoc-members:
```
