# {octicon}`passkey-fill` Privilege escalation and `sudo`

Most Linux package managers need `sudo` to perform system-wide operations, and on other OSes you may be prompted for your password to install privileged payloads (a macOS cask shipping a kernel extension or a `.pkg` installer, for example):

```shell-session
$ brew install --cask macfuse
==> Caveats
macfuse requires a kernel extension to work.
If the installation fails, retry after you enable it in:
  System Preferences → Security & Privacy → General

For more information, refer to vendor documentation or this Apple Technical Note:
  https://developer.apple.com/library/content/technotes/tn2459/_index.html

==> Downloading https://github.com/osxfuse/osxfuse/releases/download/macfuse-4.2.5/macfuse-4.2.5.dmg
Already downloaded: /Users/kde/Library/Caches/Homebrew/downloads/d7961d772f16bad95962f1a780b545a5dbb4788ec6e1ec757994bb5296397b1c--macfuse-4.2.5.dmg
==> Installing Cask macfuse
==> Running installer for macfuse; your password may be necessary.
Package installers may write to any location; options such as `--appdir` are ignored.
Password:
```

## Escalation policy

Which managers escalate is decided per manager. System package managers (`apt`, `dnf`, `pacman`, `zypper`, `xbps`, and the like) run their state-changing operations through `sudo` by default; user-level managers (`brew`, `npm`, `pip`, ...) do not.

## Controlling escalation

Override the default globally with `--sudo` / `--no-sudo`, or per manager with the `sudo` key of a [`[mpm.managers.<id>]`](overrides.md) section:

```toml
[mpm.managers.npm]
sudo = true # Run global npm installs through sudo.

[mpm.managers.pacman]
sudo = false # Rootless setup: never escalate pacman.
```

A per-manager `sudo` value wins over the global flag, so you can escalate everything with `--sudo` while keeping a single manager rootless, or the reverse.

## One prompt, up front

`mpm` runs managers concurrently with their output muted behind a progress spinner, so a `sudo` password prompt raised mid-run is easy to miss and can stall the whole command. Before a state-changing command (`install`, `upgrade`, `remove`, `sync`, `cleanup`, `restore`) that will escalate, `mpm` therefore authenticates `sudo` once, up front, on your terminal, then keeps the credential warm for the rest of the run. Every escalated call after that spends the cached credential silently, so nothing blocks in the fan-out.

That single prompt also covers a manager that escalates internally: on macOS, `brew`'s own `sudo` (for a cask like the `macfuse` example above) reuses the warmed credential when you pass `--sudo`.

Off a terminal (a pipe, CI, the menubar plugin), `mpm` cannot prompt, so managers needing root fail fast with a clear error instead of hanging.

A stock `mpm upgrade` on macOS does not pre-authenticate for casks (matching `brew`'s own lazy behavior), so a cask needing admin rights still prompts mid-run; run `mpm --sudo upgrade` for the clean one-prompt experience.

## Running `mpm` itself as root

On Linux you may instead install and run `mpm` under `sudo`, so every manager it drives is already privileged:

```shell-session
$ sudo uv tool install meta-package-manager
(...)
$ sudo mpm upgrade
(...)
```

## Security

Escalating a manager runs its binary, and every install script of the packages it touches, as root. `mpm` only escalates the managers that require it or that you have opted in, and it warns when a `sudo` override is read from an untrusted config source. See [the security model](security.md) for the trust rules behind this.
