/* Shell-free logic of the Meta Package Manager GNOME Shell extension.
 *
 * This module is the GJS counterpart of the SwiftBar/Xbar plugin launcher
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

/* mpm 6.4.0 renamed `--output-format` back to `--table-format`, the flag the
 * JSON payload of `outdated` relies on. Everything else invoked here predates
 * that release. */
export const MPM_MIN_VERSION = [6, 4, 0];

/* Default `--timeout` in seconds, mirroring bar_plugin.py: mpm's own defaults
 * suit interactive runs and are too long for a background refresh. */
export const MPM_TIMEOUT = 60;

/* Bootstrap offered when no mpm is found, the command bar_plugin.py offers
 * from its own menu (tests/test_gnome_extension.py holds the two equal). uv
 * may itself be missing, which the companion documentation item covers. */
export const INSTALL_ARGV = [
    'uv', 'tool', 'install', '--upgrade', 'meta-package-manager',
];

export const INSTALL_DOCS_URL = 'https://mpm.run/install/';

/* The two readings of `mpm --no-color --version`: the numeric components,
 * which compare, and the token as printed, which names a development build. */
const VERSION_REGEX = /\bversion\s+(\d+(?:\.\d+)+)/;
const RELEASE_REGEX = /\bversion\s+(\S+)/;

/* Well-known mpm locations probed when it is not on the session PATH, which
 * GNOME does not source from the user's shell profile. Mirrors the PATH tier
 * of bar_plugin.py's search_mpm(); its venv walk-back has no counterpart
 * here, the extension living in no Python project tree. */
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

/* Shared by both command-override settings: a non-empty value is parsed with
 * shell syntax, and anything unparsable or empty resolves to null rather than
 * silently falling back to autodetection. */
function parseOverride(override) {
    try {
        const [ok, argv] = GLib.shell_parse_argv(override);
        return ok && argv.length > 0 ? argv : null;
    } catch {
        return null;
    }
}

/**
 * Resolve the mpm invocation to use, as an argv array.
 *
 * @param {string} override - The `mpm-command` setting, parsed with shell
 *   syntax so multi-word launchers like "uv run mpm" work. Empty means auto.
 * @returns {string[]|null} argv, or null when nothing is found.
 */
export function findMpm(override = '') {
    if (override)
        return parseOverride(override);
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
 * Extract the release string from `mpm --no-color --version` output.
 *
 * Where `parseVersion` keeps the numeric components alone so releases
 * compare, this keeps the token as printed: a development build reports
 * `8.0.0.dev0+40ce0879`, and that suffix is what identifies the build.
 *
 * @param {string} text - The command's stdout.
 * @returns {string|null} the release as printed, or null when unparsable.
 */
export function parseRelease(text) {
    const match = RELEASE_REGEX.exec(text ?? '');
    return match ? match[1] : null;
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
 * @param {Gio.Cancellable} cancellable - Cancelled on extension disable.
 *   Required, never defaulted: a caller with nothing to cancel leaves the
 *   watchdog below as the one source `disable()` cannot reach.
 * @param {number} watchdogSeconds - Hard kill after this delay, 0 to disable.
 *   mpm's own `--timeout` only bounds each manager CLI it runs internally,
 *   not a wedged mpm process itself.
 * @returns {Promise<{status: number, stdout: string, stderr: string}>}
 */
export async function runCommand(argv, cancellable, watchdogSeconds = 0) {
    const proc = Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
    let watchdogId = 0;
    const clearWatchdog = () => {
        if (watchdogId) {
            GLib.source_remove(watchdogId);
            watchdogId = 0;
        }
    };
    /* Cancelling communicate_utf8_async only abandons the read and leaves the
     * child running: hook the cancellable so the child is actually killed, and
     * the watchdog dropped on the spot rather than whenever the abandoned read
     * settles. A main loop source that outlives disable() keeps firing, on a
     * session that may be locked by then. */
    const cancelId = cancellable.connect(() => {
        clearWatchdog();
        proc.force_exit();
    });
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
        clearWatchdog();
        cancellable.disconnect(cancelId);
    }
}

/**
 * Probe an mpm candidate, mirroring bar_plugin.py's check_mpm(): runnable
 * means a clean exit and an empty stderr; up to date means >= MPM_MIN_VERSION.
 *
 * @param {string[]} mpm - The mpm argv to probe.
 * @param {Gio.Cancellable} cancellable - Cancelled on extension disable.
 * @param {number} watchdogSeconds - Hard kill for a wedged probe.
 * @returns {Promise<{runnable: boolean, upToDate: boolean,
 *   version: number[]|null, release: string|null, error: string|null}>}
 */
export async function probeMpm(mpm, cancellable, watchdogSeconds = 30) {
    const noVersion = (runnable, error) => ({
        runnable, upToDate: false, version: null, release: null, error,
    });
    let result;
    try {
        result = await runCommand(
            [...mpm, '--no-color', '--version'], cancellable, watchdogSeconds);
    } catch (error) {
        return noVersion(false, String(error));
    }
    if (result.status !== 0 || result.stderr)
        return noVersion(false, result.stderr || `exit code ${result.status}`);
    const version = parseVersion(result.stdout);
    if (!version) {
        return noVersion(
            true, `unable to parse version from: ${result.stdout.trim()}`);
    }
    return {
        runnable: true,
        upToDate: compareVersions(version, MPM_MIN_VERSION) >= 0,
        version,
        release: parseRelease(result.stdout),
        error: null,
    };
}

/* Argv builders. Long-form options only, mirroring the repository-wide rule
 * for every argv mpm itself constructs at runtime. The sync/outdated pair
 * replicates bar_plugin.py's print_menu() contract: sync errors are lowered
 * to ERROR as best-effort noise, while outdated silences everything but
 * CRITICAL since per-manager errors come back inside the JSON payload. */

/**
 * Parse the `mpm-options` setting into the argv fragment every builder below
 * splices in: after the extension's own options and before the subcommand,
 * so a repeated single-value option like `--verbosity` takes the user's value.
 * The version probe never takes them, so a mistyped option fails a check with
 * mpm's own usage error in the menu rather than reading as a missing mpm.
 *
 * @param {string} text - The setting, in shell syntax; empty for none.
 * @returns {string[]} the options, empty when the setting is.
 * @throws {GLib.Error} on a shell syntax error, such as an unmatched quote,
 *   which the check reports rather than running without the options.
 */
export function parseOptions(text) {
    if (!text.trim())
        return [];
    const [ok, argv] = GLib.shell_parse_argv(text);
    return ok ? argv : [];
}

export function syncArgv(mpm, timeout = MPM_TIMEOUT, options = []) {
    return [
        ...mpm, '--verbosity', 'ERROR', '--timeout', String(timeout),
        ...options, 'sync',
    ];
}

export function outdatedArgv(mpm, timeout = MPM_TIMEOUT, options = []) {
    return [
        ...mpm, '--no-color', '--verbosity', 'CRITICAL',
        '--timeout', String(timeout), '--table-format', 'json',
        ...options, 'outdated',
    ];
}

/* Percent-encode one pURL segment like Python's `quote(text, safe="")`,
 * keeping `:` as is. encodeURIComponent leaves `!'()*` alone, where Python
 * encodes them. */
function purlQuote(text) {
    return encodeURIComponent(text)
        .replace(/[!'()*]/g, char =>
            `%${char.charCodeAt(0).toString(16).toUpperCase()}`)
        .replaceAll('%3A', ':');
}

/**
 * Render the version-less pURL tying a package to its manager, the form
 * `mpm upgrade` resolves without looking the package up in the installed
 * packages. Mirrors `manager_purl()` in meta_package_manager/package.py, and
 * tests/purl-cases.json holds both to the same strings.
 *
 * @param {string} managerId - The manager ID, used as the pURL type.
 * @param {string} packageId - The package ID, as mpm reports it.
 * @returns {string} the pURL.
 */
export function packagePurl(managerId, packageId) {
    const cut = packageId.lastIndexOf('/');
    const namespace = cut < 0 ? [] : packageId.slice(0, cut).split('/');
    const name = packageId.slice(cut + 1);
    /* The whole ID stays the name when a split would leave an empty segment,
     * like an absolute path or a URL, which a pURL parser drops. */
    const whole = namespace.length === 0 || namespace.includes('') ||
        name === '';
    const segments = whole ? [packageId] : [...namespace, name];
    return `pkg:${managerId}/${segments.map(purlQuote).join('/')}`;
}

export function upgradePackageArgv(mpm, managerId, packageId, options = []) {
    return [
        ...mpm, `--${managerId}`, ...options,
        'upgrade', packagePurl(managerId, packageId),
    ];
}

export function upgradeAllArgv(mpm, managerId, options = []) {
    return [...mpm, `--${managerId}`, ...options, 'upgrade', '--all'];
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
        /* The label and the `?` placeholder follow package_rows() of the bar
         * plugin renderer. */
        const packages = (info.packages ?? []).map(pkg => ({
            id: pkg.id,
            name: pkg.name || pkg.id,
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
 * installed suffix red, latest suffix green. The split snaps back to a
 * separator boundary, so a digit run is never cut in half and the separator
 * introducing the diverging token is colored with it: "1.23" vs "1.24" diffs
 * as ".23"/".24", not "3"/"4" nor "23"/"24".
 *
 * Held to the Python implementation by tests/version-diff-cases.json, the
 * shared corpus both test suites assert against.
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
    const isAlnum = character => /[\p{L}\p{N}]/u.test(character ?? '');
    // Snap back to a separator boundary, so the whole diverging token and the
    // separator introducing it are colored, the way diff_versions() does it.
    // Only when the divergence lands inside a token, though: one version being
    // the other plus a whole new token already sits on a boundary, and walking
    // back would swallow the tokens that did match.
    if (
        split > 0 && split < Math.max(installed.length, latest.length) &&
        (isAlnum(installed[split]) || isAlnum(latest[split]))
    ) {
        // Walk back past the partial alnum token, then past the separator.
        while (split > 0 && isAlnum(installed[split - 1]))
            split--;
        while (split > 0 && !isAlnum(installed[split - 1]))
            split--;
    }
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
    if (override)
        return parseOverride(override);
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
 * https://mpm.run/sudo/).
 *
 * @param {string[]} argv - Command to spawn.
 * @returns {Gio.Subprocess} the spawned process handle.
 */
export function spawnDetached(argv) {
    return Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
}
