Package Manager
===============

A bitbar plugin to list package updates available from Homebrew, Cask, Python's
pip2 and pip3, Node's npm, Atom's apm, Rebuy's gem and Mac AppStore via mas
CLI. Allows individual or full upgrades (if available).

![Bitbar plugin screenshot
](https://raw.githubusercontent.com/kdeldycke/package-manager/develop/screenshot.png)


History
-------

See: https://github.com/matryer/bitbar-plugins/issues/525


Changelog
---------

### [**1.8.dev** (unreleased)](https://github.com/kdeldycke/package-manager/compare/v1.7...develop)

* No changes yet.

### [**1.7** (2016-08-16)](https://github.com/kdeldycke/package-manager/compare/v1.6...v1.7)

* Fix issues with $PATH not having Homebrew/Macports
* New workaround for full pip upgrade command
* Workaround for Homebrew Cask full upgrade command
* Grammar fix when 0 packages need updated

### [**1.6** (2016-08-10)](https://github.com/kdeldycke/package-manager/compare/v1.5...v1.6)

* Work around the lacks of full pip upgrade command.
* Fix UnicodeDecodeError on parsing CLI output.

### [**1.5** (2016-07-25)](https://github.com/kdeldycke/package-manager/compare/v1.4...v1.5)

* Add support for [mas](https://github.com/argon/mas).
* Don't show all stderr as err (check return code for error state).

### [**1.4** (2016-07-10)](https://github.com/kdeldycke/package-manager/compare/v1.3...v1.4)

* Don't attempt to parse empty lines.
* Check for linked npm packages.
* Support System or Homebrew Ruby Gems (with proper sudo setup).

### [**1.3** (2016-07-09)](https://github.com/kdeldycke/package-manager/compare/v1.2...v1.3)

* Add changelog.
* Add reference to package manager's issues.
* Force Cask update before evaluating available packages.
* Add sample of command output as version parsing can be tricky.

### [**1.2** (2016-07-08)](https://github.com/kdeldycke/package-manager/compare/v1.1...v1.2)

* Add support for both pip2 and pip3, Node's npm, Atom's apm, Ruby's gem.
  Thanks @tresni.
* Fixup brew cask checking. Thanks @tresni.
* Don't die on errors. Thanks @tresni.

### [**1.1** (2016-07-07)](https://github.com/kdeldycke/package-manager/compare/v1.0...v1.1)

* Add support for Python's pip.

### [**1.0** (2016-07-05)](https://github.com/kdeldycke/package-manager/commit/170ce9)

* Initial public release.
* Add support for Homebrew and Cask.
