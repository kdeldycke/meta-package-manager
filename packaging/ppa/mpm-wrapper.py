#!/usr/bin/python3
"""Entry point of the Ubuntu `meta-package-manager` package.

The package ships its whole Python dependency tree under
`/usr/share/meta-package-manager`, which this wrapper puts first on
`sys.path`. Ubuntu carries neither `click-extra` nor `extra-platforms`, and
its `click` and `deepmerge` are older than `click-extra` accepts, so no import
mpm makes can resolve from `/usr/lib/python3/dist-packages`. Prepending is
what keeps the vendored copies ahead of the system ones, and it changes
nothing outside this process.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/usr/share/meta-package-manager")

from meta_package_manager.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
