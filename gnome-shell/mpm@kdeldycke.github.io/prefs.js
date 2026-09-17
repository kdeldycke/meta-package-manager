/* Preferences window of the Meta Package Manager GNOME Shell extension.
 *
 * Each row is bound to its GSettings key. The gschema file is the only source
 * for the types, the ranges and the default values.
 */

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {
    ExtensionPreferences,
    gettext as _,
} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

import * as Mpm from './mpm.js';

/* A failed probe's error holds raw CLI output. Put it on one line and cut
 * it, so one stderr dump does not make the row a dozen lines high. */
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
        menu.add(this._switchRow(settings, 'align-columns', {
            title: _('Center versions around the arrow'),
            subtitle: _('Sets them in a monospaced font.'),
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
        actions.add(this._entryRow(settings, 'mpm-options', {
            title: _('mpm options (empty for none)'),
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
        /* The product name alone does not separate the two rows: `mpm` is the
         * name of the CLI below as much as the name of the extension. The text
         * says "GNOME extension" and not "GNOME Shell extension", because the
         * longer one goes onto a second line and the row cannot get more space.
         * `Adw.PreferencesPage` limits the width of its content: a window 80
         * logical pixels wider gave only 23 of them to the title. */
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

        /* The row above shows the extension's own version, compiled into
         * metadata.json. This row shows the CLI, which is installed separately
         * and which the extension runs. A bug report needs both. The
         * preferences run in a process of their own and cannot read the running
         * indicator, so this code finds the tool and probes it in the same way
         * as the extension does. */
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

    /* Return two lines for the About row: the answer of the tool, then the
     * command that gave it. A missing or outdated CLI is visible here, and not
     * only as a broken menu. */
    async _describeMpm(settings, cancellable) {
        const mpm = Mpm.findMpm(settings.get_string('mpm-command'));
        if (mpm === null) {
            return _('Not found. Install it from %s')
                .format(Mpm.INSTALL_DOCS_URL);
        }
        /* A plain join, and not `shellJoin`: this is a label for the user to
         * read, and GLib.shell_quote puts quotes around an ordinary path
         * too. */
        const command = mpm.join(' ');
        const result = await Mpm.probeMpm(mpm, cancellable);
        const release = result.release ?? result.version?.join('.');
        let verdict;
        if (!result.runnable) {
            verdict = _('Failed to run: %s').format(oneLine(result.error));
        } else if (!result.upToDate) {
            verdict = _('%s, older than the required %s').format(
                release, Mpm.MPM_MIN_VERSION.join('.'));
        } else {
            verdict = release;
        }
        return `${verdict}\n${command}`;
    }

    /* Row builders. The bounds of the Gtk.Adjustment repeat the ranges of the
     * gschema, and the gschema is the authority: it rejects a write outside its
     * range. */

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
