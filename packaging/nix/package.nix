{
  lib,
  python3Packages,
  fetchFromGitHub,
}:

python3Packages.buildPythonApplication (finalAttrs: {
  pname = "meta-package-manager";
  version = "7.3.0";
  pyproject = true;
  __structuredAttrs = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "meta-package-manager";
    tag = "v${finalAttrs.version}";
    hash = "sha256-QyDUGwTSgYLe3EpUYre1KzvhnbH4i7vcpATS8wyeRYc=";
  };

  build-system = with python3Packages; [ uv-build ];

  dependencies = with python3Packages; [
    boltons
    click-extra
    extra-platforms
    packageurl-python
    tomli-w
    xmltodict
  ];

  # Tests require network access and system package managers.
  doCheck = false;

  pythonImportsCheck = [ "meta_package_manager" ];

  meta = {
    description = "Package managers abstraction and unification tool";
    homepage = "https://kdeldycke.github.io/meta-package-manager/";
    changelog = "https://github.com/kdeldycke/meta-package-manager/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
    mainProgram = "mpm";
  };
})
