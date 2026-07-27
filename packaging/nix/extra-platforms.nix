{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pytestCheckHook,
  uv-build,
}:

buildPythonPackage (finalAttrs: {
  pname = "extra-platforms";
  version = "13.4.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "extra-platforms";
    tag = "v${finalAttrs.version}";
    hash = "sha256-gSEFscji1ecBOsYW+HV0X4Q6vzCkJUJYTfTfb7HEJms=";
  };

  build-system = [ uv-build ];

  nativeCheckInputs = [ pytestCheckHook ];

  # Tests marked ``network`` reach out to PyPI; the build sandbox has no
  # system TLS CA bundle. No per-test ignore list is needed beyond that:
  # since 13.4.0 the environment-detection tests self-skip in the
  # ``HOME=/homeless-shelter`` sandbox, the Sphinx cross-reference test skips
  # when ``uv`` is absent, and ``addopts`` no longer forces the coverage or
  # xdist plugins, so a plain ``pytest`` starts with neither installed.
  disabledTestMarks = [ "network" ];

  pythonImportsCheck = [ "extra_platforms" ];

  meta = {
    description = "Detect platforms, architectures and OS families";
    homepage = "https://github.com/kdeldycke/extra-platforms";
    changelog = "https://github.com/kdeldycke/extra-platforms/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.asl20;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
