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

""" Expose package-wide elements. """

import logging
import re

from .bitbar import fix_environment

__version__ = '3.2.0'
""" Examples of valid version strings according :pep:`440#version-scheme`:

.. code-block:: python

    __version__ = '1.2.3.dev1'   # Development release 1
    __version__ = '1.2.3a1'      # Alpha Release 1
    __version__ = '1.2.3b1'      # Beta Release 1
    __version__ = '1.2.3rc1'     # RC Release 1
    __version__ = '1.2.3'        # Final Release
    __version__ = '1.2.3.post1'  # Post Release 1
"""


logger = logging.getLogger(__name__)


fix_environment()


# Based on https://en.wikipedia.org/wiki/ANSI_escape_code#Escape_sequences
ANSI_SEQUENCES = re.compile(r'''
    \x1B            # Sequence starts with ESC, i.e. hex 0x1B
    (?:
        [@-Z\\-_]   # Second byte:
                    #   all 0x40–0x5F range but CSI char, i.e ASCII @A–Z\]^_
    |               # Or
        \[          # CSI sequences, starting with [
        [0-?]*      # Parameter bytes:
                    #   range 0x30–0x3F, ASCII 0–9:;<=>?
        [ -/]*      # Intermediate bytes:
                    #   range 0x20–0x2F, ASCII space and !"#$%&'()*+,-./
        [@-~]       # Final byte
                    #   range 0x40–0x7E, ASCII @A–Z[\]^_`a–z{|}~
    )
''', re.VERBOSE)


# XXX Local copy of boltons.strutils.strip_ansi().
# TODO: Replace with the boltons util function above once
# https://github.com/mahmoud/boltons/pull/258 get merged and released.
def strip_ansi(text):
    """Strips ANSI escape codes from *text*. Useful for the occasional
    time when a log or redirected output accidentally captures console
    color codes and the like.

    >>> strip_ansi('\x1b[0m\x1b[1;36mart\x1b[46;34m')
    'art'

    Supports unicode, str, bytes and bytearray content as input. Returns the
    same type as the input.

    There's a lot of ANSI art available for testing on `sixteencolors.net`_.
    This function does not interpret or render ANSI art, but you can do so with
    `ansi2img`_ or `escapes.js`_.

    .. _sixteencolors.net: http://sixteencolors.net
    .. _ansi2img: http://www.bedroomlan.org/projects/ansi2img
    .. _escapes.js: https://github.com/atdt/escapes.js
    """
    # Transform any ASCII-like content to unicode to allow regex to match, and
    # save input type for later.
    target_type = None
    if isinstance(text, (bytes, bytearray)):
        target_type = type(text)
        text = text.decode('utf-8')

    cleaned = ANSI_SEQUENCES.sub('', text)

    # Transform back the result to the same bytearray type provided by the
    # user.
    if target_type and target_type != type(cleaned):
        cleaned = target_type(cleaned, 'utf-8')

    return cleaned
