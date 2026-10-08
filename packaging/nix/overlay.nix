# The Python package-set overrides `mpm` needs, shared by both entry points.
#
# Kept in one file because those entry points are built by different commands:
# `nix-build` reads default.nix, while `nix build ./packaging/nix` reads the
# flake. They used to carry their own copy of this set, and a fix applied to
# one silently left the other broken — which is how the click override below
# came to build locally and still fail in CI.
{ pkgs }:
self: super: {
  click-extra = self.callPackage ./click-extra.nix { };

  # click-extra 9 declares `click>=8.4.1`, above the 8.3.x nixpkgs ships, so
  # its runtime dependency check rejects it before mpm is reached.
  #
  # Pinned to that floor rather than to the newer release `uv.lock` records,
  # because an override here reaches every package in this set, not just
  # click-extra: 8.5.0 deprecates `CliRunner.isolated_filesystem`, and httpx2
  # turns that warning into an error, which broke respx and with it mpm's own
  # check inputs. Pinning click-extra itself to the lowest 9.x is what keeps
  # this to one override: 9.2 onwards also raises boltons to >=26.2 and wcwidth
  # to >=0.8.3, neither of which nixpkgs carries.
  #
  # Drop this once nixpkgs ships click 8.4.1 or newer, which
  # https://github.com/NixOS/nixpkgs/pull/544890 (8.3.3 -> 8.4.2) would do.
  # That same PR is what lets NixOS/nixpkgs#506145 be refreshed past mpm
  # 7.6.1: click-extra 9 cannot build in nixpkgs until it lands.
  click = super.click.overridePythonAttrs (_: rec {
    version = "8.4.1";
    src = pkgs.fetchFromGitHub {
      owner = "pallets";
      repo = "click";
      tag = version;
      hash = "sha256-c+Bt6h14WDLjjyemuRjAt6OZ2tqJ9yIRAiB9N6RZ0KE=";
    };
  });

  # cloup pins its setuptools-scm build requirement below 10, which nixpkgs no
  # longer ships, so pypa/build's --no-isolation dependency check fails. Relax
  # the pin when present: version detection is bypassed anyway through
  # SETUPTOOLS_SCM_PRETEND_VERSION. Use --replace-quiet, not --replace-fail:
  # recent nixpkgs cloup revisions strip the pin in their own postPatch (which
  # runs first), so ours must no-op rather than error.
  # Reported at https://github.com/janluke/cloup/issues/206.
  cloup = super.cloup.overridePythonAttrs (old: {
    postPatch = (old.postPatch or "") + ''
      substituteInPlace setup.py \
        --replace-quiet "setuptools_scm<10" "setuptools_scm"
    '';
  });

  extra-platforms = self.callPackage ./extra-platforms.nix { };

  # The click override above rebuilds the HTTP stack behind mpm's check inputs,
  # and with it their own test suites. On a loaded macOS runner their timing
  # tests fail at random: `test_h2_timeout_during_response` of httpcore2 on one
  # run, `TestReceive.test_receive_timeout` of httpx2 on another. Both suites
  # pass on nixpkgs' own builders, so skip them on the one platform they flake.
  httpcore2 = super.httpcore2.overridePythonAttrs (_: {
    doCheck = !pkgs.stdenv.hostPlatform.isDarwin;
  });
  httpx2 = super.httpx2.overridePythonAttrs (_: {
    doCheck = !pkgs.stdenv.hostPlatform.isDarwin;
  });
}
