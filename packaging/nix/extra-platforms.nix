{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pytestCheckHook,
  uv-build,
}:

buildPythonPackage (finalAttrs: {
  pname = "extra-platforms";
  version = "11.1.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "extra-platforms";
    tag = "v${finalAttrs.version}";
    hash = "sha256-2bPkus9Lk3VwB27/WKFgN/kxKE2jPDKdV9U5oYKmMPc=";
  };

  build-system = [ uv-build ];

  nativeCheckInputs = [ pytestCheckHook ];

  pythonImportsCheck = [ "extra_platforms" ];

  meta = {
    description = "Detect platforms, architectures and OS families";
    homepage = "https://github.com/kdeldycke/extra-platforms";
    changelog = "https://github.com/kdeldycke/extra-platforms/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.asl20;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
