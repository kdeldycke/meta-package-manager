#
# spec file for package meta-package-manager
#
# Copyright (c) 2026 SUSE LLC and contributors
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via https://bugs.opensuse.org/
#


# mpm is an end-user CLI whose importable module is incidental, so it builds
# for the primary flavor only and keeps an unsuffixed /usr/bin/mpm, the shape
# httpie uses. %%primary_python comes from python-rpm-macros, so this follows
# the distribution's interpreter instead of pinning one.
%define pythons %{primary_python}

Name:           meta-package-manager
Version:        7.6.1
Release:        0
Summary:        Wraps all package managers with a unifying CLI
License:        GPL-2.0-or-later
URL:            https://mpm.run/
Source:         https://files.pythonhosted.org/packages/source/m/meta-package-manager/meta_package_manager-%{version}.tar.gz
BuildRequires:  python3-base
BuildRequires:  python3-pip
BuildRequires:  python3-uv-build >= 0.8
BuildRequires:  fdupes
BuildRequires:  python-rpm-macros
# SECTION runtime requirements, also imported by the test suite
BuildRequires:  python3-boltons >= 25
BuildRequires:  python3-click-extra >= 8.8.1
BuildRequires:  python3-extra-platforms >= 13.6
BuildRequires:  python3-packageurl-python >= 0.11
BuildRequires:  python3-tomli-w >= 1
BuildRequires:  python3-xmltodict >= 0.12
# /SECTION
# SECTION test requirements
# extra-platforms reads /etc/os-release to identify the build platform, and
# fails its detection tests when the build root carries none.
BuildRequires:  openSUSE-release
# PyYAML and tomlkit are parsers the documentation tests need; the SBOM tests
# skip themselves when cyclonedx-python-lib and spdx-tools are absent, which
# they are on openSUSE.
BuildRequires:  python3-PyYAML
BuildRequires:  python3-pytest >= 9
BuildRequires:  python3-tomlkit
# /SECTION
Requires:       python3-boltons >= 25
Requires:       python3-click-extra >= 8.8.1
Requires:       python3-extra-platforms >= 13.6
Requires:       python3-packageurl-python >= 0.11
Requires:       python3-tomli-w >= 1
Requires:       python3-xmltodict >= 0.12
# Unlock `mpm sbom --vulnerabilities`, which queries the OSV database.
Suggests:       python3-httpx >= 0.27
Suggests:       python3-platformdirs >= 4
BuildArch:      noarch

%description
mpm wraps the package managers installed on a machine behind a single CLI:
list, search, install, upgrade and remove packages across all of them at
once, snapshot the whole inventory to one file and restore it on another
machine.

zypper is one of the ~70 managers it drives.

%prep
%autosetup -p1 -n meta_package_manager-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
# bar_plugin.py carries the `#!/usr/bin/env python3` shebang Xbar and SwiftBar
# need to run it directly, which openSUSE rejects in an installed file.
# %%pyproject_install already rewrites the ones under _bindir, and nothing
# else, so this module is reached by path.
%python3_fix_shebang_path %{buildroot}%{python_sitelib}/meta_package_manager/bar_plugin.py
# mpm and meta-package-manager are one entry point under two names.
%fdupes %{buildroot}%{_bindir}
%fdupes %{buildroot}%{python_sitelib}

%check
# The integration layer drives the real package managers and the CLI
# end-to-end, which no build root can satisfy. Everything else is hermetic.
%pytest -m "not integration"

%files
%license license
%doc changelog.md readme.md
%{_bindir}/mpm
%{_bindir}/%{name}
%{python_sitelib}/meta_package_manager
%{python_sitelib}/meta_package_manager-%{version}.dist-info

%changelog
