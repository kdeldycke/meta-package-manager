/* Shell-free logic of the Meta Package Manager GNOME Shell extension.
 *
 * This module is the GJS counterpart of the Xbar/SwiftBar plugin launcher
 * (meta_package_manager/bar_plugin.py): locate a runnable mpm, gate on a
 * minimum version, run `sync` then `outdated`, and build the commands behind
 * the menu actions. Rendering lives in extension.js.
 *
 * It deliberately imports only gi://Gio and gi://GLib, never any
 * resource:///org/gnome/shell/* module, so the whole file loads under a bare
 * `gjs -m` interpreter: the test suite drives every function below outside a
 * GNOME session (see tests/gnome/run-tests.js in the repository).
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

Gio._promisify(Gio.Subprocess.prototype, 'communicate_utf8_async');

export const MPM_MIN_VERSION = [6, 4, 0];
/* mpm 6.4.0 renamed `--output-format` back to `--table-format`, the flag this
 * extension relies on for the JSON payload of `outdated`. Everything else it
 * invokes (manager selectors, `upgrade --all`, `--no-color`, `--verbosity`,
 * `--timeout`, `sync`) predates that release. */

export const MPM_TIMEOUT = 60;
/* Default `--timeout` (seconds), mirroring bar_plugin.py: mpm's own defaults
 * are tuned for interactive runs and are too long for a background refresh. */

export const INSTALL_DOCS_URL =
    'https://kdeldycke.github.io/meta-package-manager/install.html';

const VERSION_REGEX = /\bversion\s+(\d+(?:\.\d+)+)/;

/* Well-known mpm locations probed when it is not on the session PATH, which
 * GNOME does not source from the user's shell profile. Mirrors the PATH tier
 * of bar_plugin.py's search_mpm(); the venv walk-back tiers make no sense
 * here since the extension does not live inside a Python project tree. */
function fallbackPaths() {
    return [
        GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'mpm']),
        '/usr/local/bin/mpm',
        '/home/linuxbrew/.linuxbrew/bin/mpm',
    ];
}

/* Terminal emulators probed in order when no override is configured, each
 * with its own "run this argv" dialect. xdg-terminal-exec is the freedesktop
 * spec entry point (trailing args are the command argv); Ptyxis and Console
 * (kgx) are the modern GNOME terminals; gnome-terminal is the legacy
 * fallback. Console has no trailing-argv form: terminalArgv() gives it its
 * `--command` single-string dialect, keyed on the program name. */
export const TERMINAL_CANDIDATES = [
    ['xdg-terminal-exec'],
    ['ptyxis', '--'],
    ['kgx'],
    ['gnome-terminal', '--'],
];

/**
 * Resolve the mpm invocation to use, as an argv array.
 *
 * @param {string} override - The `mpm-command` setting, parsed with shell
 *   syntax so multi-word launchers like "uv run mpm" work. Empty means auto.
 * @returns {string[]|null} argv, or null when nothing is found.
 */
export function findMpm(override = '') {
    if (override) {
        try {
            const [ok, argv] = GLib.shell_parse_argv(override);
            if (ok && argv.length > 0)
                return argv;
        } catch {
            return null;
        }
        return null;
    }
    const onPath = GLib.find_program_in_path('mpm');
    if (onPath)
        return [onPath];
    for (const candidate of fallbackPaths()) {
        if (GLib.file_test(candidate, GLib.FileTest.IS_EXECUTABLE))
            return [candidate];
    }
    return null;
}

/**
 * Extract a version tuple from `mpm --no-color --version` output.
 *
 * @param {string} text - The command's stdout.
 * @returns {number[]|null} version components, or null when unparsable.
 */
export function parseVersion(text) {
    const match = VERSION_REGEX.exec(text ?? '');
    if (!match)
        return null;
    return match[1].split('.').map(Number);
}

/**
 * Compare two version tuples component-wise.
 *
 * @param {number[]} left - Version components.
 * @param {number[]} right - Version components.
 * @returns {number} negative, zero or positive.
 */
export function compareVersions(left, right) {
    const length = Math.max(left.length, right.length);
    for (let i = 0; i < length; i++) {
        const delta = (left[i] ?? 0) - (right[i] ?? 0);
        if (delta !== 0)
            return delta;
    }
    return 0;
}

/**
 * Run a command asynchronously and capture its output.
 *
 * @param {string[]} argv - Command to run.
 * @param {Gio.Cancellable|null} cancellable - Cancelled on extension disable.
 * @param {number} watchdogSeconds - Hard kill after this delay, 0 to disable.
 *   mpm's own `--timeout` only bounds each manager CLI it runs internally,
 *   not a wedged mpm process itself.
 * @returns {Promise<{status: number, stdout: string, stderr: string}>}
 */
export async function runCommand(argv, cancellable = null, watchdogSeconds = 0) {
    const proc = Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
    /* Cancelling communicate_utf8_async only abandons the read and leaves the
     * child running: hook the cancellable so the child is actually killed. */
    let cancelId = 0;
    if (cancellable)
        cancelId = cancellable.connect(() => proc.force_exit());
    let watchdogId = 0;
    if (watchdogSeconds > 0) {
        watchdogId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, watchdogSeconds, () => {
                watchdogId = 0;
                proc.force_exit();
                return GLib.SOURCE_REMOVE;
            });
    }
    try {
        const [stdout, stderr] =
            await proc.communicate_utf8_async(null, cancellable);
        return {
            /* get_exit_status() asserts on signal deaths (force_exit kills
             * with SIGKILL): report those as -1. */
            status: proc.get_if_exited() ? proc.get_exit_status() : -1,
            stdout: stdout ?? '',
            stderr: stderr ?? '',
        };
    } finally {
        if (watchdogId)
            GLib.source_remove(watchdogId);
        if (cancelId)
            cancellable.disconnect(cancelId);
    }
}

/**
 * Probe an mpm candidate, mirroring bar_plugin.py's check_mpm(): runnable
 * means a clean exit and an empty stderr; up to date means >= MPM_MIN_VERSION.
 *
 * @param {string[]} mpm - The mpm argv to probe.
 * @param {Gio.Cancellable|null} cancellable - Cancelled on extension disable.
 * @param {number} watchdogSeconds - Hard kill for a wedged probe.
 * @returns {Promise<{runnable: boolean, upToDate: boolean,
 *   version: number[]|null, error: string|null}>}
 */
export async function probeMpm(mpm, cancellable = null, watchdogSeconds = 30) {
    let result;
    try {
        result = await runCommand(
            [...mpm, '--no-color', '--version'], cancellable, watchdogSeconds);
    } catch (error) {
        return {runnable: false, upToDate: false, version: null, error: String(error)};
    }
    if (result.status !== 0 || result.stderr) {
        const error = result.stderr || `exit code ${result.status}`;
        return {runnable: false, upToDate: false, version: null, error};
    }
    const version = parseVersion(result.stdout);
    if (!version) {
        return {
            runnable: true, upToDate: false, version: null,
            error: `unable to parse version from: ${result.stdout.trim()}`,
        };
    }
    return {
        runnable: true,
        upToDate: compareVersions(version, MPM_MIN_VERSION) >= 0,
        version,
        error: null,
    };
}

/* Argv builders. Long-form options only, mirroring the repository-wide rule
 * for every argv mpm itself constructs at runtime. The sync/outdated pair
 * replicates bar_plugin.py's print_menu() contract: sync errors are lowered
 * to ERROR as best-effort noise, while outdated silences everything but
 * CRITICAL since per-manager errors come back inside the JSON payload. */

export function syncArgv(mpm, timeout = MPM_TIMEOUT) {
    return [...mpm, '--verbosity', 'ERROR', '--timeout', String(timeout), 'sync'];
}

export function outdatedArgv(mpm, timeout = MPM_TIMEOUT) {
    return [
        ...mpm, '--no-color', '--verbosity', 'CRITICAL',
        '--timeout', String(timeout), '--table-format', 'json', 'outdated',
    ];
}

export function upgradePackageArgv(mpm, managerId, packageId) {
    return [...mpm, `--${managerId}`, 'upgrade', packageId];
}

export function upgradeAllArgv(mpm, managerId) {
    return [...mpm, `--${managerId}`, 'upgrade', '--all'];
}

/**
 * Parse the JSON payload of `mpm --table-format json outdated` into a plain
 * menu model. The payload shape is guarded upstream by
 * tests/test_cli.py::check_packages_payload.
 *
 * @param {string} text - Raw stdout of the outdated call.
 * @returns {{managers: Array<{id: string, name: string,
 *   packages: Array<{id: string, name: string, installedVersion: string,
 *   latestVersion: string}>, errors: string[]}>,
 *   totalOutdated: number, totalErrors: number}}
 */
export function parseOutdated(text) {
    const data = JSON.parse(text);
    const managers = [];
    let totalOutdated = 0;
    let totalErrors = 0;
    for (const [id, info] of Object.entries(data)) {
        const packages = (info.packages ?? []).map(pkg => ({
            id: pkg.id,
            // Mirror the renderer's label fallback: name or id.
            name: pkg.name || pkg.id,
            // Mirror the renderer's "?" placeholder for unknown versions.
            installedVersion: pkg.installed_version || '?',
            latestVersion: pkg.latest_version || '?',
        }));
        const errors = (info.errors ?? [])
            .map(error => String(error).trim())
            .filter(error => error.length > 0);
        managers.push({id, name: info.name || id, packages, errors});
        totalOutdated += packages.length;
        totalErrors += errors.length;
    }
    return {managers, totalOutdated, totalErrors};
}

/**
 * Split a version pair into a common prefix and colored suffixes, mirroring
 * the diff_versions() convention of the bar plugin: unchanged prefix dimmed,
 * installed suffix red, latest suffix green. The prefix backtracks to the
 * last separator so a digit run is never split ("1.23" vs "1.24" diffs as
 * "23"/"24", not "3"/"4").
 *
 * @param {string} installed - Installed version string.
 * @param {string} latest - Latest version string.
 * @returns {{prefix: string, oldSuffix: string, newSuffix: string}}
 */
export function diffVersions(installed, latest) {
    let split = 0;
    const shortest = Math.min(installed.length, latest.length);
    while (split < shortest && installed[split] === latest[split])
        split++;
    const isAlnum = character => /[a-zA-Z0-9]/.test(character ?? '');
    while (
        split > 0 && isAlnum(installed[split - 1]) &&
        (isAlnum(installed[split]) || isAlnum(latest[split]))
    )
        split--;
    return {
        prefix: installed.slice(0, split),
        oldSuffix: installed.slice(split),
        newSuffix: latest.slice(split),
    };
}

/**
 * Resolve the terminal emulator to wrap upgrade commands in.
 *
 * @param {string} override - The `terminal-command` setting, parsed with
 *   shell syntax. Empty means autodetect from TERMINAL_CANDIDATES.
 * @returns {string[]|null} terminal argv prefix, or null when none found.
 */
export function findTerminal(override = '') {
    if (override) {
        try {
            const [ok, argv] = GLib.shell_parse_argv(override);
            if (ok && argv.length > 0)
                return argv;
        } catch {
            return null;
        }
        return null;
    }
    for (const candidate of TERMINAL_CANDIDATES) {
        if (GLib.find_program_in_path(candidate[0]))
            return candidate;
    }
    return null;
}

/**
 * Shell-quote an argv into a single command string.
 *
 * @param {string[]} argv - Command to quote.
 * @returns {string} the escaped command line.
 */
export function shellJoin(argv) {
    return argv.map(arg => GLib.shell_quote(arg)).join(' ');
}

/**
 * Wrap a command into a terminal invocation that keeps the window open once
 * the command completes, surfacing its exit status (same trick as
 * arch-update's default update command).
 *
 * @param {string[]} terminal - Terminal argv prefix from findTerminal().
 * @param {string[]} argv - Command to run inside the terminal.
 * @returns {string[]} the full argv to spawn.
 */
export function terminalArgv(terminal, argv) {
    const script =
        `${shellJoin(argv)}; s=$?; ` +
        "printf '\\n[mpm exited with status %s] Press Enter to close.\\n' \"$s\"; " +
        'read -r _line';
    const inner = ['sh', '-c', script];
    /* Console (kgx) has no trailing-argv form: its `--command` option takes
     * the whole command as one shell-parsed string. The dialect is keyed on
     * the program name, never on a trailing `-e` marker, whose semantics
     * differ per terminal (kgx parses a string, alacritty and xterm exec a
     * trailing argv): a marker heuristic would misroute an `alacritty -e`
     * override. Every other terminal, overrides included, gets the argv
     * appended. */
    if (GLib.path_get_basename(terminal[0]) === 'kgx')
        return [...terminal, '--command', shellJoin(inner)];
    return [...terminal, ...inner];
}

/**
 * Fire-and-forget spawn of an action command, either wrapped in a terminal
 * or silenced in the background (the NOPASSWD path documented at
 * https://kdeldycke.github.io/meta-package-manager/sudo.html).
 *
 * @param {string[]} argv - Command to spawn.
 * @returns {Gio.Subprocess} the spawned process handle.
 */
export function spawnDetached(argv) {
    return Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
}
