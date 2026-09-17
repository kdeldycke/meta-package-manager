/* Meta Package Manager GNOME Shell extension.
 *
 * A panel indicator with the same job as the SwiftBar/Xbar plugin: it lists
 * the outdated packages that `mpm outdated` reports for every package manager.
 * Each menu action runs `mpm`, so the user's mpm configuration file governs
 * the click (manager selection, sudo policy, per-manager overrides,
 * cooldown).
 *
 * mpm.js holds the subprocess code and the menu model. This file holds the
 * widgets, the timers and the lifecycle.
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

/* States of the panel indicator. STATE_ICONS below gives each one an icon
 * name. UPDATES and UPTODATE match the 🎁↑N and 📦✓ title states of the bar
 * plugin. ERROR covers a failed check, a missing mpm (the ❗️ state of
 * bar_plugin.py) and one manager's error marker. */
const State = {
    UNKNOWN: 'unknown',
    CHECKING: 'checking',
    UPTODATE: 'uptodate',
    UPDATES: 'updates',
    ERROR: 'error',
};

/* Each state renders as a stock symbolic icon from the icon theme, with no
 * artwork of our own. The shell colors these icons with the panel foreground,
 * the user's theme (Yaru on Ubuntu) can change their style, and every
 * other GNOME update indicator already gives them the same meaning. The
 * `software-update-*` names are for this exact use.
 *
 * CHECKING keeps a static icon. The Spinner of the shell (ui/animation.js) is
 * for dialogs only and never for the top bar, and the shell removed the
 * AnimatedIcon sprite sheet that used to drive animated status icons. An
 * animation would also make the compositor repaint during a background check
 * that nobody watches. `view-refresh-symbolic` means work in progress.
 * `content-loading-symbolic` means an expandable "..." in a panel.
 * apt-update-indicator uses `emblem-synchronizing-symbolic`, which a recent
 * Adwaita no longer ships. */
const STATE_ICONS = {
    unknown: 'content-loading-symbolic',
    checking: 'view-refresh-symbolic',
    uptodate: 'selection-mode-symbolic',
    updates: 'software-update-available-symbolic',
    error: 'software-update-urgent-symbolic',
};

/* Colors of the version diff. They are here and not in the stylesheet,
 * because the five labels of one row became one label with Pango markup, and
 * Pango markup takes a literal color. The convention matches Xbar and
 * SwiftBar: the common prefix is dimmed, the installed suffix is red and the
 * latest suffix is green. Each color has a mid luminance, which is readable on
 * the light and on the dark shell theme. */
const VERSION_COLORS = {
    prefix: '#9a9996',
    old: '#ed333b',
    new: '#2ec27e',
};

/* Return spaces to fill a column. The count is never negative. */
function padding(width) {
    return ' '.repeat(Math.max(0, width));
}

/* Return one Pango markup span. The result is empty for an empty text, so a
 * version with no common prefix with the next one renders no span for that
 * prefix. */
function colorSpan(text, color) {
    if (!text)
        return '';
    return `<span color="${color}">${GLib.markup_escape_text(text, -1)}</span>`;
}

/* This state is at module scope, so a disable()/enable() cycle at screen lock
 * does not start the boot check again and does not lose the last report. This
 * is the same pattern as arch-update. The state holds plain data only: a
 * GObject instance must not exist after disable(). */
let firstBoot = true;
let lastCheck = null;
let lastMpm = null;
let lastVersion = null;
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
        /* destroy() cancels it, so an upgrade that this indicator waited for
         * cannot call the indicator after the indicator is gone. */
        this._actionCancellable = new Gio.Cancellable();
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

        /* connectObject() records every signal against this indicator, so
         * teardown is one disconnectObject() call per emitter and not one
         * handler id per connection. The shell disconnects the other handlers
         * with the actor. */
        this._settings.connectObject(
            'changed', () => this._onSettingsChanged(), this);

        if (firstBoot) {
            /* Delay the first check, to keep the session start fast. A later
             * enable() cycle (screen lock) does not set this delay again. */
            this._armOneShot(this._settings.get_int('boot-wait'));
        } else {
            this._showReport();
            this._scheduleCheck();
        }
    }

    /* Build the fixed parts of the menu. The report section is rebuilt at
     * each refresh. The footer (Check now, last-checked, Settings) stays. */
    _buildMenu() {
        /* The interactive package items are in an inner PopupMenuSection
         * inside a ScrollView, so a large report scrolls and does not grow past
         * the screen. GNOME popup menus do not scroll on their own, and
         * stylesheet.css sets the maximum height. Only the actor of the section
         * is embedded, and the section itself is never registered with the
         * menu, so its `_parent` stays null. An item activation then stops in
         * the section's own close() method, which does nothing, and the panel
         * menu stays open. The action items close the menu themselves. */
        this._reportSection = new PopupMenu.PopupMenuSection();
        /* A section with no parent is a top menu of its own, and the submenus
         * of the grouped layout call `_setOpenedSubMenu` on it. A plain
         * PopupMenuSection has no such method, as reported upstream in
         * https://gitlab.gnome.org/GNOME/gnome-shell/-/work_items/9424. A
         * grouped check would then raise an error inside a signal handler, and
         * a `removeAll` that removes an open submenu would turn that error into
         * a shell crash. This code is a copy of the one in PopupMenu, so one
         * manager section stays open at a time. */
        this._reportSection._openedSubMenu = null;
        this._reportSection._setOpenedSubMenu = submenu => {
            if (this._reportSection._openedSubMenu)
                this._reportSection._openedSubMenu.close(true);
            this._reportSection._openedSubMenu = submenu;
        };
        /* Hidden until a report fills it. The view always has its own
         * padding, so an empty view would show a band of blank menu. See
         * `_showReport()`. */
        this._reportView = new St.ScrollView({
            style_class: 'mpm-updates-list',
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            visible: false,
        });
        this._reportView.child = this._reportSection.actor;
        const scrollWrapper = new PopupMenu.PopupMenuSection();
        scrollWrapper.actor.add_child(this._reportView);
        this.menu.addMenuItem(scrollWrapper);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        /* "Check now" must keep the menu open. Adding the item to the section
         * box directly, with no addMenuItem call, skips the code that
         * closes the menu on activation, and the row stays clickable. This is
         * the method arch-update uses. */
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

    /* Set the panel icon, the count label and the visibility for one state. */
    _setPanelState(state, count = 0) {
        this._icon.gicon = this._stateIcon(state);
        const showCount = count > 0 && this._settings.get_boolean('show-count');
        this._countLabel.text = showCount ? String(count) : '';
        this._countLabel.visible = showCount;
        this.visible = count > 0 || state === State.ERROR ||
            this._settings.get_boolean('always-visible');
    }

    /* Show the progress of a check on the "Check now" row too: the row is
     * greyed out and its label changes while a check runs. arch-update and
     * apt-update-indicator both report progress here and not in the panel. */
    _setCheckNowBusy(busy) {
        this._checkNowItem.reactive = !busy;
        this._checkNowItem.label.text = busy ? _('Checking…') : _('Check now');
        const inactive = 'popup-inactive-menu-item';
        if (busy)
            this._checkNowItem.add_style_class_name(inactive);
        else
            this._checkNowItem.remove_style_class_name(inactive);
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

    /* One single-run timer for the boot delay and for the re-check after an
     * upgrade. Both start a full check. */
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

    _clearCheckTimer() {
        if (this._checkTimeoutId) {
            GLib.source_remove(this._checkTimeoutId);
            this._checkTimeoutId = null;
        }
    }

    /* Start the recurring check again. The delay is reduced by the time
     * already spent, so a lock/unlock cycle or a settings change does not reset
     * the countdown. This is arch-update's _scheduleCheck pattern. */
    _scheduleCheck() {
        this._clearCheckTimer();
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

    /* The full refresh sequence, the same one as bar_plugin.py's
     * print_menu(): find mpm, check its version, run `sync` and ignore its
     * failures, then run `outdated` with a JSON output. */
    async _checkUpdates() {
        if (this._checking)
            return;
        this._checking = true;
        /* The cancellable also tells a check that the indicator is gone:
         * destroy() cancels it, and the check reads its own cancellation. The
         * local variable keeps a second reference, because destroy() sets the
         * field to null while this run still reads it. */
        const cancellable = new Gio.Cancellable();
        this._cancellable = cancellable;
        this._setPanelState(State.CHECKING);
        this._setCheckNowBusy(true);

        try {
            const mpm = Mpm.findMpm(this._settings.get_string('mpm-command'));
            if (mpm === null) {
                this._setError(_('mpm not found on this system.'), true);
                return;
            }
            const probe = await Mpm.probeMpm(mpm, cancellable);
            if (!probe.runnable) {
                this._setError(
                    _('mpm cannot run: %s').format(probe.error), true);
                return;
            }
            if (!probe.upToDate) {
                const minimum = Mpm.MPM_MIN_VERSION.join('.');
                this._setError(
                    _('mpm is too old: version %s or newer is required.')
                        .format(minimum),
                    true);
                return;
            }
            lastMpm = mpm;
            lastVersion = probe.version;
            /* Parsed here, inside the try block, so a quote with no pair in
             * the setting is reported as the error of this check. */
            const options = [
                ...Mpm.shellEnvOptions(probe.version),
                ...Mpm.parseOptions(this._settings.get_string('mpm-options')),
            ];
            const timeout = this._settings.get_int('timeout');
            /* --timeout limits each manager command that mpm runs. mpm itself
             * needs a limit too, in proportion, so a hung run cannot leave the
             * indicator in the checking state forever. */
            const watchdog = timeout * 4;
            /* Refresh the package indexes first, and ignore the failures: the
             * outdated report shows them again, one manager at a time. */
            await Mpm.runCommand(
                Mpm.syncArgv(mpm, timeout, options), cancellable, watchdog);
            const result = await Mpm.runCommand(
                Mpm.outdatedArgv(mpm, timeout, options),
                cancellable, watchdog);
            /* The exit status is the test for a failed check. stderr alone is
             * not enough: a --verbosity option from mpm-options replaces the
             * CRITICAL value that outdatedArgv() sets, and a successful check
             * writes to stderr too. */
            if (result.status !== 0 || !result.stdout) {
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
                this._setCheckNowBusy(false);
                this._scheduleCheck();
            }
        }
    }

    /* Render the last report, then hide the view when the report is empty.
     *
     * The report is empty before the first check of a session, and the view's
     * padding would then show as a blank band above the menu. Hiding the
     * actor also makes the section around it look empty to
     * `isPopupMenuItemVisible()`. The shell then removes the separator below it
     * at the next open of the menu. */
    _showReport() {
        this._reportSection.removeAll();
        this._fillReport();
        this._reportView.visible = this._reportSection.numMenuItems > 0;
    }

    /* Set the panel state and build the menu of each manager, in the same
     * order as bar_plugin_renderer._render(). */
    _fillReport() {
        if (lastError !== null) {
            this._addErrorItems(this._reportSection, lastError);
            this._setPanelState(State.ERROR);
            if (lastError.missing)
                this._addInstallItem();
            return;
        }
        if (lastModel === null) {
            this._setPanelState(State.UNKNOWN);
            return;
        }

        const groupByManager = this._settings.get_boolean('group-by-manager');
        const rowsByManager = new Map(lastModel.managers.map(manager => [
            manager,
            manager.packages.map(pkg => ({
                pkg,
                diff: Mpm.diffVersions(pkg.installedVersion, pkg.latestVersion),
            })),
        ]));
        /* The flat layout uses one table for every manager. Its rows share a
         * column, and a width taken for one manager alone would leave the
         * arrows of each section out of line with the section above. A submenu
         * is a panel of its own and takes its own width: a width from all the
         * managers would pad a short manager to the longest version of the
         * report. This is the bar plugin's `align_managers()`. */
        const pooled = groupByManager
            ? null
            : this._versionWidths([...rowsByManager.values()].flat());

        lastModel.managers.forEach((manager, index) => {
            const rows = rowsByManager.get(manager);
            const widths = groupByManager ? this._versionWidths(rows) : pooled;
            const count = manager.packages.length;
            const packageLabel = ngettext('package', 'packages', count);
            if (groupByManager) {
                /* The submenu header is the section title of the table mode.
                 * The bar plugin puts a ⚠️ character in front of it. This code
                 * shows the same fact with the themed warning icon: an
                 * emoji is a font glyph that the shell cannot restyle, and the
                 * GNOME reviewers ask for icons. */
                const title = `${manager.id} - ${count} ${packageLabel}`;
                const failed = manager.errors.length > 0;
                if (count === 0 && !failed) {
                    /* A manager with nothing to report still gets its row:
                     * the row tells the user that the manager ran. It gets no
                     * submenu, because a submenu's expander arrow says
                     * that packages are behind it and then opens an empty
                     * panel. This row needs no header style of its own either.
                     * It sits between the manager rows, and not above a list
                     * like the flat layout's header. A non-reactive row is
                     * dimmed, and that is enough to say that there is nothing
                     * to open. */
                    this._reportSection.addMenuItem(
                        new PopupMenu.PopupMenuItem(title, {
                            reactive: false,
                            can_focus: false,
                        }));
                    return;
                }
                /* The second argument asks for the submenu's own icon slot.
                 * The code asks for it only when the manager has something to
                 * report, so the other rows keep the same left margin as in the
                 * flat layout. */
                const submenu = new PopupMenu.PopupSubMenuMenuItem(title, failed);
                /* A submenu is an St.ScrollView of its own, and St stops
                 * every wheel event that such a view receives, whether the view
                 * can use it or not. An expanded panel therefore took the wheel
                 * events, the report below it did not move, and the scrollbar
                 * was the only way down. Removing the events here costs
                 * nothing: `PopupSubMenu._needsScrollbar()` reads the maximum
                 * height of the top menu, and this menu sets that height on an
                 * inner actor, so the submenu never scrolls on its own. */
                submenu.menu.actor.set_mouse_scrolling(false);
                if (failed)
                    submenu.icon.icon_name = 'dialog-warning-symbolic';
                this._fillManagerSection(submenu.menu, manager, rows, widths);
                this._reportSection.addMenuItem(submenu);
            } else {
                /* The "---" separator that the bar plugin prints between the
                 * manager sections. */
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
                this._fillManagerSection(
                    this._reportSection, manager, rows, widths);
            }
        });

        if (lastModel.totalOutdated > 0)
            this._setPanelState(State.UPDATES, lastModel.totalOutdated);
        else if (lastModel.totalErrors > 0)
            this._setPanelState(State.ERROR);
        else
            this._setPanelState(State.UPTODATE);
    }

    /* Return the column widths in characters for a set of rows, or null when
     * the versions use the menu font instead. The two halves of a version are
     * padded, so every block has the same width. A block with a fixed width,
     * aligned to the right, puts the arrows on one vertical line. A block sized
     * for its own text leaves each arrow where its latest version ends. */
    _versionWidths(rows) {
        if (!this._settings.get_boolean('align-columns'))
            return null;
        return {
            old: Math.max(0, ...rows.map(
                r => r.diff.prefix.length + r.diff.oldSuffix.length)),
            latest: Math.max(0, ...rows.map(
                r => r.diff.prefix.length + r.diff.newSuffix.length)),
        };
    }

    /* Add one manager's packages, upgrade-all entry and error lines, to the
     * flat report section or to that manager's submenu. */
    _fillManagerSection(section, manager, rows, widths) {
        for (const {pkg, diff} of rows)
            section.addMenuItem(this._makePackageItem(manager, pkg, diff, widths));
        if (manager.packages.length > 0) {
            const upgradeAll = new PopupMenu.PopupImageMenuItem(
                _('Upgrade all %s packages').format(manager.id),
                STATE_ICONS[State.UPDATES]);
            upgradeAll.connectObject('activate', () => {
                this.menu.close();
                this._runAction(
                    Mpm.upgradeAllArgv(lastMpm, manager.id, this._mpmOptions()));
            }, this);
            section.addMenuItem(upgradeAll);
        }
        for (const error of manager.errors)
            this._addErrorItems(section, {message: error});
    }

    /* Build one package row: the name on the left, and the version diff on
     * the right with the common prefix dimmed and the changed suffixes
     * colored, as in diff_versions(). Activation runs the mpm upgrade for that
     * package. */
    _makePackageItem(manager, pkg, diff, widths) {
        const item = new PopupMenu.PopupBaseMenuItem();
        item.add_child(new St.Label({
            text: pkg.name,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'mpm-package-name',
        }));
        /* One label with markup, and not a box with five labels. A report of a
         * thousand packages would need every actor of every row at each scroll
         * step. Spans inside one label also cannot be separated by the shell
         * theme's popup-menu-item spacing. That spacing used to
         * split "5.0.0~beta1" into "5.0." and "0~beta1". */
        const dim = VERSION_COLORS.prefix;
        let markup =
            colorSpan(diff.prefix, dim) +
            colorSpan(diff.oldSuffix, VERSION_COLORS.old) +
            colorSpan(' → ', dim) +
            colorSpan(diff.prefix, dim) +
            colorSpan(diff.newSuffix, VERSION_COLORS.new);
        /* Every block starts with one space that has no color. A colored span
         * at the first character of a label renders in the menu's own text
         * color, and not in the color of the span. Pango parses the markup in
         * both cases, and every row has the space, so the column still
         * lines up. */
        if (widths) {
            /* Padded with spaces. Spaces have an equal width in a monospace
             * font only, so the whole block uses one. This is how the bar
             * plugin sets its aligned rows. */
            const lead = padding(
                widths.old - diff.prefix.length - diff.oldSuffix.length + 1);
            const trail = padding(
                widths.latest - diff.prefix.length - diff.newSuffix.length);
            markup =
                `<span font_family="monospace">${lead}${markup}${trail}</span>`;
        } else {
            markup = ` ${markup}`;
        }
        const versions = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        versions.clutter_text.set_markup(markup);
        item.add_child(versions);
        item.connectObject('activate', () => {
            this.menu.close();
            this._runAction(
                Mpm.upgradePackageArgv(
                    lastMpm, manager.id, pkg.id, this._mpmOptions()));
        }, this);
        return item;
    }

    /* Add the error lines: red, monospace, non-reactive, and one item per
     * line of the message. This is the bar plugin's print_error()
     * rendering. */
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

    /* Add the two items shown when mpm is missing. bar_plugin.py offers the
     * same pair: a global uv install, run through the regular action path, and
     * the installation page for a system where uv is not the right method. */
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

    /* Replace the report with an error. The `missing` flag also asks for the
     * two install items for a missing mpm. */
    _setError(message, missing = false) {
        lastModel = null;
        lastError = {message, missing};
        this._showReport();
    }

    /* Send a desktop notification when the report holds outdated packages that
     * the previous report did not have. The user must enable this option. Uses
     * the GNOME 46 MessageTray API. */
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

    /* Read the mpm-options setting at the time the action is built, and not at
     * the time of the last check. An option typed into the preferences then
     * takes effect at the next click, with no new check. A syntax error gives
     * no options here: the check is the place that reports it. The --shell-env
     * gate of the last check comes first either way, so a --no-shell-env typed
     * into the setting wins. */
    _mpmOptions() {
        const gate = Mpm.shellEnvOptions(lastVersion);
        try {
            return [
                ...gate,
                ...Mpm.parseOptions(this._settings.get_string('mpm-options')),
            ];
        } catch {
            return gate;
        }
    }

    /* Start an upgrade command. The default is a terminal, so the user sees
     * the progress and sudo can ask for a password. Then start the re-check
     * after the upgrade: a terminal process detaches, so the code cannot wait
     * for its end. */
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
                /* Nothing detaches here, so this process is the upgrade
                 * itself. Wait for it and run the re-check when it exits, with
                 * no post-upgrade-recheck delay. The branch above cannot do
                 * this: every terminal that mpm knows is a client of a server
                 * process. */
                const proc = Mpm.spawnDetached(argv);
                const cancellable = this._actionCancellable;
                proc.wait_async(cancellable, (source, result) => {
                    if (cancellable.is_cancelled())
                        return;
                    try {
                        source.wait_finish(result);
                    } catch (error) {
                        logError(error, 'mpm: awaiting an upgrade');
                    }
                    /* A failed run also gets a re-check: it may have upgraded
                     * some of the packages it received. */
                    this._armOneShot(1);
                });
            }
        } catch (error) {
            Main.notifyError(_('Could not launch the upgrade'), String(error));
            return;
        }
        this._armOneShot(this._settings.get_int('post-upgrade-recheck'));
    }

    /* A settings change renders the report again and starts the timers again.
     * It does not start a new check. */
    _onSettingsChanged() {
        this._showReport();
        this._updateLastChecked();
        if (!this._checking)
            this._scheduleCheck();
    }

    destroy() {
        /* Cancel first. The cancellation tells a running check that the
         * indicator is gone, and it removes the watchdog source that runCommand
         * started for that check. After this, no timer, signal or source can
         * still fire. */
        if (this._cancellable !== null) {
            this._cancellable.cancel();
            this._cancellable = null;
        }
        if (this._actionCancellable !== null) {
            this._actionCancellable.cancel();
            this._actionCancellable = null;
        }
        this._clearCheckTimer();
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
