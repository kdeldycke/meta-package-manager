# {octicon}`shield-lock` Security model

`mpm` runs other programs: that is its whole job. This page explains the trust model behind that, what is safe by default, and the guardrails around the most powerful configuration features.

## The configuration file is trusted input

The single most important thing to understand: **your `mpm` configuration file can make `mpm` run arbitrary commands.** Treat it like your shell startup file (`.bashrc`, `.zshrc`) or a `Makefile`: anyone who can write it can run code as you the next time you invoke `mpm`.

This is not new to any one feature. The per-manager override mechanism alone already allows it. A `[mpm.managers.<id>]` section can point a built-in manager at a different binary and prefix every call with `sudo`:

```toml
[mpm.managers.brew]
cli_search_path = ["/tmp/somewhere"]   # searched before $PATH
cli_names = ["not-really-brew"]        # the binary mpm executes
pre_cmds = ["sudo"]                     # prepended to every invocation
```

Defining a {ref}`brand-new manager <define-a-new-manager>` makes this capability explicit rather than more powerful: a definition spells out the commands to run, but choosing the binary (`cli_names` + `cli_search_path`) already permitted running anything. The ceiling is the same either way: configuration is code.

## What is safe by default

`mpm` only reads configuration from a location you control:

- By default it loads a single file from the per-user application directory (`~/.config/mpm/` on Linux, `~/Library/Application Support/mpm/` on macOS, the roaming app data folder on Windows).
- It does **not** scan the current working directory, and it does **not** auto-discover a `pyproject.toml` from a project you happen to be standing in. A `[tool.mpm]` block in a `pyproject.toml` is only read when you explicitly point `mpm` at it with `--config ./pyproject.toml`.

So cloning a hostile repository and running `mpm outdated` inside it does not load that repository's configuration.

## No shell, no injection

Every command `mpm` runs is executed as an argument list, never through a shell (`subprocess` is called without `shell=True` anywhere). Placeholders like `{package_id}` and `{query}` in a manager definition are substituted into individual argument elements, not interpolated into a command string. A package name containing shell metacharacters (`;`, `|`, `` ` ``) stays a single argument and is never interpreted by a shell.

The residual surface is ordinary *argument* injection (a package id that begins with `-` being read as a flag), which is inherent to wrapping any CLI and applies equally to the built-in managers.

## Guardrails on manager definitions

Because a {ref}`manager definition <define-a-new-manager>` is the most capable configuration feature, it carries guardrails the plain overrides do not:

1. **Trusted local files only.** `mpm` refuses to build a manager from a definition unless the config file (and its parent directory) is owned by you or root and is not group- or world-writable. This mirrors how `ssh`, `git`, and `sudo` reject unsafe-permission config. A world-writable directory is accepted only when it carries the sticky bit (like `/tmp`), which prevents others from replacing your file.
2. **No definitions from remote configs.** `mpm` supports `--config <url>`, but it will not synthesize a manager from a definition fetched over the network. Overrides of built-in managers still load from a URL for backward compatibility.
3. **A warning for risky overrides from untrusted sources.** When an override of `pre_cmds`, `cli_names`, `cli_search_path` (the fields that can redirect `mpm` to an arbitrary binary), or `sudo` (which runs a manager's binary as root) is read from a remote URL or an unsafe-permission file, `mpm` prints a warning. The override still applies, so existing setups keep working, but the heads-up is loud.

```{note}
The permission check is POSIX-only. On Windows the file-ownership model differs (ACLs rather than Unix mode bits), so the check is skipped. Keep your configuration directory restricted to your own account.
```

## Recommendations

- Keep your configuration file in the default per-user directory and make sure it is not group- or world-writable.
- Be deliberate about `--config`: pointing it at a file you did not write (a downloaded snippet, a repository's `pyproject.toml`) loads whatever that file says, including commands.
- Prefer [contributing a manager upstream](add-new-manager.md) over a private definition when the manager could be useful to others: an upstreamed manager is reviewed, tested, and shared, rather than living as executable configuration on one machine.

## See also

- {doc}`overrides` — the `[mpm.managers.<id>]` override and definition schema.
- {doc}`cooldown` — the release-age gate that mitigates a different threat: compromised upstream *package* releases.
- {doc}`configuration` — configuration-file discovery and precedence.
