{
  lib,
  python3Packages,
  fetchFromGitHub,
}:

python3Packages.buildPythonApplication (finalAttrs: {
  pname = "meta-package-manager";
  version = "6.3.0";
  pyproject = true;
  __structuredAttrs = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "meta-package-manager";
    tag = "v${finalAttrs.version}";
    hash = "sha256-ZYPBy2k6SFElhICJxXYhLXlvf43VoQ1soW6VRuY2zHA=";
  };

  build-system = with python3Packages; [ uv-build ];

  dependencies = with python3Packages; [
    boltons
    click-extra
    cyclonedx-python-lib
    extra-platforms
    more-itertools
    packageurl-python
    spdx-tools
    tomli-w
    xmltodict
  ];

  # Tests require network access and system package managers.
  doCheck = false;

  pythonImportsCheck = [ "meta_package_manager" ];

  meta = {
    description = "CLI wrapping all package managers with a unifying interface";
    homepage = "https://github.com/kdeldycke/meta-package-manager";
    changelog = "https://github.com/kdeldycke/meta-package-manager/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
    mainProgram = "mpm";
  };
})
