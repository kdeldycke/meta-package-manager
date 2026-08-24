/* Meta Package Manager GNOME Shell extension.
 *
 * Panel indicator mirroring the SwiftBar/Xbar plugin: it lists outdated
 * packages reported by `mpm outdated` across every package manager, and every
 * menu action runs `mpm` itself so the user's mpm configuration file governs
 * clicks (manager selection, sudo policy, per-manager overrides, cooldown).
 *
 * The subprocess plumbing and menu model live in mpm.js; this file owns the
 * widgetry, timers and lifecycle.
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {
    Extension,
    gettext as _,
    ngettext,
} from 'resource:///org/gnome/shell/extensions/extension.js';

import * as Mpm from './mpm.js';

/* Panel states, each mapped to a stock icon name below. UPDATES and UPTODATE
 * mirror the 🎁↑N / 📦✓ title states of the bar plugin; ERROR covers both a
 * failed check and the per-manager error marker; MISSING is the bootstrap
 * state of bar_plugin.py when no runnable mpm is found. */
const State = {
    UNKNOWN: 'unknown',
    CHECKING: 'unknown',
    UPTODATE: 'uptodate',
    UPDATES: 'updates',
    ERROR: 'error',
    MISSING: 'error',
};

/* Each state renders as a stock symbolic icon from the icon theme, not as
 * artwork of our own: the shell recolors them with the panel foreground, the
 * user's theme (Yaru on Ubuntu) can restyle them, and they carry the meaning
 * every other GNOME updates indicator already gives them. `software-update-*`
 * name this domain exactly. */
const STATE_ICONS = {
    unknown: 'content-loading-symbolic',
    uptodate: 'selection-mode-symbolic',
    updates: 'software-update-available-symbolic',
    error: 'software-update-urgent-symbolic',
};

/* State deliberately kept at module scope so a screen-lock disable()/enable()
 * cycle neither re-triggers the boot check nor drops the last report (same
 * pattern as arch-update). Plain data only: GObject instances must never
 * outlive disable(). */
let firstBoot = true;
let lastCheck = null;
let lastMpm = null;
let lastModel = null;
let lastError = null;
let knownOutdated = null;

const MpmIndicator = GObject.registerClass(
class MpmIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, _('Meta Package Manager'));
        this._extension = extension;
        this._settings = extension.getSettings();
        this._checking = false;
        this._cancellable = null;
        this._checkTimeoutId = null;
        this._oneShotTimeoutId = null;
        this._notifSource = null;

        this.add_style_class_name('mpm-indicator');
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this._icon = new St.Icon({
            gicon: this._stateIcon(State.UNKNOWN),
            style_class: 'system-status-icon',
        });
        this._countLabel = new St.Label({
            text: '',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'mpm-count-label',
        });
        box.add_child(this._icon);
        box.add_child(this._countLabel);
        this.add_child(box);

        this._buildMenu();

        /* Every signal is tracked against this indicator through
         * connectObject(), so teardown is one disconnectObject() per emitter
         * instead of a handler id per connection: the shell disconnects the
         * rest with the actor itself. */
        this._settings.connectObject(
            'changed', () => this._onSettingsChanged(), this);

        if (firstBoot) {
            /* Delay the very first check to keep session startup snappy. Not
             * re-armed on later enable() cycles (screen lock). */
            this._armOneShot(this._settings.get_int('boot-wait'));
        } else {
            this._showReport();
            this._scheduleCheck();
        }
    }

    /* Static menu skeleton. The report section is rebuilt on every refresh;
     * the footer (Check now, last-checked, Settings) is permanent. */
    _buildMenu() {
        /* Interactive package items live in an inner PopupMenuSection wrapped
         * in a ScrollView, so a big report scrolls instead of overflowing the
         * screen (GNOME popup menus do not scroll natively; the max-height
         * lives in stylesheet.css). The section is deliberately never
         * registered with the menu, only its actor is embedded: its _parent
         * stays null, so an item activation dead-ends in the section's no-op
         * close() instead of closing the panel menu. Action items therefore
         * close the menu explicitly. */
        this._reportSection = new PopupMenu.PopupMenuSection();
        const scrollView = new St.ScrollView({
            style_class: 'mpm-updates-list',
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
        });
        scrollView.child = this._reportSection.actor;
        const scrollWrapper = new PopupMenu.PopupMenuSection();
        scrollWrapper.actor.add_child(scrollView);
        this.menu.addMenuItem(scrollWrapper);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        /* "Check now" must keep the menu open: adding the item to the section
         * box directly (not addMenuItem) skips the activate-closes-the-menu
         * wiring while keeping the row clickable (same trick as
         * arch-update). */
        this._checkNowItem = new PopupMenu.PopupMenuItem(_('Check now'));
        this._checkNowItem.connectObject(
            'activate', () => this._checkUpdates(), this);
        const checkNowSection = new PopupMenu.PopupMenuSection();
        checkNowSection.box.add_child(this._checkNowItem);
        this.menu.addMenuItem(checkNowSection);

        this._lastCheckedItem = new PopupMenu.PopupMenuItem('', {
            reactive: false,
        });
        this.menu.addMenuItem(this._lastCheckedItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const settingsItem = new PopupMenu.PopupMenuItem(_('Settings'));
        settingsItem.connectObject('activate', () => {
            this.menu.close();
            this._extension.openPreferences();
        }, this);
        this.menu.addMenuItem(settingsItem);

        this._updateLastChecked();
    }

    _stateIcon(state) {
        return new Gio.ThemedIcon({name: STATE_ICONS[state]});
    }

    /* Panel icon, count label and indicator visibility for a given state. */
    _setPanelState(state, count = 0) {
        this._icon.gicon = this._stateIcon(state);
        const showCount = this._settings.get_boolean('show-count');
        this._countLabel.text = showCount && count > 0 ? String(count) : '';
        this._countLabel.visible = showCount && count > 0;
        const alwaysVisible = this._settings.get_boolean('always-visible');
        this.visible = alwaysVisible || count > 0 ||
            state === State.ERROR || state === State.MISSING;
    }

    _updateLastChecked() {
        if (lastCheck === null) {
            this._lastCheckedItem.visible = false;
            return;
        }
        this._lastCheckedItem.visible = true;
        const time = lastCheck.toLocaleTimeString([], {timeStyle: 'short'});
        this._lastCheckedItem.label.text = _('Last checked %s').format(time);
    }

    /* One-shot timer shared by the boot delay and the post-upgrade re-check:
     * both funnel into a full check. */
    _armOneShot(seconds) {
        this._clearOneShot();
        this._oneShotTimeoutId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, seconds, () => {
                this._oneShotTimeoutId = null;
                firstBoot = false;
                this._checkUpdates();
                return GLib.SOURCE_REMOVE;
            });
    }

    _clearOneShot() {
        if (this._oneShotTimeoutId) {
            GLib.source_remove(this._oneShotTimeoutId);
            this._oneShotTimeoutId = null;
        }
    }

    /* Re-arm the recurring check, compensating for time already elapsed so
     * lock/unlock cycles and settings changes never reset the countdown
     * (arch-update's _scheduleCheck pattern). */
    _scheduleCheck() {
        if (this._checkTimeoutId) {
            GLib.source_remove(this._checkTimeoutId);
            this._checkTimeoutId = null;
        }
        let delay = this._settings.get_int('check-interval') * 60;
        if (lastCheck !== null) {
            delay -= (Date.now() - lastCheck.getTime()) / 1000;
            delay = Math.max(delay, this._settings.get_int('boot-wait'));
        }
        this._checkTimeoutId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, Math.round(delay), () => {
                this._checkTimeoutId = null;
                this._checkUpdates();
                return GLib.SOURCE_REMOVE;
            });
    }

    /* The full refresh pipeline, mirroring bar_plugin.py print_menu(): locate
     * mpm, gate on version, best-effort `sync`, then `outdated` as JSON. */
    async _checkUpdates() {
        if (this._checking)
            return;
        this._checking = true;
        /* The cancellable is also the liveness handle: destroy() cancels it,
         * so a check outliving the indicator learns that from its own
         * cancellation. Held in a local as well, because destroy() clears the
         * field while this run still needs to consult it. */
        const cancellable = new Gio.Cancellable();
        this._cancellable = cancellable;
        this._setPanelState(State.CHECKING);
        this._checkNowItem.reactive = false;
        this._checkNowItem.add_style_class_name('popup-inactive-menu-item');

        try {
            const mpm = Mpm.findMpm(this._settings.get_string('mpm-command'));
            if (mpm === null) {
                this._setMissing(_('mpm not found on this system.'));
                return;
            }
            const probe = await Mpm.probeMpm(mpm, cancellable);
            if (!probe.runnable) {
                this._setMissing(_('mpm cannot run: %s').format(probe.error));
                return;
            }
            if (!probe.upToDate) {
                const minimum = Mpm.MPM_MIN_VERSION.join('.');
                this._setMissing(
                    _('mpm is too old: version %s or newer is required.')
                        .format(minimum));
                return;
            }
            lastMpm = mpm;
            const timeout = this._settings.get_int('timeout');
            /* --timeout caps each manager CLI inside mpm: give mpm itself a
             * proportional hard bound so a wedged run cannot pin the
             * indicator in the checking state forever. */
            const watchdog = timeout * 4;
            /* Refresh the package indexes first, best-effort: failures will
             * resurface per manager in the outdated report. */
            await Mpm.runCommand(
                Mpm.syncArgv(mpm, timeout), cancellable, watchdog);
            const result = await Mpm.runCommand(
                Mpm.outdatedArgv(mpm, timeout), cancellable, watchdog);
            if (result.stderr || !result.stdout) {
                this._setError(result.stderr || _('mpm produced no output.'));
                return;
            }
            let model;
            try {
                model = Mpm.parseOutdated(result.stdout);
            } catch (error) {
                this._setError(String(error));
                return;
            }
            lastModel = model;
            lastError = null;
            this._maybeNotify(model);
            this._showReport();
        } catch (error) {
            if (cancellable.is_cancelled())
                return;
            this._setError(String(error));
        } finally {
            this._checking = false;
            if (this._cancellable === cancellable)
                this._cancellable = null;
            if (!cancellable.is_cancelled()) {
                lastCheck = new Date();
                this._updateLastChecked();
                this._checkNowItem.reactive = true;
                this._checkNowItem.remove_style_class_name(
                    'popup-inactive-menu-item');
                this._scheduleCheck();
            }
        }
    }

    /* Render the last report: panel state plus the per-manager menu, in the
     * same order as bar_plugin_renderer._render(). */
    _showReport() {
        this._reportSection.removeAll();
        if (lastError !== null) {
            this._addErrorItems(this._reportSection, lastError);
            this._setPanelState(lastError.missing ? State.MISSING : State.ERROR);
            if (lastError.missing)
                this._addInstallItem();
            return;
        }
        if (lastModel === null) {
            this._setPanelState(State.UNKNOWN);
            return;
        }

        const groupByManager = this._settings.get_boolean('group-by-manager');
        lastModel.managers.forEach((manager, index) => {
            const count = manager.packages.length;
            const packageLabel = ngettext('package', 'packages', count);
            if (groupByManager) {
                /* Submenu header mirrors the table-mode section title. Where
                 * the bar plugin prefixes a ⚠️ character, this marks the same
                 * fact with the themed warning icon: an emoji is a font
                 * glyph the shell cannot restyle, and the GNOME reviewers ask
                 * for icons. */
                const title = `${manager.id} - ${count} ${packageLabel}`;
                const failed = manager.errors.length > 0;
                /* The second argument is the submenu's own icon slot: asking
                 * for it only when there is something to report keeps the
                 * healthy rows flush with the flat layout. */
                const submenu = new PopupMenu.PopupSubMenuMenuItem(title, failed);
                if (failed)
                    submenu.icon.icon_name = 'dialog-warning-symbolic';
                this._fillManagerSection(submenu.menu, manager);
                this._reportSection.addMenuItem(submenu);
            } else {
                /* The "---" separator the bar plugin prints between manager
                 * sections. */
                if (index > 0) {
                    this._reportSection.addMenuItem(
                        new PopupMenu.PopupSeparatorMenuItem());
                }
                const title = _('%d outdated %s %s').format(
                    count, manager.name, packageLabel);
                const header = new PopupMenu.PopupMenuItem(title, {
                    reactive: false,
                    style_class: 'mpm-manager-header',
                });
                this._reportSection.addMenuItem(header);
                this._fillManagerSection(this._reportSection, manager);
            }
        });

        if (lastModel.totalOutdated > 0)
            this._setPanelState(State.UPDATES, lastModel.totalOutdated);
        else if (lastModel.totalErrors > 0)
            this._setPanelState(State.ERROR);
        else
            this._setPanelState(State.UPTODATE);
    }

    /* One manager's packages, upgrade-all entry and error lines, appended to
     * either the flat report section or its own submenu. */
    _fillManagerSection(section, manager) {
        for (const pkg of manager.packages)
            section.addMenuItem(this._makePackageItem(manager, pkg));
        if (manager.packages.length > 0) {
            const upgradeAll = new PopupMenu.PopupImageMenuItem(
                _('Upgrade all %s packages').format(manager.id),
                STATE_ICONS[State.UPDATES]);
            upgradeAll.connectObject('activate', () => {
                this.menu.close();
                this._runAction(Mpm.upgradeAllArgv(lastMpm, manager.id));
            }, this);
            section.addMenuItem(upgradeAll);
        }
        for (const error of manager.errors)
            this._addErrorItems(section, {message: error});
    }

    /* A package row: name stretched left, version diff on the right with the
     * common prefix dimmed and the changed suffixes colored, mirroring
     * diff_versions(). Activating runs the mpm upgrade for that package. */
    _makePackageItem(manager, pkg) {
        const item = new PopupMenu.PopupBaseMenuItem();
        item.add_child(new St.Label({
            text: pkg.name,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'mpm-package-name',
        }));
        const diff = Mpm.diffVersions(pkg.installedVersion, pkg.latestVersion);
        const cells = [
            [diff.prefix, 'mpm-version-prefix'],
            [diff.oldSuffix, 'mpm-version-old'],
            [' → ', 'mpm-version-arrow'],
            [diff.prefix, 'mpm-version-prefix'],
            [diff.newSuffix, 'mpm-version-new'],
        ];
        /* The cells spell out two version strings, so they go in a box of
         * their own: added straight to the menu item, each would be held off
         * the next by the shell theme's own popup-menu-item spacing, splitting
         * "5.0.0~beta1" into "5.0." and "0~beta1". */
        const versions = new St.BoxLayout({
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'mpm-version-diff',
        });
        for (const [text, styleClass] of cells) {
            if (text === '')
                continue;
            versions.add_child(new St.Label({
                text,
                y_align: Clutter.ActorAlign.CENTER,
                style_class: styleClass,
            }));
        }
        item.add_child(versions);
        item.connectObject('activate', () => {
            this.menu.close();
            this._runAction(
                Mpm.upgradePackageArgv(lastMpm, manager.id, pkg.id));
        }, this);
        return item;
    }

    /* Red monospace error lines, non-reactive, one per line of the message
     * (the print_error() rendering of the bar plugin). */
    _addErrorItems(section, error) {
        for (const line of String(error.message).split('\n')) {
            if (line.trim() === '')
                continue;
            const item = new PopupMenu.PopupBaseMenuItem({reactive: false});
            item.add_child(new St.Label({
                text: line,
                style_class: 'mpm-error-line',
            }));
            section.addMenuItem(item);
        }
    }

    /* The bootstrap items of the MISSING state, the same pair bar_plugin.py
     * offers: a global uv install run through the regular action path, and the
     * installation page for every system uv does not answer for. */
    _addInstallItem() {
        const install = new PopupMenu.PopupMenuItem(_('Install mpm with uv'));
        install.connectObject('activate', () => {
            this.menu.close();
            this._runAction(Mpm.INSTALL_ARGV);
        }, this);
        this._reportSection.addMenuItem(install);

        const docs = new PopupMenu.PopupMenuItem(
            _('Open mpm installation instructions'));
        docs.connectObject('activate', () => {
            this.menu.close();
            Gio.AppInfo.launch_default_for_uri(Mpm.INSTALL_DOCS_URL, null);
        }, this);
        this._reportSection.addMenuItem(docs);
    }

    _setMissing(message) {
        lastModel = null;
        lastError = {message, missing: true};
        this._showReport();
    }

    _setError(message) {
        lastModel = null;
        lastError = {message, missing: false};
        this._showReport();
    }

    /* Desktop notification when outdated packages appear that were not in the
     * previous report. Opt-in, GNOME 46 MessageTray API. */
    _maybeNotify(model) {
        const current = new Set();
        for (const manager of model.managers) {
            for (const pkg of manager.packages)
                current.add(`${manager.id}/${pkg.id}`);
        }
        const fresh = knownOutdated === null
            ? [...current]
            : [...current].filter(key => !knownOutdated.has(key));
        knownOutdated = current;
        if (fresh.length === 0 || !this._settings.get_boolean('notify'))
            return;

        if (this._notifSource === null) {
            this._notifSource = new MessageTray.Source({
                title: this._extension.metadata.name,
                icon: this._stateIcon(State.UPDATES),
            });
            this._notifSource.connectObject('destroy', () => {
                this._notifSource = null;
            }, this);
            Main.messageTray.add(this._notifSource);
        }
        const title = ngettext(
            '%d package can be upgraded',
            '%d packages can be upgraded',
            model.totalOutdated).format(model.totalOutdated);
        const notification = new MessageTray.Notification({
            source: this._notifSource,
            title,
            body: fresh.map(key => key.split('/').pop()).join(', '),
        });
        this._notifSource.addNotification(notification);
    }

    /* Spawn an upgrade command, in a terminal by default so progress is
     * visible and sudo can prompt. Then arm the post-upgrade re-check:
     * terminal processes detach, so completion cannot be awaited. */
    _runAction(argv) {
        try {
            if (this._settings.get_boolean('upgrade-in-terminal')) {
                const terminal = Mpm.findTerminal(
                    this._settings.get_string('terminal-command'));
                if (terminal === null) {
                    Main.notifyError(
                        _('No terminal emulator found'),
                        _('Set one in the Meta Package Manager extension settings.'));
                    return;
                }
                Mpm.spawnDetached(Mpm.terminalArgv(terminal, argv));
            } else {
                Mpm.spawnDetached(argv);
            }
        } catch (error) {
            Main.notifyError(_('Could not launch the upgrade'), String(error));
            return;
        }
        this._armOneShot(this._settings.get_int('post-upgrade-recheck'));
    }

    /* Settings changes re-render and re-arm timers, but never re-check. */
    _onSettingsChanged() {
        this._showReport();
        this._updateLastChecked();
        if (!this._checking)
            this._scheduleCheck();
    }

    destroy() {
        /* Cancel first: that is what tells an in-flight check it has outlived
         * the indicator, and what drops the watchdog source runCommand armed
         * for it. Then no timer, signal or source is left to fire. */
        if (this._cancellable !== null) {
            this._cancellable.cancel();
            this._cancellable = null;
        }
        if (this._checkTimeoutId) {
            GLib.source_remove(this._checkTimeoutId);
            this._checkTimeoutId = null;
        }
        this._clearOneShot();
        this._settings.disconnectObject(this);
        if (this._notifSource !== null) {
            this._notifSource.disconnectObject(this);
            this._notifSource.destroy();
            this._notifSource = null;
        }
        this._settings = null;
        this._extension = null;
        super.destroy();
    }
});

export default class MpmExtension extends Extension {
    enable() {
        this._indicator = new MpmIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
