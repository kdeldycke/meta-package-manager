/* Unit tests for the shell-free mpm.js module of the GNOME Shell extension.
 *
 * Runs under a bare gjs interpreter, no GNOME session required:
 *
 *     gjs -m tests/gnome/run-tests.js
 *
 * Driven by tests/test_gnome_extension.py when gjs is installed, and by the
 * tests-gnome-extension.yaml workflow in CI. Output is TAP-ish: one line per
 * check, non-zero exit on any failure.
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import system from 'system';

import * as Mpm from '../../gnome-shell/mpm@kdeldycke.github.io/mpm.js';

let counter = 0;
let failures = 0;

function check(label, actual, expected) {
    counter++;
    const got = JSON.stringify(actual);
    const wanted = JSON.stringify(expected);
    if (got === wanted) {
        console.log(`ok ${counter} - ${label}`);
    } else {
        failures++;
        console.log(`not ok ${counter} - ${label}: got ${got}, expected ${wanted}`);
    }
}

/* Mirrors tests/test_bar_plugin.py::_outdated_fixture: the exact JSON shape
 * `mpm --table-format json outdated` produces, with an empty-but-erroring
 * manager, a null name and a null installed version. */
const OUTDATED_FIXTURE = JSON.stringify({
    'brew': {
        'id': 'brew',
        'name': 'Homebrew Formulae',
        'errors': [],
        'packages': [
            {
                'id': 'github-keygen',
                'name': 'github-keygen',
                'installed_version': '1.2.0',
                'latest_version': '1.3.0',
            },
            {
                'id': 'meson',
                'name': null,
                'installed_version': null,
                'latest_version': '0.60.1',
            },
        ],
    },
    'cask': {
        'id': 'cask',
        'name': 'Homebrew Cask',
        'errors': ['boom went wrong\n', '   '],
        'packages': [],
    },
});

function testParseVersion() {
    check('parseVersion nominal',
        Mpm.parseVersion('mpm, version 7.5.0'), [7, 5, 0]);
    check('parseVersion ignores dev suffix',
        Mpm.parseVersion('mpm, version 7.5.1.dev0'), [7, 5, 1]);
    check('parseVersion multiline tail',
        Mpm.parseVersion('mpm, version 6.4.0\nmore lines'), [6, 4, 0]);
    check('parseVersion garbage', Mpm.parseVersion('no digits here'), null);
    check('parseVersion empty', Mpm.parseVersion(''), null);
}

function testCompareVersions() {
    check('compare equal', Mpm.compareVersions([7, 5, 0], [7, 5, 0]), 0);
    check('compare shorter is older',
        Mpm.compareVersions([7, 5], [7, 5, 1]) < 0, true);
    check('compare component-wise not lexicographic',
        Mpm.compareVersions([10], [9, 9]) > 0, true);
}

function testArgvBuilders() {
    const mpm = ['/usr/bin/mpm'];
    check('syncArgv', Mpm.syncArgv(mpm, 60), [
        '/usr/bin/mpm', '--verbosity', 'ERROR', '--timeout', '60', 'sync',
    ]);
    check('outdatedArgv', Mpm.outdatedArgv(mpm, 42), [
        '/usr/bin/mpm', '--no-color', '--verbosity', 'CRITICAL',
        '--timeout', '42', '--table-format', 'json', 'outdated',
    ]);
    check('upgradePackageArgv',
        Mpm.upgradePackageArgv(mpm, 'brew', 'wget'),
        ['/usr/bin/mpm', '--brew', 'upgrade', 'wget']);
    check('upgradeAllArgv', Mpm.upgradeAllArgv(mpm, 'apt'),
        ['/usr/bin/mpm', '--apt', 'upgrade', '--all']);
}

function testParseOutdated() {
    const model = Mpm.parseOutdated(OUTDATED_FIXTURE);
    check('parseOutdated totals',
        [model.totalOutdated, model.totalErrors], [2, 1]);
    check('parseOutdated manager order',
        model.managers.map(manager => manager.id), ['brew', 'cask']);
    check('parseOutdated package mapping', model.managers[0].packages[0], {
        id: 'github-keygen',
        name: 'github-keygen',
        installedVersion: '1.2.0',
        latestVersion: '1.3.0',
    });
    check('parseOutdated null fallbacks', model.managers[0].packages[1], {
        id: 'meson',
        name: 'meson',
        installedVersion: '?',
        latestVersion: '0.60.1',
    });
    check('parseOutdated errors trimmed and filtered',
        model.managers[1].errors, ['boom went wrong']);
    check('parseOutdated empty manager kept',
        model.managers[1].packages, []);
}

/* These cases are the contract between this implementation and the Python
 * diff_versions() the bar plugin renders with: test_version.py reads the pairs
 * and expectations straight out of this function and asserts its own splits
 * match. Add a case here and the Python side picks it up on the next run. */
function testDiffVersions() {
    check('diff distinct suffix', Mpm.diffVersions('1.2.0', '1.3.0'),
        {prefix: '1', oldSuffix: '.2.0', newSuffix: '.3.0'});
    check('diff last component', Mpm.diffVersions('0.60.0', '0.60.1'),
        {prefix: '0.60', oldSuffix: '.0', newSuffix: '.1'});
    check('diff never splits a digit run', Mpm.diffVersions('1.23', '1.24'),
        {prefix: '1', oldSuffix: '.23', newSuffix: '.24'});
    check('diff widening component', Mpm.diffVersions('7.5.0', '7.15.0'),
        {prefix: '7', oldSuffix: '.5.0', newSuffix: '.15.0'});
    check('diff no common prefix', Mpm.diffVersions('?', '1.2'),
        {prefix: '', oldSuffix: '?', newSuffix: '1.2'});
    check('diff identical versions', Mpm.diffVersions('1.0', '1.0'),
        {prefix: '1.0', oldSuffix: '', newSuffix: ''});
    /* The separator introducing the diverging token is colored with it, not
     * left in the dimmed prefix. */
    check('diff colors the separator', Mpm.diffVersions('1.0.0-alpha', '1.0.0-beta'),
        {prefix: '1.0.0', oldSuffix: '-alpha', newSuffix: '-beta'});
    check('diff keeps a Debian epoch dimmed',
        Mpm.diffVersions('1:9.20.18-1ubuntu2.1', '1:9.20.24-1ubuntu0.1'),
        {prefix: '1:9.20', oldSuffix: '.18-1ubuntu2.1', newSuffix: '.24-1ubuntu0.1'});
    /* A version that is the other plus a whole new token already sits on a
     * boundary: backtracking would color both in full and highlight nothing. */
    check('diff appended token', Mpm.diffVersions('14ubuntu6', '14ubuntu6.1'),
        {prefix: '14ubuntu6', oldSuffix: '', newSuffix: '.1'});
    check('diff truncated token', Mpm.diffVersions('1.2.3', '1.2'),
        {prefix: '1.2', oldSuffix: '.3', newSuffix: ''});
    /* Nothing precedes the first token, so there is no separator to color. */
    check('diff first token', Mpm.diffVersions('1.2.3', '2.0.0'),
        {prefix: '', oldSuffix: '1.2.3', newSuffix: '2.0.0'});
}

function testShellHelpers() {
    const tricky = ['echo', 'a b', "it's", '--flag=value'];
    const [ok, roundTrip] = GLib.shell_parse_argv(Mpm.shellJoin(tricky));
    check('shellJoin round-trips through shell parsing',
        [ok, roundTrip], [true, tricky]);

    const command = ['mpm', '--brew', 'upgrade', 'wget'];
    const argvStyle = Mpm.terminalArgv(['gnome-terminal', '--'], command);
    check('terminalArgv argv dialect structure', argvStyle.slice(0, 4),
        ['gnome-terminal', '--', 'sh', '-c']);
    check('terminalArgv embeds the quoted command',
        argvStyle[4].includes("'mpm' '--brew' 'upgrade' 'wget'"), true);
    check('terminalArgv surfaces the exit status',
        argvStyle[4].includes('[mpm exited with status %s]'), true);
    check('terminalArgv keeps the window open',
        argvStyle[4].endsWith('read -r _line'), true);

    /* Console (kgx) has no trailing-argv form: it gets its `--command`
     * single-string dialect, keyed on the program basename. */
    const kgxStyle = Mpm.terminalArgv(['kgx'], command);
    check('terminalArgv kgx single-string dialect',
        [kgxStyle.length, kgxStyle[0], kgxStyle[1]], [3, 'kgx', '--command']);
    const [kgxOk, kgxInner] = GLib.shell_parse_argv(kgxStyle[2]);
    check('terminalArgv single-string round-trips to sh -c',
        [kgxOk, kgxInner.slice(0, 2)], [true, ['sh', '-c']]);
    check('terminalArgv kgx dialect keys on the basename',
        Mpm.terminalArgv(['/usr/bin/kgx'], command).slice(0, 2),
        ['/usr/bin/kgx', '--command']);

    /* An override ending in `-e` stays in argv form: alacritty's `-e` execs
     * the trailing argv directly, a single string would break it. */
    const alacrittyStyle = Mpm.terminalArgv(['alacritty', '-e'], command);
    check('terminalArgv -e override keeps the argv form',
        alacrittyStyle.slice(0, 4), ['alacritty', '-e', 'sh', '-c']);
}

function testFinders() {
    check('findMpm override parses shell syntax',
        Mpm.findMpm('uv run mpm'), ['uv', 'run', 'mpm']);
    check('findTerminal override parses shell syntax',
        Mpm.findTerminal('foot --hold'), ['foot', '--hold']);
    check('terminal candidates lead with their binary',
        Mpm.TERMINAL_CANDIDATES.map(candidate => candidate.length >= 1),
        [true, true, true, true]);
}

async function testSubprocess() {
    /* Every call takes a cancellable, the extension's own liveness handle:
     * runCommand no longer defaults it, so a watchdog always has something
     * able to drop it. This one is never cancelled. */
    const live = new Gio.Cancellable();

    const result = await Mpm.runCommand(
        ['sh', '-c', 'echo out; echo err >&2; exit 3'], live);
    check('runCommand captures everything',
        [result.status, result.stdout, result.stderr],
        [3, 'out\n', 'err\n']);

    /* probeMpm appends --no-color --version, which the sh -c scripts below
     * receive as ignored positional parameters. */
    const fresh = await Mpm.probeMpm(
        ['sh', '-c', 'echo "mpm, version 6.4.0"'], live);
    check('probeMpm fresh enough',
        [fresh.runnable, fresh.upToDate, fresh.version, fresh.error],
        [true, true, [6, 4, 0], null]);

    const stale = await Mpm.probeMpm(
        ['sh', '-c', 'echo "mpm, version 5.0.0"'], live);
    check('probeMpm too old',
        [stale.runnable, stale.upToDate, stale.version],
        [true, false, [5, 0, 0]]);

    const broken = await Mpm.probeMpm(
        ['sh', '-c', 'echo boom >&2; exit 1'], live);
    check('probeMpm broken candidate',
        [broken.runnable, broken.error !== null], [false, true]);

    const missing = await Mpm.probeMpm(['/nonexistent/mpm-binary'], live);
    check('probeMpm missing binary',
        [missing.runnable, missing.error !== null], [false, true]);

    /* The watchdog force-kills a wedged process; signal deaths report -1. */
    const watchdogStart = GLib.get_monotonic_time();
    const wedged = await Mpm.runCommand(['sleep', '5'], live, 1);
    check('runCommand watchdog kills a wedged process',
        [wedged.status, (GLib.get_monotonic_time() - watchdogStart) / 1e6 < 4],
        [-1, true]);

    /* Cancellation rejects the promise and kills the child fast. */
    const cancellable = new Gio.Cancellable();
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
        cancellable.cancel();
        return GLib.SOURCE_REMOVE;
    });
    const cancelStart = GLib.get_monotonic_time();
    let cancelled = false;
    try {
        await Mpm.runCommand(['sleep', '5'], cancellable);
    } catch {
        cancelled = true;
    }
    check('runCommand cancellation rejects fast',
        [cancelled, (GLib.get_monotonic_time() - cancelStart) / 1e6 < 3],
        [true, true]);
}

async function main() {
    testParseVersion();
    testCompareVersions();
    testArgvBuilders();
    testParseOutdated();
    testDiffVersions();
    testShellHelpers();
    testFinders();
    await testSubprocess();
}

const loop = new GLib.MainLoop(null, false);
let exitCode = 0;
main().catch(error => {
    console.log(`not ok - unhandled error: ${error}`);
    exitCode = 1;
}).finally(() => loop.quit());
loop.run();

if (failures > 0) {
    console.log(`# ${failures} of ${counter} checks failed`);
    exitCode = 1;
} else {
    console.log(`# all ${counter} checks passed`);
}
system.exit(exitCode);
