# {octicon}`shield-lock` SBOM: Software Bill of Materials

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
  supplier: 'Organization: Ruby Gems'
  versionInfo: 2.4.22
- SPDXID: SPDXRef-Package-gem-libxml-ruby
  downloadLocation: https://www.example.com
  filesAnalyzed: false
  name: libxml-ruby
  primaryPackagePurpose: INSTALL
  supplier: 'Organization: Ruby Gems'
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

- {doc}`dump` &mdash; TOML manifest and Brewfile snapshots for re-installation workflows.
- {doc}`cooldown` &mdash; release-age gates that complement the SBOM workflow on the install side.
