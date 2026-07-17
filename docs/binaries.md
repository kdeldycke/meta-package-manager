---
orphan: true
---

# Binaries

All standalone executables published by this repository, one row per binary, newest release first. The version links to its GitHub release, the platform to the direct binary download, and the VirusTotal cell to the file's public analysis.

Compiled Python binaries are regularly flagged by heuristic antivirus engines, so every release is submitted to [VirusTotal](https://www.virustotal.com/): this seeds vendor databases with the new signatures and keeps false positives in check. The VirusTotal cell tracks those false positives: a green check marks binaries no engine flags, and flagged binaries show the share of engine verdicts flagging them, snapshotted minutes after publication and before false-positive reports get processed. The live analysis behind the link supersedes it.

## Development builds

Fresh binaries are compiled from every push to the default branch by the [release workflow](https://github.com/kdeldycke/meta-package-manager/actions/workflows/release.yaml). To try the latest development build: open the most recent successful run and download the artifact matching your platform (a GitHub account is required, and the binary comes wrapped in a zip). The same builds are also attached to a rolling dev pre-release, a draft only visible to repository maintainers.

<!-- binaries-start -->

## VirusTotal detections

Share of antivirus engine verdicts flagging the binaries of each release, at scan time. Colors follow the catalog shields: green for zero detections, amber below 10%, red from there up.

```{raw} html
<div style="height: 320px;"><canvas id="vt-trend"></canvas></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.min.js"></script>
<script>
const VT_TREND = [{"date": "2026-05-04", "flagged": 30, "pct": 7.8, "tag": "v6.4.1", "total": 384}, {"date": "2026-05-11", "flagged": 26, "pct": 7.9, "tag": "v6.4.2", "total": 328}, {"date": "2026-05-11", "flagged": 30, "pct": 7.7, "tag": "v6.4.3", "total": 390}, {"date": "2026-05-25", "flagged": 5, "pct": 1.4, "tag": "v6.5.0", "total": 367}, {"date": "2026-05-28", "flagged": 10, "pct": 2.6, "tag": "v6.5.1", "total": 387}, {"date": "2026-06-17", "flagged": 23, "pct": 6.2, "tag": "v6.6.0", "total": 371}, {"date": "2026-06-26", "flagged": 16, "pct": 4.2, "tag": "v7.0.0", "total": 382}, {"date": "2026-06-27", "flagged": 15, "pct": 3.9, "tag": "v7.0.1", "total": 388}, {"date": "2026-07-07", "flagged": 15, "pct": 4.0, "tag": "v7.1.0", "total": 374}, {"date": "2026-07-09", "flagged": 20, "pct": 5.3, "tag": "v7.2.0", "total": 377}, {"date": "2026-07-17", "flagged": 20, "pct": 5.2, "tag": "v7.3.0", "total": 384}];
const VT_DANGER_PCT = 10;
const vtCss = getComputedStyle(document.documentElement);
const vtColor = (name, fallback) =>
    vtCss.getPropertyValue(name).trim() || fallback;
const vtTint = (p) => {
    if (p.pct === 0) { return vtColor("--sd-color-success", "#28a745"); }
    return p.pct >= VT_DANGER_PCT
        ? vtColor("--sd-color-danger", "#dc3545")
        : vtColor("--sd-color-warning", "#f0b37e");
};
new Chart(document.getElementById("vt-trend"), {
    type: "line",
    data: {
        datasets: [{
            data: VT_TREND.map((p) => ({x: Date.parse(p.date), y: p.pct})),
            borderColor: "#88888866",
            pointBackgroundColor: VT_TREND.map(vtTint),
            pointBorderColor: VT_TREND.map(vtTint),
            pointRadius: 4,
            tension: 0.2,
        }],
    },
    options: {
        maintainAspectRatio: false,
        plugins: {
            legend: {display: false},
            tooltip: {callbacks: {
                title: (items) => VT_TREND[items[0].dataIndex].tag,
                label: (item) => {
                    const p = VT_TREND[item.dataIndex];
                    return p.flagged + " / " + p.total
                        + " verdicts flagged (" + p.pct + "%)";
                },
            }},
        },
        scales: {
            x: {
                type: "linear",
                ticks: {
                    maxTicksLimit: 8,
                    callback: (value) =>
                        new Date(value).toISOString().slice(0, 10),
                },
            },
            y: {
                beginAtZero: true,
                title: {display: true, text: "Flagged verdicts (%)"},
            },
        },
    },
});
</script>
```

<!-- binaries-end -->

## Catalog

The table is searchable and sortable on the documentation site; the raw data lives in [`binaries.csv`](assets/binaries.csv).

```{csv-table}
:file: assets/binaries.csv
:header-rows: 1
:class: sphinx-datatable
```

## Antivirus false positives on Windows binaries

Nuitka `--onefile` Windows x64 binaries are systematically flagged by antivirus engines on VirusTotal. This is a structural issue with the Nuitka compilation model, not a sign of actual malware.

### Why it happens

The generic mechanics (Nuitka `--onefile`'s "drop and execute from temp" pattern reads as a trojan dropper, and AV heuristics are poisoned by malware authors using Nuitka) are documented in [repomatic's false-positive playbook](https://kdeldycke.github.io/repomatic/security.html#why-binaries-get-flagged). On top of that, `mpm` invokes external system commands (package managers), triggering behavioral rules for command-and-control activity.

### Typical detection profile

The [catalog above](#catalog) tracks the exact counts per release and platform. The recurring pattern: Linux binaries scan clean, macOS x64 sees an occasional ML false positive, macOS ARM64 picks up a couple of engines (Cynet, Microsoft ML, Avast/AVG), Windows ARM64 stays low (fewer ARM64 heuristics in AV engines), while **Windows x64 is heavily flagged** by heuristic and ML engines. The `.whl` and `.tar.gz` distributions scan clean (Python source, no Nuitka).

### Submitting false positive reports

After each release with high detections, submit false-positive reports to the major vendors. The [vendor portals, priority order, submission content, and long-term mitigations](https://kdeldycke.github.io/repomatic/security.html#vendor-portals) are maintained upstream, and the `av-false-positive` skill generates the per-vendor submission files with all details pre-filled.

### Impact on Chocolatey

Chocolatey's moderation pipeline rejects any package flagged by more than 10 antivirus engines on VirusTotal ([chocolatey/home#395](https://github.com/chocolatey/home/issues/395#issuecomment-4378555157)). The Windows x64 binary sits well above that threshold (see the [catalog](#catalog)), so [submission `6.4.2`](https://community.chocolatey.org/packages/meta-package-manager/6.4.2) was rejected and automated publishing to the community repository has been removed from `release.yaml`. Reaching the cutoff would require either lowering the detection count through false-positive submissions (a moving target) or applying one of the [long-term mitigations](https://kdeldycke.github.io/repomatic/security.html#long-term-mitigations).

### References

- Previous report: [#1157](https://github.com/kdeldycke/meta-package-manager/issues/1157)
