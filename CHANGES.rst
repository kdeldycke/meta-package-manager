Changelog
=========

`1.8.dev (unreleased) <https://github.com/kdeldycke/package-manager/compare/v1.7...develop>`_
---------------------------------------------------------------------------------------------

* Move the plugin to its own repository.
* Add a ``README.md`` file.
* License under GPLv2+.
* Add ``.gitignore`` config.
* Add Python package skeleton. Closes #1.
* Split changelog out of readme.
* Add Travis CI configuration.


`1.7 (2016-08-16) <https://github.com/kdeldycke/package-manager/compare/v1.6...v1.7>`_
--------------------------------------------------------------------------------------

* Fix issues with ``$PATH`` not having Homebrew/Macports.
* New workaround for full ``pip`` upgrade command.
* Workaround for Homebrew Cask full upgrade command.
* Grammar fix when 0 packages need updated.


`1.6 (2016-08-10) <https://github.com/kdeldycke/package-manager/compare/v1.5...v1.6>`_
--------------------------------------------------------------------------------------

* Work around the lacks of full ``pip`` upgrade command.
* Fix ``UnicodeDecodeError`` on parsing CLI output.


`1.5 (2016-07-25) <https://github.com/kdeldycke/package-manager/compare/v1.4...v1.5>`_
--------------------------------------------------------------------------------------

* Add support for ``mas``.
* Don't show all ``stderr`` as ``err`` (check return code for error state).


`1.4 (2016-07-10) <https://github.com/kdeldycke/package-manager/compare/v1.3...v1.4>`_
--------------------------------------------------------------------------------------

* Don't attempt to parse empty lines.
* Check for linked ``npm`` packages.
* Support system or Homebrew Ruby Gems (with proper ``sudo`` setup).


`1.3 (2016-07-09) <https://github.com/kdeldycke/package-manager/compare/v1.2...v1.3>`_
--------------------------------------------------------------------------------------

* Add changelog.
* Add reference to package manager's issues.
* Force Cask update before evaluating available packages.
* Add sample of command output as version parsing can be tricky.


`1.2 (2016-07-08) <https://github.com/kdeldycke/package-manager/compare/v1.1...v1.2>`_
--------------------------------------------------------------------------------------

* Add support for both ``pip2`` and ``pip3``, Node's ``npm``, Atom's ``apm``,
  Ruby's ``gem``.
* Fixup ``brew cask`` checking.
* Don't die on errors.


`1.1 (2016-07-07) <https://github.com/kdeldycke/package-manager/compare/v1.0...v1.1>`_
--------------------------------------------------------------------------------------

* Add support for Python's ``pip``.


`1.0 (2016-07-05) <https://github.com/kdeldycke/package-manager/commit/170ce9>`_
--------------------------------------------------------------------------------

* Initial public release.
* Add support for Homebrew and Cask.
