# -*- coding: utf-8 -*-
#
# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

# pylint: disable=redefined-outer-name

import pytest
import simplejson as json

from .conftest import MANAGER_IDS, destructive, run_cmd, unless_macos
from .test_cli import CLISubCommandTests


class TestOutdated(CLISubCommandTests):


    subcmd = 'outdated'


    def test_default_all_manager(self, invoke):
        result = invoke(self.subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result.output)


    @pytest.mark.parametrize('mid', MANAGER_IDS)
    def test_single_manager(self, invoke, mid):
        result = invoke('--manager', mid, self.subcmd)
        assert result.exit_code == 0
        self.check_manager_selection(result.output, {mid})


    def test_json_parsing(self, invoke):
        result = invoke('--output-format', 'json', self.subcmd)
        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data
        assert isinstance(data, dict)
        assert set(data).issubset(MANAGER_IDS)

        for manager_id, info in data.items():
            assert isinstance(manager_id, str)
            assert isinstance(info, dict)

            assert isinstance(info['id'], str)
            assert isinstance(info['name'], str)

            keys = {'errors', 'id', 'name', 'packages'}
            if 'upgrade_all_cli' in info:
                assert isinstance(info['upgrade_all_cli'], str)
                keys.add('upgrade_all_cli')
            assert set(info) == keys

            assert isinstance(info['errors'], list)
            if info['errors']:
                assert set(map(type, info['errors'])) == {str}

            assert info['id'] == manager_id

            assert isinstance(info['packages'], list)
            for pkg in info['packages']:
                assert isinstance(pkg, dict)

                assert set(pkg) == {
                    'id', 'installed_version', 'latest_version', 'name',
                    'upgrade_cli'}

                assert isinstance(pkg['id'], str)
                assert isinstance(pkg['installed_version'], str)
                assert isinstance(pkg['latest_version'], str)
                assert isinstance(pkg['name'], str)
                assert isinstance(pkg['upgrade_cli'], str)


    def test_cli_format_plain(self, invoke):
        result = invoke(
            '--output-format', 'json', self.subcmd, '--cli-format', 'plain')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                assert isinstance(infos['upgrade_cli'], str)


    def test_cli_format_fragments(self, invoke):
        result = invoke(
            '--output-format', 'json', self.subcmd, '--cli-format', 'fragments')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                assert isinstance(infos['upgrade_cli'], list)
                assert set(map(type, infos['upgrade_cli'])) == {str}


    def test_cli_format_bitbar(self, invoke):
        result = invoke(
            '--output-format', 'json', self.subcmd, '--cli-format', 'bitbar')
        for outdated in json.loads(result.output).values():
            for infos in outdated['packages']:
                assert isinstance(infos['upgrade_cli'], str)
                assert 'param1=' in infos['upgrade_cli']


    @destructive
    @unless_macos
    def test_unicode_name(self, invoke):
        """ See #16. """
        # Install an old version of a package with a unicode name.
        # Old Cask formula for ubersicht 1.0.44.
        formula_url = (
            "https://raw.githubusercontent.com/Homebrew/homebrew-cask"
            "/103dde670d398ab32492783a3822132d47f9ebf6/Casks/ubersicht.rb")
        code, output, error = run_cmd('brew', 'cask', 'install', formula_url)
        assert code == 0
        assert not error
        assert 'Uebersicht-1.0.44.app.zip' in output
        assert 'Übersicht.app' in output

        # Look for reported available upgrade.
        result = invoke('--manager', 'cask', self.subcmd)
        assert result.exit_code == 0
        assert "ubersicht" in result.output
        assert "Übersicht" in result.output

        # Remove the installed package.
        # TODO: Use a fixture that yields to cleanup if test fail.
        run_cmd('brew', 'cask', 'uninstall', 'ubersicht')
        assert result.exit_code == 0
        assert not error


    @destructive
    @unless_macos
    def test_multiple_names(self, invoke):
        """ See #26. """
        # Install an old version of a package with multiple names.
        # Old Cask formula for xld 2016.09.20.
        formula_url = (
            "https://raw.githubusercontent.com/Homebrew/homebrew-cask"
            "/16ea1a95c76beaf2ff4dba161a86721d680756e8/Casks/xld.rb")
        code, output, error = run_cmd('brew', 'cask', 'install', formula_url)
        assert code == 0
        assert not error
        assert 'xld-20160920.dmg' in output
        assert 'XLD.app' in output

        # Look for reported available upgrade.
        result = invoke('--manager', 'cask', self.subcmd)
        assert result.exit_code == 0
        assert "xld" in result.output
        assert "X Lossless Decoder" in result.output

        # Remove the installed package.
        # TODO: Use a fixture that yields to cleanup if test fail.
        run_cmd('brew', 'cask', 'uninstall', 'xld')
        assert result.exit_code == 0
        assert not error
