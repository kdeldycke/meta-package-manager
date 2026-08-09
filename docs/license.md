# {octicon}`law` Legal notices

## License

Copyright Kevin Deldycke and contributors.

This software is licensed under the [GNU General Public License v2 or later (GPLv2+)](https://github.com/kdeldycke/meta-package-manager/blob/main/license), and so is its documentation.

```{literalinclude} ../license
```

## Trademarks

`mpm` exists to drive other people's package managers, so their names, logos and product names are all over this site. Each one is the property of its owner and is used here nominatively, to identify the tool `mpm` wraps and nothing more. No affiliation with, sponsorship by or endorsement from any of them is claimed or implied.

## Package manager logos

```{python:render}
from meta_package_manager._docs import manager_logo_credits

print(manager_logo_credits())
```

## Documentation artwork

The mascot and logo are derived from [Open Clipart](https://openclipart.org), distributed under a [Creative Commons Zero 1.0 Public Domain License](http://creativecommons.org/publicdomain/zero/1.0/):

- [happy paper box](https://github.com/kdeldycke/meta-package-manager/blob/main/docs/assets/happy-paper-box.svg) is sourced from [paper box head 3](https://openclipart.org/detail/300435/paper-box-head-3)
- [angry paper box](https://github.com/kdeldycke/meta-package-manager/blob/main/docs/assets/angry-paper-box.svg) is sourced from [paper box head](https://openclipart.org/detail/300407/paper-box-head)
- [multi-box logo](https://github.com/kdeldycke/meta-package-manager/blob/main/docs/assets/logo-banner.svg) is based on a modified [Packaging icons](https://openclipart.org/detail/190311/packaging-icons)

The page titles and sidebar entries use [Octicons](https://primer.style/foundations/icons/), MIT-licensed and copyright GitHub Inc., reached through [sphinx-design](https://github.com/executablebooks/sphinx-design)'s bundled copy for the `{octicon}` role and inlined into `docs/_static/custom.css` for the sidebar.

[XKCD #1654 - *Universal Install Script*](https://xkcd.com/1654/), shown on the [home page](index.md) and in [duplicate packages](duplicates.md), is the work of Randall Munroe under a [Creative Commons Attribution-NonCommercial 2.5 License](https://xkcd.com/license.html).

## Dependency licenses

`mpm`'s own dependencies and their version constraints are laid out in the [packaging guide](packaging.md#dependencies).