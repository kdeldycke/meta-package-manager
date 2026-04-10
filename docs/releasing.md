# {octicon}`rocket` Releasing

## Release pipeline

The release process is automated via reusable workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic). A push to `main` triggers the `release.yaml` workflow, which produces:

- Python source distributions (`.whl`, `.tar.gz`) uploaded to [PyPI](https://pypi.org/project/meta-package-manager/)
- Nuitka-compiled standalone binaries for Linux, macOS, and Windows (x64 and ARM64) attached to [GitHub Releases](https://github.com/kdeldycke/meta-package-manager/releases)
- A [Chocolatey package](https://community.chocolatey.org/packages/meta-package-manager) for Windows

All release artifacts are signed with [GitHub Artifact Attestations](https://docs.github.com/en/actions/security-guides/using-artifact-attestations-to-establish-provenance-for-builds) providing [SLSA v1 provenance](https://slsa.dev/spec/v1.0/).

The release PR must be merged via "Rebase and merge" (never squash). See the `repomatic-release` skill for the full mechanics.

## Chocolatey

The Chocolatey package is maintained in-tree at `packaging/meta-package-manager/`, unlike Homebrew, Scoop, NixOS, and AUR which are maintained externally. The `chocolatey` job in `release.yaml` runs after the main release, downloads the Windows binaries, computes SHA256 checksums, and pushes the `.nupkg` to https://push.chocolatey.org/.

Chocolatey moderation then validates the package, which includes automated virus scanning (see below).

## Antivirus false positives on Windows binaries

Nuitka `--onefile` Windows x64 binaries are systematically flagged by antivirus engines on VirusTotal. This is a structural issue with the Nuitka compilation model, not a sign of actual malware.

### Why it happens

Nuitka `--onefile` creates a self-extracting archive that decompresses an embedded Python runtime to a temporary directory and executes it at launch. This "drop and execute from temp" pattern is behaviorally identical to trojan droppers, which triggers heuristic and ML-based detections.

Additional factors:
- Nuitka is popular with malware authors for source code protection, which poisons AV heuristics for all Nuitka-compiled binaries.
- `mpm` invokes external system commands (package managers), triggering behavioral rules for command-and-control activity.
- Microsoft has gone as far as [suspending an Artifact Signing account](https://github.com/Nuitka/Nuitka/issues/3842) over Nuitka onefile binaries.

### Typical detection profile

Based on the `v6.2.1` release (scanned 2026-04-10):

| Platform | Detection rate | VT reports | Notes |
|---|---|---|---|
| Linux x64 | 0/62 | | Clean |
| Linux ARM64 | 0/60 | | Clean |
| macOS x64 | 0-1/63 | | Occasional ML false positive |
| macOS ARM64 | 2/55-60 | [`meta-package-manager`](https://www.virustotal.com/gui/file/61c7a27f13b3c5a1f6cd079362c51880af9f1a945b6e3ec59ee3e5951efae1b0), [`mpm`](https://www.virustotal.com/gui/file/3369b48aed98d4ddedcf3e414f4fbf2e4fd8560ec1195b8c0ff5f41765e4bbd5) | Cynet, Microsoft ML, Avast/AVG |
| Windows ARM64 | 1/68-70 | [`meta-package-manager`](https://www.virustotal.com/gui/file/ebd0e35a09da7b496127aeca5669c2c5b1ab1e74c4f529ae050672850e8f627f), [`mpm`](https://www.virustotal.com/gui/file/136d9410d3887b1023e30f9e31f6e3d054d117ebd08cf50d7d8f83f87a3c6b39) | Fewer ARM64 heuristics in AV engines |
| **Windows x64** | **33-35/70** | [**`meta-package-manager`**](https://www.virustotal.com/gui/file/5435366a1bdd6790074caacd1c5b4a9d22d28e996671d0a432b399d06762707e), [**`mpm`**](https://www.virustotal.com/gui/file/3edbaf472a6a154db6c2f9f33f935737eeead50a8a7159612ebe0ba930d3a47f) | Heavily flagged by heuristic/ML engines |
| `.whl` / `.tar.gz` | 0/56-63 | | Clean (Python source, no Nuitka) |

The Windows x64 detections come from generic signatures like `Gen:Variant.Application.tedy` (BitDefender family), [`Trojan:Win32/Sabsik`](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?Name=Trojan:Win32/Sabsik.EN.A!ml&threatId=-2147156305) (Microsoft), `Python/Packed.Nuitka.AL` (ESET), and various ML-based classifiers.

### Submitting false positive reports

After each release, if VirusTotal detections are high, submit false positive reports to the major vendors. Priority order by impact:

1. **Microsoft** (https://www.microsoft.com/en-us/wdsi/filesubmission): most influential engine. Covers `Sabsik`, `Wacatac` detections. Turnaround: 1-2 business days.
2. **BitDefender** (https://www.bitdefender.com/submit/): their engine powers ~6 downstream vendors (ALYac, Arcabit, Emsisoft, GData, MicroWorld-eScan, VIPRE). Fixing BitDefender removes the most detections per submission.
3. **ESET** (email `samples@eset.com`, files in password-protected ZIP with password `infected`): covers `Python/Packed.Nuitka.AL`. Turnaround: 1-3 business days.
4. **Symantec** (https://symsubmit.symantec.com/false_positive): covers `ML.Attribute.HighConfidence`. ML-based detections may take longer (3-7 business days).
5. **Avast/AVG** (https://www.avast.com/submit-a-sample): shared engine, one submission covers both. Covers `Win64:Malware-gen`.
6. **Sophos** (https://support.sophos.com/support/s/filesubmission): covers `Generic Reputation PUA`. PUA submissions require justification of the software's legitimate purpose. Turnaround: up to 15 business days.

A complete list of vendor FP contacts is maintained by [VirusTotal](https://docs.virustotal.com/docs/false-positive-contacts) and [False-Positive-Center](https://github.com/yaronelh/False-Positive-Center).

### Impact on Chocolatey

Chocolatey's moderation pipeline includes automated virus scanning. A high VirusTotal detection count on the Windows binaries can block package validation. Reducing the count via FP submissions (or waiting for vendors to update their signatures) may be necessary before Chocolatey validation passes.

### Long-term mitigations

- **Code signing with an EV certificate** would reduce heuristic detections across the board, especially from Microsoft and Symantec ML models.
- **Switching from `--onefile` to `--standalone`** would eliminate the self-extracting pattern entirely, at the cost of distributing a directory instead of a single `.exe`.
- **Nuitka Commercial** (https://nuitka.net/doc/commercial.html) claims proprietary AV-mitigation techniques but offers no guarantees.

### References

- Previous report: [#1157](https://github.com/kdeldycke/meta-package-manager/issues/1157)
- Nuitka issues: [Nuitka/Nuitka#2685](https://github.com/Nuitka/Nuitka/issues/2685), [Nuitka/Nuitka#2495](https://github.com/Nuitka/Nuitka/issues/2495), [Nuitka/Nuitka#2757](https://github.com/Nuitka/Nuitka/issues/2757), [Nuitka/Nuitka#3842](https://github.com/Nuitka/Nuitka/issues/3842)
