History
=======

The ``package_manager.py`` script `started its life in my 'dotfile' repository
<https://github.com/kdeldycke/dotfiles/commit/bfcc51e318b40c4283974548cfa1712d082be121#diff-c8127ac6af9d4a21e366ff740db2eeb5>`_,
as a rewrite from Bash to Python of the `'brew-updates.sh' script
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
<https://github.com/kdeldycke/meta-package-manager>`_. For details, see the
`migration script
<https://gist.github.com/kdeldycke/13712cb70e9c1cf4f338eb10dcc059f0>`_.
