# History

The `package_manager.py` script
[started its life in my `dotfile` repository](https://github.com/kdeldycke/dotfiles/commit/bfcc51e318b40c4283974548cfa1712d082be121#diff-c8127ac6af9d4a21e366ff740db2eeb5)
in 2016. It was a rewrite of the
[`brew-updates.sh` script](https://github.com/matryer/xbar-plugins/blob/master/Dev/Homebrew/brew-updates.1h.sh)
from Bash to Python.

I then
[merged both Homebrew and Cask](https://github.com/kdeldycke/dotfiles/commit/792d32bfddfc3511ea10c10513b62e269f145148#diff-c8127ac6af9d4a21e366ff740db2eeb5)
upgrade in the same single script to fix an
[issue preventing them to run concurrently](https://github.com/matryer/xbar-plugins/issues/493).

I finally
[proposed the script for inclusion](https://github.com/matryer/xbar-plugins/pull/466)
in the official
[xbar plugin repository](https://github.com/matryer/xbar-plugins). It lived
there for a couple of weeks and saw a huge amount of contributions by the
community.

With its complexity increasing, it was
[decided to move the plugin](https://github.com/matryer/xbar-plugins/issues/525)
to {gh}`its own repository <>`. For details, see the
[migration script](https://gist.github.com/kdeldycke/13712cb70e9c1cf4f338eb10dcc059f0).
