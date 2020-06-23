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

""" Collection of utilities to manage mpm project itself.
"""

from pathlib import Path

from boltons.iterutils import flatten
from simplejson import dumps as json_dumps

from meta_package_manager.managers import pool
from meta_package_manager.platform import ALL_OS_LABELS


def generate_labels():
    """ Generate GitHub labels to use in issues and PR management.
    """
    json_file = Path(__file__).parent.joinpath(
        '../.github/labels.json').resolve()

    # Format: label name, color, optional description.
    LABELS = [
        ("BitBar plugin", '#fef2c0',
         "Plugin code, documentation or features related to BitBar"),
        ("bug", '#d73a4a',
         "Something isn't working"),
        ("CI/CD", '#dbca13',
         "Automation and management of the project itself"),
        ("documentation", '#006b75',
         "Update to documentation's content or its generation"),
        ("duplicate", '#cfd3d7',
         "This issue or pull request already exists"),
        ("enhancement", '#84b6eb',
         "Improvement of an existing feature"),
        ("feature request", '#fbca04',
         "Something not existing yet that need to be implemented"),
        ("good first issue", '#7057ff',
         "A place for newcomers to start contributing"),
        ("help wanted", '#008672',
         "Extra attention is needed"),
        ("can't reproduce", '#fec1c1',
         "Root cause unlikely to come from the project"),
        ("question", '#d876e3',
         "Further information is requested"),
        ("wont do/fix", '#eeeeee',
         "This will not be worked on"),
    ]

    # Define some colors.
    PLATFORM_COLOR = '#bfd4f2'
    MANAGER_COLOR = '#bfdadc'

    # Some managers sharing some roots will be grouped together.
    MANAGER_GROUPS = {
        'dpkg-like': {'dpkg', 'apt', 'opkg'},
        'npm-like': {'npm', 'yarn'},
    }

    # Create one label per platform.
    for platform_id in ALL_OS_LABELS:
        LABELS.append((
            'platform: {}'.format(platform_id), PLATFORM_COLOR,
            '{}'.format(platform_id)))

    # Create one label per manager. Add mpm as its own manager.
    non_grouped_managers = set(
        pool()) - set(flatten(MANAGER_GROUPS.values())) | {'mpm'}
    for manager_id in non_grouped_managers:
        LABELS.append((
            'manager: {}'.format(manager_id), MANAGER_COLOR,
            '{}'.format(manager_id)))

    # Add labels for grouped managers.
    for group_label, manager_ids in MANAGER_GROUPS.items():
        LABELS.append((
            'manager: {}'.format(group_label), MANAGER_COLOR,
            ', '.join(sorted(manager_ids))))

    # Debug messages.
    for label_name, _, _ in sorted(LABELS):
        print("Generated label: {}".format(label_name))
    print("{} labels generated.".format(len(LABELS)))
    print("Saving to: {}".format(json_file))

    # Save to json definition file.
    label_defs = [
        dict(zip(['name', 'color', 'description'], label))
        for label in sorted(LABELS)]
    json_file.open('w').write(json_dumps(
        label_defs,
        indent=2,
        separators=(',', ': '),
    ))


if __name__ == '__main__':
    generate_labels()
