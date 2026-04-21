;;; Meta Package Manager packaging for GNU Guix.
;;;
;;; This definition is maintained in the mpm repository and updated automatically
;;; on each release.  To use it locally:
;;;
;;;   guix install --load-path=packaging/guix python-meta-package-manager
;;;
;;; To submit upstream, copy the define-public form into the appropriate module
;;; in the Guix repository (gnu/packages/python-xyz.scm).

(define-module (meta-package-manager)
  #:use-module (guix build-system pyproject)
  #:use-module (guix download)
  #:use-module ((guix licenses) #:prefix license:)
  #:use-module (guix packages)
  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-xyz))

(define-public python-meta-package-manager
  (package
    (name "python-meta-package-manager")
    (version "6.3.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "meta_package_manager" version))
       (sha256
        (base32 "1xhxk270phj498l9xzv25byl92hfq7wc1v6vz571b66pyc7kpzh4"))))
    (build-system pyproject-build-system)
    ;; Some propagated inputs may not yet exist in Guix and will need packaging
    ;; before this definition can be submitted upstream.
    (propagated-inputs
     (list python-boltons
           python-click-extra
           python-cyclonedx-python-lib
           python-extra-platforms
           python-more-itertools
           python-packageurl-python
           python-spdx-tools
           python-tomli-w
           python-xmltodict))
    (native-inputs
     (list python-uv-build))
    (home-page "https://github.com/kdeldycke/meta-package-manager")
    (synopsis "CLI that wraps all package managers with a unifying interface")
    (description
     "Meta Package Manager (mpm) is a CLI that wraps multiple package managers
behind a unified interface.  It can list, search, install, upgrade, and remove
packages across all detected managers simultaneously.  Output formats include
tables, JSON, and CSV.")
    (license license:gpl2+)))
