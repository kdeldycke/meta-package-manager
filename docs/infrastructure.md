# {octicon}`globe` Infrastructure

Everything needed to rebuild the documentation site's hosting from nothing, and the reasoning behind each deviation from a stock GitHub Pages setup.

## What the site runs on

| Piece | Where | Notes |
| --- | --- | --- |
| Canonical host | `mpm.run` | Everything the site publishes lives here |
| Hosting | GitHub Pages, `gh-pages` branch | Custom domain set in the repository's Pages settings, not a `CNAME` file |
| Build | GitHub Actions, `.github/workflows/docs.yaml` | Sphinx `dirhtml`, then deploy, then link check |
| URL shape | `/managers/apk/`, no extension | Old `.html` paths answer from redirect stubs |
| DNS | Cloudflare | Apex and `www` are **DNS-only**; only the wildcard is proxied |
| Vanity redirects | Cloudflare Single Redirect, `http_request_dynamic_redirect` phase | `<manager>.mpm.run` to that manager's page |
| Certificates | GitHub for the apex and `www`, Cloudflare Universal SSL for the wildcard | Neither is managed by us |

There are no Workers, no KV namespaces and no Pages project involved. The whole edge configuration is a handful of DNS records and a single redirect rule.

## The apex is deliberately not proxied

This is the one deviation that looks like an oversight and is not.

GitHub Pages issues and renews its own Let's Encrypt certificate for a custom domain, validating over HTTP against that domain. Putting Cloudflare's proxy in front of the apex interferes with that validation, and the failure mode is the worst kind: nothing breaks at setup time, and the certificate silently fails to renew months later.

So the apex and `www` stay grey-cloud. The cost is real and accepted: no Cloudflare caching, no analytics and no WAF in front of the documentation. GitHub's own CDN serves it.

One thing is proxied, because an edge redirect cannot work otherwise, and it has no origin that could fail to renew anything: `*.mpm.run`, for the vanity redirects. It points at `100::`, the IPv6 discard prefix, which is the documented placeholder for a hostname that exists only to be intercepted at the edge.

## Vanity subdomains carry no manager list

`https://apt.mpm.run/` 301s to `https://mpm.run/managers/apt/`, and so does every other manager, without anything enumerating them.

The redirect rule splices the subdomain label straight into the path:

```
expression:  ends_with(http.host, ".mpm.run") and http.host ne "www.mpm.run"
target:      concat("https://mpm.run/managers/", substring(http.host, 0, -8), "/")
```

`substring(http.host, 0, -8)` trims the eight characters of `.mpm.run` off the end, leaving the label. `substring()` was chosen over `regex_replace()` because it is core to the Rules language and works on the Free plan.

Two consequences worth keeping:

- **A manager added to the pool gets its vanity host for free.** Nothing here can drift from `meta_package_manager.pool`, because nothing here knows what a manager is.
- **An unknown label lands on the site's 404**, not on an edge error. `wrong.mpm.run` redirects to `/managers/wrong/` and fails there, which is the friendlier of the two failures and costs nothing to allow.

The apex is not matched: `mpm.run` does not end in `.mpm.run`. `www` is excluded explicitly, though it is also DNS-only and so never reaches the rule at all: belt and braces, because the day someone proxies `www` is the day the exclusion starts mattering.

The trailing slash is the only thing this rule says about page layout, and it is edited by hand in the dashboard: it targeted `.html` paths until the site switched builders.

## Pages are directories

`[tool.repomatic] sphinx.builder` is `dirhtml`, so Sphinx writes every page as `<name>/index.html` and the site serves `/managers/apk/` where it used to serve `/managers/apk.html`. An extension-less URL survives a change of generator, which a suffix naming the output format does not.

The `.html` paths the site published for years still answer, from stubs `docs/conf.py` writes beside each page at the end of a `dirhtml` build: a zero-delay `<meta http-equiv="refresh">` plus the `<link rel="canonical">` naming the directory URL. That is as close to a `301` as this host allows, GitHub Pages serving files and the apex staying unproxied, so no edge rule can rewrite a path. A stub answering `200` is the one deliberate exception to the rule below, and its canonical link is what keeps it from becoming a second indexable copy of the page.

Two smaller consequences of the switch, both handled and both easy to reintroduce:

- **`manpages_url` is rooted, not relative.** The man pages under `/man/` are roff renderings, not Sphinx documents, so their link template lands in the page verbatim, with none of the per-page rewriting a document reference gets. Relative, it resolved against the page's own directory and 404ed. Their *index* broke the same way for a different reason, and was fixed upstream: click-extra `8.9.1` resolves the `click-extra-manpages` directive's links against the page's own URL rather than its docname, which is one directory shallower under this builder. That release is the floor `pyproject.toml` declares.
- **Absolute self-links move by hand.** The readme, the benchmark and the packaging specs name the canonical host from outside Sphinx's reach, so nothing rewrites them when the layout changes: `meta_package_manager._docs.manager_page_url` builds the manager ones, and the rest are literals.

## One host serves, and only one

Whatever else resolves to this site (a redirect, an old URL, a vanity subdomain) answers `301`, never `200`. Two hosts serving the same bytes is the failure this setup exists to avoid: it gives every page a second indexable origin and splits whatever authority the documentation accumulates between them. If anything other than `mpm.run` ever answers `200`, that is a fault.

## One declaration of the canonical URL

The origin is declared once, as `[project.urls] Documentation` in `pyproject.toml`, because three consumers need it and only one of them can read that file:

| Consumer | Reads it from | Why |
| --- | --- | --- |
| `docs/conf.py` | `pyproject.toml` directly | Sets `html_baseurl`, which drives canonical tags and the sitemap |
| `meta_package_manager._docs.DOCS_SITE_URL` | Repeats the literal | Runtime code cannot read `pyproject.toml`: it is not shipped in the wheel |
| `docs/robots.txt` | Repeats the literal | A static file with no templating |

`test_docs_site_url_matches_pyproject` fails when the first two drift apart.

## What crawlers get

`html_baseurl` makes every page emit a `<link rel="canonical">`, which is what tells a crawler that the vanity redirect and the former `kdeldycke.github.io` URL both land on the same page. `sphinx-sitemap` writes `sitemap.xml` from the same value, and `docs/robots.txt` (copied to the site root by `html_extra_path`, since `_static/` is not a location `robots.txt` can be served from) points at it.

`sitemap_url_scheme` is set to `{link}`. The extension's default assumes a site publishing several languages or versions side by side; anything but the bare link here produces sitemap entries that 404.

## Rebuilding from nothing

1. Register the domain and point its nameservers at Cloudflare.
2. Four `A` records at the apex for GitHub Pages, a `CNAME` for `www` to the `github.io` host, all DNS-only. Add a proxied `AAAA` wildcard at `100::`.
3. Set the custom domain in the repository's Pages settings and wait for the certificate to be issued. Setting it there rather than committing a `CNAME` file keeps a docs deploy from wiping it.
4. Enable HTTPS enforcement once the certificate is approved.
5. Add the vanity redirect rule.

A token for steps 2 to 5 needs `Zone → Read`, `DNS → Edit`, `Dynamic URL Redirects → Edit` and `Zone Settings → Edit`, scoped to **this zone only**. The account carries other zones whose mail records cannot be reconstructed if damaged, so an all-zones token is the wrong instrument for this job.

## Known gaps

- **No `AAAA` records on the apex.** GitHub publishes an IPv6 apex set; it was not verifiable from the machine that set this up, and a wrong `AAAA` black-holes v6 clients while an absent one costs nothing. Visitors still reach the proxied hostnames over IPv6 from Cloudflare's edge. Worth adding once verified.
- **The old `.html` URLs answer `200`, not `301`.** A static host cannot redirect, so they land on the stubs described above. Whatever authority a `301` would have passed along stays with the canonical link instead.
- **Downstream packaging specs lag.** The in-repo `packaging/*` specs point at the canonical host, but the copies already accepted by Nix, Guix, MacPorts and Alpine still carry the old URL until the next release bump re-submits them.

## Keeping this current

The Cloudflare dashboard is not the source of truth for *why*: this file is. When the two disagree about *what*, reconcile deliberately rather than editing this file to match whatever is live.
