/* GNOME Shell's own coding-style rules, from the eslint-config-gnome package
 * gnome-shell pins as a git dependency (there is no npmjs release). The
 * `eslint` job of ../.github/workflows/tests-gnome-extension.yaml installs it
 * at the same commit and points ESLint at this file.
 *
 * No package.json or lockfile accompanies it, deliberately: nobody would keep
 * a 100-package lockfile refreshed, and a pin that rots is worse than none.
 * The job floats the ESLint stack behind a release-age cooldown instead. The
 * `.mjs` extension is what makes this file ESM without a package.json. */

import gnome from 'eslint-config-gnome';

/* `recommended` is an unscoped pair of config objects, so each gets the same
 * scope. Its paths are relative to the repository root, not to this file:
 * ESLint is invoked from there, which is what lets one config cover both the
 * extension and its gjs test runner. Everything else, including the
 * documentation's browser-side assets, is left unmatched and unruled. */
export default gnome.configs.recommended.map(config => ({
    ...config,
    files: ['gnome-shell/**/*.js', 'tests/gnome/**/*.js'],
}));
