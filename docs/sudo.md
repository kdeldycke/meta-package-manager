# {octicon}`key` Privilege escalation and `sudo`

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

Which managers escalate is decided per manager. System package managers (`apt`, `dnf`, `pacman`, `zypper`, `xbps`, `macports`, `snap`, and the like) run their state-changing operations through `sudo` by default; user-level managers (`brew`, `npm`, `pip`, ...) do not, and daemon-backed managers authorizing through polkit (`flatpak`, `fwupd`, `pkcon`) need no wrap at all.

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

`mpm` runs managers concurrently with their output muted behind a progress spinner, so a `sudo` password prompt raised mid-run is easy to miss and can stall the whole command. Before a state-changing command (`install`, `upgrade`, `remove`, `sync`, `cleanup`, `restore`) that involves escalation, `mpm` therefore probes the credential cache without prompting. A cache found warm (a prior `sudo --validate`, a `NOPASSWD` rule, a recent privileged command) is silently kept fresh for the rest of the run, and every escalated call spends it: no prompt at all.

Only a cold cache, on an interactive terminal, leads to a prompt: a notice names the managers about to escalate and the subcommand, then a single branded `sudo` prompt authenticates once for the whole run, so nothing blocks in the fan-out:

```shell-session
$ mpm upgrade
apt, deb-get need administrator rights to upgrade: enter your password.
[mpm] password for apt, deb-get:
```

Off a terminal (a pipe, CI, the menubar plugin), `mpm` cannot prompt: a warning names the managers needing root, and they fail fast with a clear error instead of hanging. To escalate unattended, configure a `NOPASSWD` rule for the managers' commands: the probe then finds the cache warm and keeps it alive. A prior `sudo --validate` also works, but only from the same terminal session `mpm` runs in: under sudo's default terminal-keyed timestamps, credentials cached in one terminal do not carry to a `mpm` launched without one (a menubar plugin, a CI step), so `NOPASSWD` is the robust choice there.

## Managers escalating internally

Some managers run `sudo` from inside their own commands: on macOS, `brew` escalates while installing a cask with a privileged payload (the `macfuse` example above) and `fink` re-execs its root commands through `sudo`, while on Linux the AUR helpers call `sudo pacman` for their privileged phases, `pacstall` re-execs itself through `sudo pacstall`, and `topgrade` drives each privileged step through its own per-step `sudo`. `mpm` never wraps these managers in `sudo` (`brew` even refuses to run as root, and `topgrade` warns and prompts when launched as root), and most of their runs never escalate, so a stock `mpm upgrade` does not pre-authenticate for them: prompting on every run would be worse than the rare mid-run prompt it avoids.

Two mechanisms cover that rare prompt instead. When the up-front probe finds the credential cache already warm, the keepalive is armed for internal escalators too, so their mid-run `sudo` spends the cache silently. And on a cold cache, a mutating call of such a manager that stays silent for 30 seconds on a terminal draws a warning, while there is still time to answer the prompt:

```shell-session
$ mpm install macfuse
(...)
warning:cask: No output for 30s: may be waiting on a hidden password prompt. Last output: "==> Running installer for macfuse; your password may be necessary."
```

For a guaranteed one-prompt experience, opt the manager into up-front authentication with a scoped `sudo = true` override:

```toml
[mpm.managers.cask]
sudo = true # Authenticate up front before any privileged cask payload.
```

or scope the global flag to the manager: `mpm --cask --sudo upgrade`. Prefer these to a bare `mpm --sudo upgrade`, which is broader than it looks: the global flag covers every selected manager, and also activates dormant privileged markers like those of `pip`, `npm`, `gem` and `cpan`, wrapping their system-scope installs in `sudo`.

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
