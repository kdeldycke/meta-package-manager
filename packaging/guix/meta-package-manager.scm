;;; Meta Package Manager packaging for GNU Guix.
;;;
;;; This definition is maintained in the mpm repository and updated automatically
;;; on each release.  To use it locally:
;;;
;;;   guix install --load-path=packaging/guix meta-package-manager
;;;
;;; meta-package-manager and its dependencies are now part of GNU Guix upstream
;;; (gnu/packages/package-management.scm).  This in-tree copy is kept for local
;;; installs and drives the automated version bumps forwarded upstream.

(define-module (meta-package-manager)
  #:use-module (guix build-system pyproject)
  #:use-module (guix gexp)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-check)
  #:use-module (gnu packages python-xyz))

(define-public meta-package-manager
  (package
    (name "meta-package-manager")
    (version "7.0.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
             (url "https://github.com/kdeldycke/meta-package-manager")
             (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "1y56z5970kp540w408y0fzk7g7r27vplqqihdav7gf8mqzfd23sz"))))
    (build-system pyproject-build-system)
    ;; Upstream builds with uv-build, which is not yet packaged for Guix; fall
    ;; back to setuptools.  Skip the SBOM CLI test, which pulls heavy optional
    ;; dependencies that are not declared here.
    (arguments
     (list #:build-backend "setuptools.build_meta"
           #:test-flags #~(list "--ignore=tests/test_cli_sbom.py")))
    (native-inputs
     (list python-pytest
           python-pyyaml
           python-setuptools
           python-tomlkit))
    ;; Propagated inputs are available in Guix upstream.
    (propagated-inputs
     (list python-boltons
           python-click-extra
           python-extra-platforms
           python-packageurl-python
           python-tomli-w
           python-xmltodict))
    (home-page "https://kdeldycke.github.io/meta-package-manager/")
    (synopsis "Package managers abstraction and unification tool")
    (description "Meta Package Manager (mpm) is a CLI that wraps multiple
GNU/Linux package managers behind a unified interface.  It can list, search,
install, upgrade, and remove packages across all detected managers
simultaneously.  Output formats include tables, JSON, and CSV.")
    (license license:gpl2+)))
