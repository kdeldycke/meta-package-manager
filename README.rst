Package Manager
===============

A `BitBar <https://getbitbar.com>`_ plugin to simplify software upgrades from
several package managers.

.. image:: https://raw.githubusercontent.com/kdeldycke/package-manager/develop/screenshot.png
   :alt: Bitbar plugin screenshot.
   :align: center


Supported
---------

================  ===================  =============
Package manager   Individual upgrade   Full upgrade
================  ===================  =============
|homebrew|__      ✅                   ✅
|cask|__          ✅                   ✅
|pip2|__          ✅                   ✅
|pip3|__          ✅                   ✅
|npm|__           ✅                   ✅
|apm|__           ✅                   ✅
|gem|__           ✅                   ✅
|mas|__           ✅                   ✅
================  ===================  =============

.. |homebrew| replace::
   Homebrew
__ http://brew.sh
.. |cask| replace::
   Homebrew Cask
__ https://caskroom.github.io
.. |pip2| replace::
   Python 2 ``pip``
__ https://pypi.org
.. |pip3| replace::
   Python 3 ``pip``
__ https://pypi.org
.. |npm| replace::
   Node's ``npm``
__ https://www.npmjs.com
.. |apm| replace::
   Atom's ``apm``
__ https://atom.io/packages
.. |gem| replace::
   Ruby's ``gem``
__ https://rubygems.org
.. |mas| replace::
  Mac AppStore via `mas``
__ https://github.com/argon/mas


History
-------

The ``package_manager.py`` script `started its life in my ``dotfile``
repository
<https://github.com/kdeldycke/dotfiles/commit/bfcc51e318b40c4283974548cfa1712d082be121#diff-c8127ac6af9d4a21e366ff740db2eeb5>`_,
as a rewrite from Bash to Python of the ` ``brew-updates.sh`` script
<https://getbitbar.com/plugins/Dev/Homebrew/brew-updates.1h.sh>`_.

I then `merged both Homebrew and Cask
<https://github.com/kdeldycke/dotfiles/commit/792d32bfddfc3511ea10c10513b62e269f145148#diff-c8127ac6af9d4a21e366ff740db2eeb5>`_
upgrade in the same single script as both were `competing with each other
<https://github.com/matryer/bitbar-plugins/issues/493>`_ when run concurrently.

I finally `proposed the script for inclusion
<https://github.com/matryer/bitbar-plugins/pull/466>`_ in the official `BitBar
plugin repository <https://github.com/matryer/bitbar-plugins>`_. It lived there
for a couple of weeks and saw a huge amount of contributions by the community.

With its complexity increasing, it was `decided to move the plugin
<https://github.com/matryer/bitbar-plugins/issues/525>`_ to `its own repository
<https://github.com/kdeldycke/package-manager>`_.


Current status
--------------

Active development of the script is continuing here, in the exact same
conditions as we were before moving the repository, like nothing happened.

Each time we reach a releaseable script, we simply tag it and push a copy to
the BitBar plugin repository. Plain and simple.

At the same time we maintain a Python library on the side. The library is going
to handle all idiosyncracies of supported package managers under a unified API.

Once the library is good enough, we'll evaluate rebasing the original plugin on
it, and lay out a plan for a painless transition, from the standalone script to
a bare BitBar-plugin depending on the library alone.

In the mean time we have to temporarily manage duplicate code. But at least the
whole project is kept in one centralized place, trying to tackle the same
issues.


Contributors
------------

* `Kevin Deldycke <https://github.com/kdeldycke>`_
* `Brian Hartvigsen <https://github.com/tresni>`_


License
-------

The content of this repository is copyrighted (c) 2016 `Kevin Deldycke
<http://kevin.deldycke.com>`_.

This code is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, version 2, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

For full details, please see the file named COPYING in the top directory of the
source tree. You should have received a copy of the GNU General Public License
along with this program. If not, see `http://www.gnu.org/licenses/
<http://www.gnu.org/licenses/>`_.
