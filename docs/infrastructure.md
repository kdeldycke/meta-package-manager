# {octicon}`globe` Infrastructure

Everything needed to rebuild the documentation site's hosting from nothing, and the reasoning behind each deviation from a stock setup. No account, zone or project identifier is recorded here: this repository is public, and every one of them is resolved at runtime from the credential instead. Find them with `wrangler whoami` or in any dashboard URL.

## What the site runs on

| Piece | Where | Notes |
| --- | --- | --- |
| Canonical host | `mpm.run` | Everything the site publishes lives here |
| Hosting | Cloudflare Pages project `meta-package-manager` | Direct Upload, no Git connection |
| Build | GitHub Actions, `.github/workflows/docs.yaml` | Sphinx `dirhtml`, then `wrangler pages deploy` |
| Deploy target | `[tool.repomatic] site.deploy` | `cloudflare-pages`, selecting the job that publishes |
| DNS | Cloudflare | Apex and the wildcard are **proxied**; nothing is DNS-only |
| Redirects | `docs/_redirects` for paths, zone rules for hosts | Pages matches on path only, never on host |
| URL shape | `/managers/apk/`, no extension | `sphinx.builder` is `dirhtml` |
| Certificates | Cloudflare, for everything | Issued and renewed internally, no ACME, no token |

There are no Workers, no KV namespaces and no D1 databases. The whole edge configuration is two DNS records and two redirect rules.

## Cloudflare never builds this site

GitHub Actions renders it and uploads the finished tree, which is what a Direct Upload flow means: Cloudflare has no access to this repository and no build configuration capable of producing a usable site. The `deploy-docs-cloudflare` job of repomatic's shared `docs.yaml` runs `sphinx-build`, then `wrangler pages deploy ./docs/_build`.

Two repository secrets feed it. `CLOUDFLARE_API_TOKEN` needs exactly one permission, `Account → Cloudflare Pages → Edit`, and `CLOUDFLARE_ACCOUNT_ID` is not a credential at all: a stable identifier visible in every dashboard URL, which never expires and never needs rotating.

The token does need rotating, and nothing warns when it lapses: Cloudflare sends no expiry notice for account API tokens. Give it a TTL, and remember that a docs deploy only runs when the docs change, so an expired token surfaces whenever the next documentation push happens to land.

### Why this moved off GitHub Pages

GitHub Pages validates its Let's Encrypt renewal over HTTP against the domain, so putting Cloudflare's proxy in front of the apex broke that renewal months later, silently. The apex therefore had to stay DNS-only, and an unproxied apex is one no edge rule can touch: no redirects, no caching, no analytics, on the one hostname that matters.

Cloudflare Pages issues the certificate for its own custom domains, so that constraint is gone. The apex is proxied now, and the redirects below exist because of it.

GitHub Pages is still enabled on the repository, and should stay that way: with `mpm.run` still configured there as the custom domain, `kdeldycke.github.io/meta-package-manager/…` answers `301` to `https://mpm.run/…` with the path preserved. That is a decade of old links kept alive by a site nothing deploys to any more. Deleting the Pages site would turn every one of them into a `404`.

## What the edge serves, exactly

Measured against a preview deployment before the cutover, because the behaviour is not what the documentation suggests:

| Request | Answer | Why |
| --- | --- | --- |
| `/managers/apk/` | `200` | The page |
| `/managers/apk` | `308` → `/managers/apk/` | Pages normalizes a directory to its trailing slash |
| `/managers/apk.html` | `301` → `/managers/apk/` | `docs/_redirects`, not Pages |
| `/index.html` | `308` → `/` | Pages normalization again |
| `/nope` | `404` | `docs/404.html` |

Three findings sit behind that table, and each cost a preview deployment to learn:

- **Pages strips `.html` only when an asset sits at the stripped path.** `/contact.html` normalizes to `/contact` because `contact.html` is a file. Against a *directory* it finds nothing, so every pre-`dirhtml` URL fell straight through. `docs/_redirects` is what answers them, and it has to.
- **Without `404.html`, an unmatched path returns the home page under a `200`.** Not a 404, not an error: a soft-404 across the entire URL space, telling crawlers every misspelling is a real page. `docs/404.html` is deliberately self-contained, with no stylesheet and no script, because it is reached from arbitrary depth and a relative asset path would break on half of them.
- **An extension-less URL resolves to a sibling `.html` file before the directory.** The redirect stubs that made GitHub Pages work therefore *shadowed* the pages they pointed at: `/managers/apk` served a 354-byte "Page moved" placeholder. They were deleted with the move, and must not come back.

## Hosts are canonicalized at the edge

Every hostname but `mpm.run` answers `301`, never `200`. Two rules in the zone's `http_request_dynamic_redirect` phase do it, and neither could live in `_redirects`: Pages redirects match on path, never on host.

```
description: 301 <manager>.mpm.run to that manager's documentation page
expression:  ends_with(http.host, ".mpm.run") and http.host ne "www.mpm.run"
target:      concat("https://mpm.run/managers/", substring(http.host, 0, -8), "/")
             301, preserve_query_string

description: 301 www.mpm.run to the canonical host
expression:  (http.host eq "www.mpm.run")
target:      concat("https://mpm.run", http.request.uri.path)
             301, preserve_query_string
```

`substring(http.host, 0, -8)` trims the eight characters of `.mpm.run`, leaving the label. It was chosen over `regex_replace()` because it is core to the Rules language and works on the Free plan. The trailing `/` is the only thing that rule says about page layout, and it is edited by hand: it targeted `.html` paths until the site switched builders.

Both targets take the path from the expression and leave the query string to `preserve_query_string`. `http.request.uri` already carries the query, so concatenating *it* while the flag is set appends the query twice.

Three consequences worth keeping:

- **A manager added to the pool gets its vanity host for free.** Nothing here can drift from `meta_package_manager.pool`, because nothing here knows what a manager is.
- **An unknown label lands on the site's own 404**, not on an edge error. `wrong.mpm.run` redirects to `/managers/wrong/` and fails there, which is the friendlier of the two failures.
- **`www` names itself.** It is excluded from the wildcard rule and handled by its own, because its redirect used to come from GitHub Pages: the hostname `CNAME`d to `kdeldycke.github.io`, and GitHub answered the `301` on the strength of the custom domain configured there. That is a redirect this project did not control, and it would have died with the Pages site.

## DNS

Two records, and each earns its place:

| Type | Name | Content | Proxied |
| --- | --- | --- | --- |
| CNAME | `mpm.run` | `meta-package-manager.pages.dev` | yes |
| AAAA | `*.mpm.run` | `100::` | yes |

`www.mpm.run` has no record of its own: the wildcard covers it, and the rule above redirects it. `100::` is the IPv6 discard prefix, the documented placeholder for a hostname that exists only to be intercepted at the edge — a proxied hostname needs at least one record for Cloudflare to answer for it at all, and the wildcard's traffic never reaches an origin.

## The published tree carries only what it serves

Three things Sphinx writes into its output directory are not content, and none of them ship:

- **`.doctrees/`**, the pickled parse cache, was 118 MB of a 182 MB artifact. Repomatic's `docs.yaml` passes `-d` to send it to the runner's temp directory instead.
- **`_sources/`**, a copy of every document, is off via `html_copy_source`: no page this theme renders carries a source link, and the sources are the repository.
- **`.buildinfo`**, the incremental-build marker, has no setting to suppress it, so `docs/conf.py` deletes it once the build is over.

That matters more here than it did on GitHub Pages, which simply refused to serve dot-prefixed paths: Pages Direct Upload rejects any file over 25 MiB, and the parse cache held a 20 MB pickle.

## One declaration of the canonical URL

The origin is declared once, as `[project.urls] Documentation` in `pyproject.toml`, because three consumers need it and only one of them can read that file:

| Consumer | Reads it from | Why |
| --- | --- | --- |
| `docs/conf.py` | `pyproject.toml` directly | Sets `html_baseurl`, which drives canonical tags and the sitemap |
| `meta_package_manager._docs.DOCS_SITE_URL` | Repeats the literal | Runtime code cannot read `pyproject.toml`: it is not shipped in the wheel |
| `docs/robots.txt` | Repeats the literal | A static file with no templating |

`test_docs_site_url_matches_pyproject` fails when the first two drift apart.

## What crawlers get

`html_baseurl` makes every page emit a `<link rel="canonical">`, and `sphinx-sitemap` writes `sitemap.xml` from the same value. `sitemap_url_scheme` is `{link}`: the extension's default assumes a site publishing several languages or versions side by side, and anything but the bare link here produces entries that 404.

Both matter more than usual now, because `meta-package-manager.pages.dev` serves the same bytes and cannot be deleted — Cloudflare assigns one `<project>.pages.dev` per project and keeps it for the project's life. The duplicate is inert rather than absent: every page names `mpm.run` as its canonical, the sitemap lists canonical URLs only, and the readme's own links are absolute.

## Rebuilding from nothing

1. Register the domain and point its nameservers at Cloudflare.
2. Create a Pages project named after the repository. Choose **Direct Upload**, never a Git connection.
3. Create the API token, and set `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as repository secrets. The project is named after the repository, which is what `site.cloudflare-project` overrides when it is not.
4. Attach `mpm.run` to the project as a custom domain, then add the proxied apex `CNAME` and the proxied `*` `AAAA` at `100::`.
5. Add the two redirect rules.
6. Push, or run the Docs workflow by hand, to produce the first deployment.

A token for steps 4 and 5 needs `Zone → Read`, `DNS → Edit` and `Dynamic URL Redirects → Edit`, scoped to **this zone only**. The account carries other zones whose mail records cannot be reconstructed if damaged, so an all-zones token is the wrong instrument.

## Working with the API

Two things cost an afternoon each and are not written down anywhere obvious:

- **An account-owned token (the `cfat_` prefix) is rejected by `/user/tokens/verify`.** That endpoint is user-scoped, and answers `HTTP 401`, error `1000`, "Invalid API Token" — for a token that works perfectly on every zone and account call. Never gate a script on a verify step; prove the credential against the resource it is meant to touch.
- **Cloudflare answers `403` to urllib's default user agent.** Anything probing the live site from Python has to set one, or every check fails in a way that looks like the site is down.

Single Redirects live in the `rulesets` API, which accepts account-owned tokens: `GET /zones/{zone}/rulesets` finds the `http_request_dynamic_redirect` phase, and `PATCH …/rules/{rule}` edits one in place. The legacy `pagerules` endpoint is a different thing.

## Known gaps

- **Nothing reconciles the edge configuration.** The rules and records above are recorded here by hand; no script diffs them against the live zone, so this file can drift from reality without anything noticing.
- **The wildcard covers hostnames nobody registered.** `*.mpm.run` answers for every label, so a typo becomes a redirect into the site's 404 rather than a DNS failure. That is the friendlier failure, and it is deliberate, but it does mean the zone answers for names the project never chose.
- **No `AAAA` on the apex beyond the proxy.** Not needed while Cloudflare terminates everything, and noted only so a future reader does not go looking for one.

## Keeping this current

The Cloudflare dashboard is not the source of truth for *why*: this file is. When the two disagree about *what*, reconcile deliberately rather than editing this file to match whatever is live.

Record what was checked and how, not just the conclusion, so a later reader can tell a verified fact from a plausible assumption. Every measurement in the tables above was taken against a real deployment, which is the only reason they contradict the vendor documentation in three places.
