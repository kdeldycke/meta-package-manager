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
      extra-platforms = self.callPackage ./extra-platforms.nix { };
    };
  };
in
pkgs.callPackage ./package.nix {
  python3Packages = python3.pkgs;
  inherit (pkgs) lib fetchFromGitHub;
}
