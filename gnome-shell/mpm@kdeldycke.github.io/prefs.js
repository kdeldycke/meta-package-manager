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
        const aboutRow = new Adw.ActionRow({
            title: this.metadata.name,
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
        page.add(about);
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
