;;; Meta Package Manager packaging for GNU Guix.
;;;
;;; meta-package-manager and its dependencies are part of GNU Guix upstream
;;; (gnu/packages/package-management.scm).  This standalone copy is updated
;;; automatically on each release and drives the version bumps forwarded
;;; upstream.  To install from it:
;;;
;;;   guix install --load-path=packaging/guix meta-package-manager

(define-module (meta-package-manager)
  #:use-module (guix build-system pyproject)
  #:use-module (guix git-download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module (gnu packages check)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-xyz)
  #:use-module (gnu packages xml))

(define-public meta-package-manager
  (package
    (name "meta-package-manager")
    (version "7.6.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/kdeldycke/meta-package-manager")
              (commit (string-append "v" version))))
       (file-name (git-file-name name version))
       (sha256
        (base32 "0c0yyqbhws7gq1ncjm9i793ckvrj5izlclap16afy8ick1nhgrqy"))))
    (build-system pyproject-build-system)
    ;; Upstream uses uv-build which is not yet available in Guix.
    (arguments
     (list #:build-backend "setuptools.build_meta"))
    ;; python-pyyaml and python-tomlkit: tests/test_docs.py loads
    ;; docs/docs_update.py, which imports them.
    (native-inputs
     (list python-pytest
           python-pyyaml
           python-setuptools
           python-tomlkit))
    (propagated-inputs
     (list python-boltons
           python-click-extra
           python-extra-platforms
           python-packageurl
           python-tomli-w
           python-xmltodict))
    (home-page "https://kdeldycke.github.io/meta-package-manager/")
    (synopsis "Package managers abstraction and unification tool")
    (description
     "Meta Package Manager (mpm) is a @acronym{Command Line Interface, CLI}
that wraps multiple GNU/Linux package managers behind a unified interface.
It can list, search, install, upgrade, and remove packages across all detected
managers simultaneously.  Output formats include tables, JSON, and CSV.")
    (license license:gpl2+)))
