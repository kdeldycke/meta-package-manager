# Install meta-package-manager from a local checkout while the nixpkgs PR is
# pending (https://github.com/NixOS/nixpkgs/pull/506145).
#
# Usage:
#   nix-env -f ./packaging/nix -i
#   nix-shell -p -f ./packaging/nix --run "mpm --version"
#
# Once click-extra and extra-platforms land in nixpkgs, the overlay below
# becomes unnecessary and this file reduces to a single callPackage.
{ pkgs ? import <nixpkgs> { } }:

let
  python3 = pkgs.python3.override {
    packageOverrides = self: super: {
      click-extra = self.callPackage ./click-extra.nix { };
      # cloup pins its setuptools-scm build requirement below 10, which
      # nixpkgs no longer ships, so pypa/build's --no-isolation dependency
      # check fails. Relax the pin when present: version detection is bypassed
      # anyway through SETUPTOOLS_SCM_PRETEND_VERSION. Use --replace-quiet, not
      # --replace-fail: recent nixpkgs cloup revisions strip the pin in their
      # own postPatch (which runs first), so ours must no-op rather than error.
      # Reported at https://github.com/janluke/cloup/issues/206.
      cloup = super.cloup.overridePythonAttrs (old: {
        postPatch = (old.postPatch or "") + ''
          substituteInPlace setup.py \
            --replace-quiet "setuptools_scm<10" "setuptools_scm"
        '';
      });
      # click-extra 9 declares `click>=8.4.1`, `boltons>=26.2` and
      # `wcwidth>=0.8.3`, all of which nixpkgs sits below, so the runtime
      # dependency check rejects it before mpm is reached. Each is pinned to
      # the version `uv.lock` records for the packaged mpm release rather than
      # to the bare floor, so the build reproduces the combination upstream
      # tested. Overriding inside this package set leaves the rest of nixpkgs
      # untouched, and each entry goes away as nixpkgs catches up.
      boltons = super.boltons.overridePythonAttrs (_: rec {
        version = "26.2.0";
        src = pkgs.fetchFromGitHub {
          owner = "mahmoud";
          repo = "boltons";
          tag = version;
          hash = "sha256-V6Kdamn2HHOjucKGrjCqjE/xExCJmyUAE11YwLjOkzI=";
        };
        # nixpkgs patches a pytest 9 compatibility fix into 25.0.0 that 26.2
        # already carries upstream, so the patch no longer applies.
        patches = [ ];
      });
      click = super.click.overridePythonAttrs (_: rec {
        version = "8.5.0";
        src = pkgs.fetchFromGitHub {
          owner = "pallets";
          repo = "click";
          tag = version;
          hash = "sha256-VYdaEN9l2MRVz42I8t8IDOpG5XeDM8bf34dLZy3yf10=";
        };
      });
      wcwidth = super.wcwidth.overridePythonAttrs (_: rec {
        version = "0.8.3";
        src = pkgs.fetchFromGitHub {
          owner = "jquast";
          repo = "wcwidth";
          tag = version;
          hash = "sha256-4GzYqoXdYqZjyB/iIsuOnwSjJGSKY9LitVKVDT2aUCo=";
        };
      });
      extra-platforms = self.callPackage ./extra-platforms.nix { };
    };
  };
in
pkgs.callPackage ./package.nix {
  python3Packages = python3.pkgs;
  inherit (pkgs) lib fetchFromGitHub;
}
