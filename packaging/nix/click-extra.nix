{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pytestCheckHook,
  uv-build,
  boltons,
  click,
  cloup,
  deepmerge,
  extra-platforms,
  requests,
  tabulate,
  wcmatch,
}:

buildPythonPackage (finalAttrs: {
  pname = "click-extra";
  version = "7.13.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "click-extra";
    tag = "v${finalAttrs.version}";
    hash = "sha256-RGKFPnj493y/66UMRHLRNMhEHLtnbs1J2d+ffwo4pHM=";
  };

  build-system = [ uv-build ];

  dependencies = [
    boltons
    click
    cloup
    deepmerge
    extra-platforms
    requests
    tabulate
    wcmatch
  ];

  nativeCheckInputs = [ pytestCheckHook ];

  disabledTests = [
    # Tests require network access.
    "test_colored_help"
    "test_help_theme"
  ];

  pythonImportsCheck = [ "click_extra" ];

  meta = {
    description = "Drop-in replacement for Click to build colorful CLI";
    homepage = "https://github.com/kdeldycke/click-extra";
    changelog = "https://github.com/kdeldycke/click-extra/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
