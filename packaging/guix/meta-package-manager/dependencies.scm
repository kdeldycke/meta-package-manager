;;; Newer releases of the Guix channel packages that meta-package-manager needs.
;;;
;;; The Guix channel lags behind the dependency floors of meta-package-manager.
;;; python-click-extra and python-extra-platforms are its own dependencies, and
;;; the four others are what this python-click-extra requires.
;;;
;;; Each package inherits its channel definition, with a new version and a new
;;; source.  A propagated input that this module also defines points to the
;;; definition here.  The native inputs hold only the build tools, because the
;;; test suites stay off: the channel runs them when it ships these releases,
;;; and this build is there to test mpm.
;;;
;;; update.py bumps only meta-package-manager.scm.  When a release raises a
;;; floor above a package of this module, the sanity-check phase fails: bump
;;; the package here by hand.  A third-party release must first clear the
;;; exclude-newer window of pyproject.toml.  The NAR helpers of update.py
;;; compute a git-fetch hash without Guix.  Delete a package once the channel
;;; ships its release or a newer one.  For the two public packages, also drop
;;; their names from the #:hide clause of meta-package-manager.scm.

(define-module (meta-package-manager dependencies)
  #:use-module (guix build-system pyproject)
  #:use-module (guix download)
  #:use-module (guix git-download)
  #:use-module (guix packages)
  #:use-module (guix utils)
  #:use-module (gnu packages python-build)
  #:use-module ((gnu packages python-xyz) #:prefix channel:))

(define (arguments-without-tests p)
  "Return the build arguments of package P with its test suite turned off."
  (substitute-keyword-arguments (package-arguments p)
    ((#:tests? _ #t) #f)))

(define python-click
  (package/inherit channel:python-click
    (version "8.5.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/pallets/click")
              (commit version)))
       (file-name (git-file-name "python-click" version))
       (sha256
        (base32 "0pbzy8nnfjw7vzgwccw3fzjldshc13gz524drxaw9n35vw85m1sm"))))
    (arguments (arguments-without-tests channel:python-click))
    (native-inputs (list python-flit-core))))

(define-public python-extra-platforms
  (package/inherit channel:python-extra-platforms
    (version "14.0.1")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/kdeldycke/extra-platforms")
              (commit (string-append "v" version))))
       (file-name (git-file-name "python-extra-platforms" version))
       (sha256
        (base32 "0zw677ij3d0p9xdbzy0i1arv3d2rzyzqba27xpjda491v5kcbhk3"))))
    (arguments (arguments-without-tests channel:python-extra-platforms))
    (native-inputs (list python-setuptools))))

(define python-wcwidth
  (package/inherit channel:python-wcwidth
    (version "0.9.4")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "wcwidth" version))
       (sha256
        (base32 "0m2rhglijjih1jf7bh4913s4xqr4bj4b3yn8clr0wmzyrp9mg3gx"))))
    (arguments (arguments-without-tests channel:python-wcwidth))
    (native-inputs (list python-setuptools))))

(define python-cloup
  (package/inherit channel:python-cloup
    (version "4.0.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "cloup" version))
       (sha256
        (base32 "0f5hr9vd5xyss3hrqbhls96bxpngich1n3p4558wig33x078gc43"))))
    (arguments (arguments-without-tests channel:python-cloup))
    ;; cloup 4 builds with hatchling instead of setuptools.
    (native-inputs (list python-hatch-vcs python-hatchling))
    (propagated-inputs (list python-click))))

(define python-tabulate
  (package/inherit channel:python-tabulate
    (version "0.10.0")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "tabulate" version))
       (sha256
        (base32 "03d691p14av6mhbmsra7x6y5mg5nqfp9mnnyzzp6s3s2g67xxkz2"))))
    (arguments (arguments-without-tests channel:python-tabulate))
    (native-inputs (list python-setuptools python-setuptools-scm))
    (propagated-inputs (list python-wcwidth))))

(define-public python-click-extra
  (package/inherit channel:python-click-extra
    (version "10.2.0")
    (source
     (origin
       (method git-fetch)
       (uri (git-reference
              (url "https://github.com/kdeldycke/click-extra")
              (commit (string-append "v" version))))
       (file-name (git-file-name "python-click-extra" version))
       (sha256
        (base32 "1zmlssnh8hrg3p3mgcza66zfq8xi9napaq3d9n6sk2vyvisdynvq"))))
    (arguments (arguments-without-tests channel:python-click-extra))
    (native-inputs (list python-setuptools))
    ;; click-extra 10 no longer needs python-boltons and python-deepmerge.
    (propagated-inputs
     (list python-click
           python-cloup
           python-extra-platforms
           python-tabulate
           channel:python-wcmatch
           python-wcwidth))))
