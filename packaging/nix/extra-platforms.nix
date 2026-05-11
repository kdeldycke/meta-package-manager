{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pytestCheckHook,
  requests,
  uv-build,
}:

buildPythonPackage (finalAttrs: {
  pname = "extra-platforms";
  version = "12.0.3";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "extra-platforms";
    tag = "v${finalAttrs.version}";
    hash = "sha256-OJ5ch1dfAnblC+3UCJ9I9P9sw8taGp8yBg//ZraunRo=";
  };

  build-system = [ uv-build ];

  nativeCheckInputs = [
    pytestCheckHook
    requests
  ];

  # Tests marked ``network`` fetch from PyPI.
  disabledTestMarks = [ "network" ];

  # test_sphinx_crossrefs.py shells out to ``uv``, unavailable in the build sandbox.
  disabledTestPaths = [ "tests/test_sphinx_crossrefs.py" ];

  pythonImportsCheck = [ "extra_platforms" ];

  meta = {
    description = "Detect platforms, architectures and OS families";
    homepage = "https://github.com/kdeldycke/extra-platforms";
    changelog = "https://github.com/kdeldycke/extra-platforms/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.asl20;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
