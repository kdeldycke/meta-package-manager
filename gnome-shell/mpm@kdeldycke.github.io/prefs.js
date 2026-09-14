/* Preferences window of the Meta Package Manager GNOME Shell extension.
 *
 * Every row is bound declaratively to its GSettings key: the gschema file is
 * the single source of truth for types, ranges and defaults.
 */

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {
    ExtensionPreferences,
    gettext as _,
} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

import * as Mpm from './mpm.js';

/* A probe failure carries raw CLI output: flatten and clip it so one stderr
 * dump never grows the row to a dozen lines. */
function oneLine(text, limit = 120) {
    const flat = String(text ?? '').replace(/\s+/g, ' ').trim();
    return flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat;
}

export default class MpmPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const page = new Adw.PreferencesPage({
            title: _('General'),
            icon_name: 'preferences-system-symbolic',
        });
        window.add(page);

        const checking = new Adw.PreferencesGroup({
            title: _('Checking for updates'),
        });
        checking.add(this._spinRow(settings, 'check-interval', {
            title: _('Check interval (minutes)'),
            subtitle: _('Checks are resource intensive: a several-hour cycle is recommended.'),
        }));
        checking.add(this._spinRow(settings, 'boot-wait', {
            title: _('Delay before the first check (seconds)'),
        }));
        checking.add(this._spinRow(settings, 'timeout', {
            title: _('mpm timeout (seconds)'),
        }));
        checking.add(this._spinRow(settings, 'post-upgrade-recheck', {
            title: _('Re-check delay after an upgrade (seconds)'),
        }));
        page.add(checking);

        const indicator = new Adw.PreferencesGroup({title: _('Indicator')});
        indicator.add(this._switchRow(settings, 'always-visible', {
            title: _('Always show the indicator'),
            subtitle: _('When disabled, only appears on outdated packages or errors.'),
        }));
        indicator.add(this._switchRow(settings, 'show-count', {
            title: _('Show the outdated package count'),
        }));
        page.add(indicator);

        const menu = new Adw.PreferencesGroup({title: _('Menu')});
        menu.add(this._switchRow(settings, 'group-by-manager', {
            title: _('Group packages by manager'),
        }));
        page.add(menu);

        const actions = new Adw.PreferencesGroup({title: _('Upgrades')});
        actions.add(this._switchRow(settings, 'upgrade-in-terminal', {
            title: _('Run upgrades in a terminal'),
            subtitle: _('Background upgrades need passwordless escalation for system managers.'),
        }));
        actions.add(this._entryRow(settings, 'terminal-command', {
            title: _('Terminal command (empty to autodetect)'),
        }));
        actions.add(this._entryRow(settings, 'mpm-command', {
            title: _('mpm command (empty to autodetect)'),
        }));
        page.add(actions);

        const notifications = new Adw.PreferencesGroup({
            title: _('Notifications'),
        });
        notifications.add(this._switchRow(settings, 'notify', {
            title: _('Notify when new outdated packages appear'),
        }));
        page.add(notifications);

        const about = new Adw.PreferencesGroup({title: _('About')});
        /* The product name alone would not tell the two rows apart: `mpm` is
         * the name of the CLI below as much as of the extension. "GNOME
         * extension" rather than the fuller "GNOME Shell extension" because
         * the longer one wraps onto a second line, and the row cannot be
         * widened out of it: `Adw.PreferencesPage` clamps its content, so a
         * window grown by 80 logical pixels passed only 23 of them to the
         * title. */
        const aboutRow = new Adw.ActionRow({
            title: _('%s (GNOME extension)').format(this.metadata.name),
            subtitle: this.metadata['version-name'] ?? '',
        });
        const logo = Gtk.Image.new_from_file(`${this.path}/icons/mpm-logo.svg`);
        logo.set_pixel_size(48);
        aboutRow.add_prefix(logo);
        const link = Gtk.LinkButton.new_with_label(
            'https://mpm.run/gnome-shell/',
            _('Documentation'));
        link.set_valign(Gtk.Align.CENTER);
        aboutRow.add_suffix(link);
        about.add(aboutRow);

        /* The row above carries the extension's own version, compiled into
         * metadata.json. This one reports the separately installed CLI it
         * drives, which is the other half a bug report needs. The preferences
         * run in their own process, with no access to the running indicator,
         * so the tool is resolved and probed here exactly as the extension
         * resolves and probes it. */
        const toolRow = new Adw.ActionRow({
            title: _('mpm command-line tool'),
            subtitle: _('Looking for it…'),
            subtitle_lines: 2,
            use_markup: false,
        });
        about.add(toolRow);
        const probe = new Gio.Cancellable();
        window.connect('close-request', () => {
            probe.cancel();
            return false;
        });
        this._describeMpm(settings, probe)
            .then(subtitle => {
                if (!probe.is_cancelled())
                    toolRow.subtitle = subtitle;
            })
            .catch(error => {
                if (!probe.is_cancelled())
                    toolRow.subtitle = oneLine(error);
            });
        page.add(about);
    }

    /* Two lines for the About row: what the tool answers, then the command
     * answering it. A missing or stale CLI shows up here rather than only as
     * a broken menu. */
    async _describeMpm(settings, cancellable) {
        const mpm = Mpm.findMpm(settings.get_string('mpm-command'));
        if (mpm === null) {
            return _('Not found. Install it from %s')
                .format(Mpm.INSTALL_DOCS_URL);
        }
        /* Plain join, not `shellJoin`: this is a label to read, and
         * GLib.shell_quote wraps even an ordinary path in quotes. */
        const command = mpm.join(' ');
        const result = await Mpm.probeMpm(mpm, cancellable);
        const release = result.release ?? result.version?.join('.');
        let verdict;
        if (!result.runnable)
            verdict = _('Failed to run: %s').format(oneLine(result.error));
        else if (!result.upToDate)
            verdict = _('%s, older than the required %s').format(
                release, Mpm.MPM_MIN_VERSION.join('.'));
        else
            verdict = release;
        return `${verdict}\n${command}`;
    }

    /* Row builders: the Gtk.Adjustment bounds duplicate the gschema ranges,
     * which remain authoritative (out-of-range writes are rejected there). */

    _spinRow(settings, key, params) {
        const range = settings.get_range(key).deep_unpack()[1].deep_unpack();
        const row = new Adw.SpinRow({
            ...params,
            adjustment: new Gtk.Adjustment({
                lower: range[0],
                upper: range[1],
                step_increment: 1,
                page_increment: 10,
            }),
        });
        settings.bind(key, row, 'value', Gio.SettingsBindFlags.DEFAULT);
        return row;
    }

    _switchRow(settings, key, params) {
        const row = new Adw.SwitchRow(params);
        settings.bind(key, row, 'active', Gio.SettingsBindFlags.DEFAULT);
        return row;
    }

    _entryRow(settings, key, params) {
        const row = new Adw.EntryRow(params);
        settings.bind(key, row, 'text', Gio.SettingsBindFlags.DEFAULT);
        return row;
    }
}
