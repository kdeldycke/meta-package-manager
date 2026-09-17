/* Logic of the Meta Package Manager GNOME Shell extension, with no shell code.
 *
 * This module is the GJS counterpart of the SwiftBar/Xbar plugin launcher
 * (meta_package_manager/bar_plugin.py): find a runnable mpm, check its version
 * against a minimum, run `sync` and then `outdated`, and build the commands of
 * the menu actions. extension.js holds the rendering.
 *
 * This file imports gi://Gio and gi://GLib only, and no
 * resource:///org/gnome/shell/* module. The whole file then loads in a bare
 * `gjs -m` interpreter, and the test suite calls every function below outside
 * a GNOME session (see tests/gnome/run-tests.js in the repository).
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

Gio._promisify(Gio.Subprocess.prototype, 'communicate_utf8_async');

/* mpm 6.4.0 changed `--output-format` back to `--table-format`, which is the
 * option that the `outdated` JSON payload needs. Every other option used
 * here existed before that release. */
export const MPM_MIN_VERSION = [6, 4, 0];

/* First mpm release accepting --shell-env. GNOME Shell starts the extension
 * with the environment of the session, which never reads .bashrc or .zshrc,
 * so a manager installed under the home directory is invisible to mpm until
 * mpm adopts the login shell's environment itself. An older mpm rejects the
 * option as unknown, which is worse than the narrow PATH. bar_plugin.py
 * carries the same gate, and tests/test_gnome_extension.py holds the two in
 * sync. */
export const SHELL_ENV_MIN_VERSION = [8, 0, 0];

/* Default `--timeout` in seconds, the same value as in bar_plugin.py. The mpm
 * defaults are for interactive runs and are too long for a background
 * refresh. */
export const MPM_TIMEOUT = 60;

/* Command offered when no mpm is found. bar_plugin.py offers the same command
 * in its own menu, and tests/test_gnome_extension.py checks that the two are
 * equal. uv may be missing too, and the documentation item next to it covers
 * that case. */
export const INSTALL_ARGV = [
    'uv', 'tool', 'install', '--upgrade', 'meta-package-manager',
];

export const INSTALL_DOCS_URL = 'https://mpm.run/install/';

/* The two readings of `mpm --no-color --version`: the numeric components,
 * which the code compares, and the token as printed, which names a development
 * build. */
const VERSION_REGEX = /\bversion\s+(\d+(?:\.\d+)+)/;
const RELEASE_REGEX = /\bversion\s+(\S+)/;

/* Known locations of mpm, probed when mpm is not on the session PATH. GNOME
 * does not read that PATH from the user's shell profile. This is
 * the PATH step of search_mpm() in bar_plugin.py. The walk up to a virtual
 * environment has no counterpart here, because the extension is in no Python
 * project tree. */
function fallbackPaths() {
    return [
        GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'mpm']),
        '/usr/local/bin/mpm',
        '/home/linuxbrew/.linuxbrew/bin/mpm',
    ];
}

/* Terminal emulators, probed in this order when the user sets no override.
 * Each one has its own syntax for "run this argv". xdg-terminal-exec is the
 * freedesktop specification's entry point, and its trailing arguments are
 * the command argv. Ptyxis and Console (kgx) are the recent GNOME terminals.
 * gnome-terminal is the older alternative. Console has no trailing-argv form,
 * so terminalArgv() gives it the `--command` option, which takes one string.
 * That function selects the syntax from the program name. */
export const TERMINAL_CANDIDATES = [
    ['xdg-terminal-exec'],
    ['ptyxis', '--'],
    ['kgx'],
    ['gnome-terminal', '--'],
];

/* Shared by the two command-override settings. A value that is not empty is
 * parsed with the shell syntax. A value that is empty, or that cannot be
 * parsed, gives null: the code does not fall back to autodetection in that
 * case. */
function parseOverride(override) {
    try {
        const [ok, argv] = GLib.shell_parse_argv(override);
        return ok && argv.length > 0 ? argv : null;
    } catch {
        return null;
    }
}

/**
 * Return the mpm command to use, as an argv array.
 *
 * @param {string} override - The `mpm-command` setting, parsed with shell
 *   syntax, so a command of several words like "uv run mpm" works. An empty
 *   value means autodetection.
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
 * Return the version tuple from the output of `mpm --no-color --version`.
 *
 * @param {string} text - The stdout of the command.
 * @returns {number[]|null} version components, or null when the text cannot be
 *   parsed.
 */
export function parseVersion(text) {
    const match = VERSION_REGEX.exec(text ?? '');
    if (!match)
        return null;
    return match[1].split('.').map(Number);
}

/**
 * Return the release string from the output of `mpm --no-color --version`.
 *
 * `parseVersion` keeps the numeric components only, so two releases can be
 * compared. This function keeps the token as printed: a development build
 * reports `8.0.0.dev0+40ce0879`, and its suffix identifies the build.
 *
 * @param {string} text - The stdout of the command.
 * @returns {string|null} the release as printed, or null when the text cannot
 *   be parsed.
 */
export function parseRelease(text) {
    const match = RELEASE_REGEX.exec(text ?? '');
    return match ? match[1] : null;
}

/**
 * Compare two version tuples, one component at a time.
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
 * Run a command without blocking, and capture its output.
 *
 * @param {string[]} argv - Command to run.
 * @param {Gio.Cancellable} cancellable - Cancelled when the extension is
 *   disabled. This parameter is required and has no default: a caller with
 *   nothing to cancel would leave the watchdog below as the one source that
 *   `disable()` cannot stop.
 * @param {number} watchdogSeconds - Kill the command after this delay. Use 0
 *   for no watchdog. mpm's own `--timeout` option limits each manager command
 *   that mpm runs, and it does not limit a hung mpm process.
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
    /* Cancelling communicate_utf8_async stops the read only, and the child
     * process keeps running. This handler kills the child and removes the
     * watchdog at once, and it does not wait for the abandoned read to end. A
     * main loop source that still exists after disable() keeps firing, and the
     * session may be locked by then. */
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
            /* get_exit_status() fails an assertion when a signal killed the
             * process, and force_exit kills it with SIGKILL. Report that case
             * as -1. */
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
 * Probe one mpm candidate. This is check_mpm() of bar_plugin.py: runnable
 * means an exit with no error and an empty stderr, and up to date means a
 * version equal to or higher than MPM_MIN_VERSION.
 *
 * @param {string[]} mpm - The mpm argv to probe.
 * @param {Gio.Cancellable} cancellable - Cancelled when the extension is
 *   disabled.
 * @param {number} watchdogSeconds - Kill a probe that does not end.
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

/* Argv builders. They use long-form options only, which is this repository's
 * rule for every argv that mpm builds at runtime. The sync and outdated pair
 * follows bar_plugin.py's print_menu(): the sync call logs at the ERROR
 * level, because a failure there is not fatal, and the outdated call logs
 * CRITICAL messages only, because each manager's errors come back in the JSON
 * payload. */

/**
 * Parse the `mpm-options` setting into the argv fragment that every builder
 * below inserts. It goes after the extension's own options and before the
 * subcommand, so a single-value option that occurs twice, like `--verbosity`,
 * takes the value from the user. The version probe does not use these options,
 * so a mistyped option makes a check fail with mpm's own usage error in the
 * menu. Without this, the same typo would look like a missing mpm.
 *
 * @param {string} text - The setting, in shell syntax. Empty for no option.
 * @returns {string[]} the options, empty when the setting is empty.
 * @throws {GLib.Error} on a shell syntax error, like a quote with no pair. The
 *   check reports that error, and it does not run without the options.
 */
export function parseOptions(text) {
    if (!text.trim())
        return [];
    const [ok, argv] = GLib.shell_parse_argv(text);
    return ok ? argv : [];
}

/**
 * The `--shell-env` option for an mpm that accepts it, nothing for an older
 * one. It goes ahead of the user's options, so a `--no-shell-env` typed into
 * the mpm-options setting wins.
 *
 * @param {number[]|null} version - The probed mpm version, null when unknown.
 * @returns {string[]} the option, or an empty list.
 */
export function shellEnvOptions(version) {
    if (version && compareVersions(version, SHELL_ENV_MIN_VERSION) >= 0)
        return ['--shell-env'];
    return [];
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

/* Percent-encode one pURL segment the way Python's `quote(text, safe="")`
 * does it, and keep `:` as it is. encodeURIComponent does not encode `!'()*`,
 * and Python encodes them. */
function purlQuote(text) {
    return encodeURIComponent(text)
        .replace(/[!'()*]/g, char =>
            `%${char.charCodeAt(0).toString(16).toUpperCase()}`)
        .replaceAll('%3A', ':');
}

/**
 * Return the pURL, with no version, that ties a package to its manager.
 * `mpm upgrade` resolves this form with no search in the installed packages.
 * This is `manager_purl()` in meta_package_manager/package.py, and
 * tests/purl-cases.json checks that both produce the same strings.
 *
 * @param {string} managerId - The manager ID, used as the pURL type.
 * @param {string} packageId - The package ID, as mpm reports it.
 * @returns {string} the pURL.
 */
export function packagePurl(managerId, packageId) {
    const cut = packageId.lastIndexOf('/');
    const namespace = cut < 0 ? [] : packageId.slice(0, cut).split('/');
    const name = packageId.slice(cut + 1);
    /* The whole ID stays the name when a split would leave an empty segment.
     * This happens for an absolute path or a URL, and a pURL parser drops an
     * empty segment. */
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
 * menu model. tests/test_cli.py::check_packages_payload checks the shape of
 * that payload upstream.
 *
 * @param {string} text - The raw stdout of the outdated call.
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
 * Split a pair of versions into a common prefix and two colored suffixes. The
 * convention is the bar plugin's diff_versions(): the unchanged prefix is
 * dimmed, the installed suffix is red and the latest suffix is green. The
 * split moves back to a separator, so the code never cuts a run of digits in
 * half, and the separator in front of the different token is colored with
 * it. "1.23" against "1.24" gives ".23" and ".24", and not "3" and "4", and
 * not "23" and "24".
 *
 * tests/version-diff-cases.json is the corpus that both test suites check,
 * each against its own implementation.
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
    // Move the split back to a separator, so the whole different token and
    // the separator in front of it are colored, as diff_versions() does it. Do
    // this only when the difference starts inside a token. When one version is
    // the other plus one new token, the split is already on a separator, and a
    // move back would take tokens that are equal.
    if (
        split > 0 && split < Math.max(installed.length, latest.length) &&
        (isAlnum(installed[split]) || isAlnum(latest[split]))
    ) {
        // Move back past the incomplete alnum token, then past the
        // separator.
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
 * Return the terminal emulator that runs the upgrade commands.
 *
 * @param {string} override - The `terminal-command` setting, parsed with shell
 *   syntax. An empty value means autodetection from
 *   TERMINAL_CANDIDATES.
 * @returns {string[]|null} the terminal argv prefix, or null when none is
 *   found.
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
 * Quote an argv into one command string for a shell.
 *
 * @param {string[]} argv - Command to quote.
 * @returns {string} the escaped command line.
 */
export function shellJoin(argv) {
    return argv.map(arg => GLib.shell_quote(arg)).join(' ');
}

/**
 * Put a command into a terminal invocation that keeps the window open after
 * the command ends and shows its exit status. arch-update uses the same method
 * for its default update command.
 *
 * @param {string[]} terminal - The terminal argv prefix from findTerminal().
 * @param {string[]} argv - The command to run inside the terminal.
 * @returns {string[]} the full argv to start.
 */
export function terminalArgv(terminal, argv) {
    const script =
        `${shellJoin(argv)}; s=$?; ` +
        "printf '\\n[mpm exited with status %s] Press Enter to close.\\n' \"$s\"; " +
        'read -r _line';
    const inner = ['sh', '-c', script];
    /* Console (kgx) has no trailing-argv form: its `--command` option takes
     * the whole command as one string that a shell parses. This code selects
     * the syntax from the program name, and not from a trailing `-e` marker.
     * That marker means a different thing in each terminal: kgx parses a
     * string, and alacritty and xterm run a trailing argv. A test on the marker
     * would send an `alacritty -e` override down the wrong path. Every other
     * terminal, including an override, gets the argv at the end. */
    if (GLib.path_get_basename(terminal[0]) === 'kgx')
        return [...terminal, '--command', shellJoin(inner)];
    return [...terminal, ...inner];
}

/**
 * Start an action command and do not wait for it. The command is either inside
 * a terminal or in the background with no output, which is the NOPASSWD case
 * documented at https://mpm.run/sudo/.
 *
 * @param {string[]} argv - Command to start.
 * @returns {Gio.Subprocess} the handle of the started process.
 */
export function spawnDetached(argv) {
    return Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
}
