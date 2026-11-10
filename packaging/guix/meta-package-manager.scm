;;; Meta Package Manager packaging for GNU Guix.
;;;
;;; meta-package-manager and its dependencies are part of GNU Guix upstream
;;; (gnu/packages/package-management.scm).  This standalone copy is updated
;;; automatically on each release and drives the version bumps forwarded
;;; upstream.  To install from it:
;;;
;;;   guix install --load-path=packaging/guix meta-package-manager
;;;
;;; The Guix channel can ship older dependencies than this release needs.  The
;;; (meta-package-manager dependencies) module defines newer ones, and the
;;; #:hide clause below keeps the channel packages they replace out of scope.

(define-module (meta-package-manager)
  #:use-module (guix build-system pyproject)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module (gnu packages check)
  #:use-module (gnu packages python-build)
  #:use-module ((gnu packages python-xyz)
                #:hide (python-click-extra python-extra-platforms))
  #:use-module (meta-package-manager dependencies))

(define-public meta-package-manager
  (package
    (name "meta-package-manager")
    (version "8.3.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/kdeldycke/meta-package-manager")
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0slisbpv95xcnwzkcv2h2yp8vav4yiq5lha3ykcfhc16d75sdm1l"))))
    (build-system pyproject-build-system)
    ;; Upstream uses uv-build which is not yet available in Guix.
    (arguments
     (list #:build-backend "setuptools.build_meta"))
    ;; python-pytest-xdist: the 8.3.0 tests set its xdist_group marker, which
    ;; strict_markers rejects when no plugin registers it.  Drop it once the
    ;; definition builds a release whose tests/conftest.py declares the marker.
    ;; python-pyyaml: tests/test_cli_sbom.py and tests/test_docs.py import it.
    (native-inputs
     (list python-pytest
           python-pytest-xdist
           python-pyyaml
           python-setuptools))
    (propagated-inputs
     (list python-click-extra
           python-extra-platforms
           python-tomli-w))
    (home-page "https://mpm.run/")
    (synopsis "Package managers abstraction and unification tool")
    (description
     "Meta Package Manager (mpm) is a @acronym{Command Line Interface, CLI}
that wraps multiple GNU/Linux package managers behind a unified interface.
It can list, search, install, upgrade, and remove packages across all detected
managers simultaneously.  Output formats include tables, JSON, and CSV.")
    (license license:gpl2+)))
