---
name: file-bug-report
description: Write a bug report for an upstream project. Exhaustively reads contribution guidelines, issue templates, and community norms before producing a markdown file ready to paste.
model: opus
allowed-tools: Bash, Read, Grep, Glob, Write, WebFetch, WebSearch, Agent
argument-hint: <owner/repo> <one-line summary of the bug>
---

# Write an upstream bug report

Create a well-structured bug report for filing against an external project. The report is written to a local markdown file so the user can review before pasting into a GitHub issue.

`$ARGUMENTS` contains the target repo (`owner/repo`) and a short summary of the bug.

## Workflow

### 1. Discover upstream contribution norms

Before writing anything, exhaustively search for every piece of guidance the maintainers publish about how they want contributions. Do not skip any of these checks: each one can reveal requirements that, if missed, make the report look careless.

#### 1a. Contribution guidelines

GitHub recognizes contribution guidelines in the repo root, `.github/`, and `docs/`, but owners do not always follow GitHub's conventions. File names vary in casing, extension, and placement. Do not assume any single path: check all plausible variations.

**Step 1: use the GitHub community endpoint** (returns the canonical contributing file regardless of location or casing):

```
gh api repos/<owner/repo>/community/profile --jq '.files.contributing'
```

If this returns a file, fetch its `html_url` or `url` and read it.

**Step 2: list the directories** where contribution guidelines commonly live. For each directory, list its contents and scan for any file whose name matches `contributing` (case-insensitive) with any extension:

```
gh api repos/<owner/repo>/contents/ --jq '.[].name'
gh api repos/<owner/repo>/contents/.github --jq '.[].name'
gh api repos/<owner/repo>/contents/docs --jq '.[].name'
gh api repos/<owner/repo>/contents/doc --jq '.[].name'
```

Look for files matching these patterns (case-insensitive): `contributing.md`, `CONTRIBUTING.md`, `Contributing.md`, `CONTRIBUTING.markdown`, `CONTRIBUTING.rst`, `CONTRIBUTING.txt`, `CONTRIBUTING`, `contributing.adoc`, `CONTRIBUTING.adoc`, or any other variation. Owners may use `.rst`, `.txt`, `.adoc`, `.markdown`, no extension, or non-standard casing. Fetch and read every match.

**Step 3: check the readme** for inline contribution guidance or links to external docs:

```
gh api repos/<owner/repo>/readme --jq '.download_url'
```

Fetch the readme and scan for headings like "Contributing", "How to contribute", "Bug reports", "Filing issues", "Reporting bugs", "Development", or links to external contribution guides (wikis, documentation sites, readthedocs pages). If a link points to an external URL, fetch and read it.

**Step 4: check the wiki.** Some projects put contribution guidelines in their GitHub wiki:

```
gh api repos/<owner/repo> --jq '.has_wiki'
```

If the wiki is enabled, note this for the user: the wiki may contain additional contribution norms that cannot be fetched via the API. Suggest the user check `https://github.com/<owner/repo>/wiki` for pages like "Contributing", "How to file a bug", etc.

#### 1b. Code of conduct

Check for a code of conduct (it sometimes contains issue-filing etiquette):

```
gh api repos/<owner/repo>/contents/CODE_OF_CONDUCT.md --jq '.download_url'
gh api repos/<owner/repo>/contents/.github/CODE_OF_CONDUCT.md --jq '.download_url'
gh api repos/<owner/repo>/community/code_of_conduct --jq '.body'
```

#### 1c. Issue templates and forms

List all issue templates. Repos may use classic markdown templates, YAML issue forms, or both:

```
gh api repos/<owner/repo>/contents/.github/ISSUE_TEMPLATE --jq '.[].name'
```

Fetch **every** template and form found. Identify which one is the correct match for a bug report by examining filenames and content. Common patterns:

- `bug_report.md` / `bug_report.yml` / `bug-report.yml`: bug reports.
- `feature_request.md` / `feature_request.yml`: feature requests (skip).
- `security.md` / `SECURITY.md`: security disclosures (use only if the bug is a security issue).
- `config.yml`: template chooser config that may redirect users to discussions or external links.

**If the repo uses YAML issue forms** (`.yml` files with `type: input`, `type: textarea`, etc.), the report must fill in each required field using the exact field labels as section headers, preserving the order from the form. Optional fields should be included if relevant evidence exists.

**If the repo uses markdown templates** (`.md` files with HTML comments like `<!-- description -->`), follow the template structure and replace placeholders.

**If no templates exist**, use the default structure from step 5.

Also check the template chooser config for redirection:

```
gh api repos/<owner/repo>/contents/.github/ISSUE_TEMPLATE/config.yml --jq '.content' | base64 -d
```

This file may disable blank issues (`blank_issues_enabled: false`) or add links that redirect users to discussions, forums, or other channels. Respect these preferences.

#### 1d. Security policy

If the bug has security implications, check for a security policy first:

```
gh api repos/<owner/repo>/contents/SECURITY.md --jq '.download_url'
gh api repos/<owner/repo>/contents/.github/SECURITY.md --jq '.download_url'
```

If a security policy exists and the bug is a vulnerability, warn the user that it should be reported through the security channel (often a private advisory or email), not a public issue. Stop and report this to the user.

#### 1e. Discussions preference

Some maintainers require opening a discussion before filing an issue. Check for signals:

```
gh api repos/<owner/repo> --jq '.has_discussions'
```

If discussions are enabled, search for patterns in the contribution guidelines that say things like "open a discussion first", "please ask in discussions before filing", "use discussions for questions and bug reports". Also check if the template chooser config redirects to discussions.

If the maintainers prefer discussions first, warn the user and suggest opening a discussion instead. Write the report in a tone appropriate for a discussion (same factual content, but framed as "I encountered this, is this a known issue?" rather than a direct bug report).

#### 1f. PR and issue cross-reference conventions

While reading contribution guidelines, note any rules about:

- Whether PRs require a linked issue first ("please open an issue before submitting a PR").
- Whether issues should include attempted fixes or just describe the problem.
- Label conventions the maintainer wants reporters to use.
- Required information the maintainer explicitly asks for (specific version commands to run, config files to include, etc.).

### 2. Search for existing issues

Check whether the bug is already reported:

```
gh search issues --repo <owner/repo> "<keywords>" --json title,url,state
gh issue list --repo <owner/repo> --state all --json title,url,state
```

Search with multiple keyword variations (error messages, function names, symptoms). Check both open and closed issues: the bug may have been reported and closed as "won't fix", or fixed in a version the user hasn't upgraded to.

If a matching open issue exists, report it to the user and stop. If a matching closed issue exists, mention it in the report with a link and explain why this is a new occurrence (different version, different context, regression).

### 3. Gather evidence

Collect the actual error output, environment details, and reproduction steps from the current conversation context, CI logs, or local files. Always include:

- Exact error messages and tracebacks (not paraphrased).
- Version numbers of the failing tool. Run any version commands the contribution guidelines specify.
- OS and architecture.
- CI run URL if applicable.
- Any additional environment details the issue template or contribution guidelines explicitly request.

#### Link to public context

Maintainers can diagnose faster when they can see the original context themselves. Whenever the triggering context is publicly accessible, include deep links in the report:

- **CI run logs**: link to the specific GitHub Actions run (or step anchor) that shows the failure, not just the repo. Use `gh run view <run-id> --json url --jq '.url'` to get the URL.
- **Source code**: link to the exact file and line(s) in the user's public repo that trigger the bug, using GitHub's permalink format (`https://github.com/<owner/repo>/blob/<sha>/path/to/file.py#L42-L55`). Use a commit SHA, not a branch name, so the link stays stable.
- **Configuration files**: if the bug depends on a specific config (workflow YAML, `pyproject.toml` section, tool config), link to it.
- **PR or commit**: if the bug surfaced after a specific change, link to the PR or commit.

Ask yourself: "Can the maintainer click a link and immediately see what I'm describing?" If yes, include the link. If the context is private, quote the relevant snippet inline instead.

### 4. Select the right template

Based on step 1c, pick the correct template:

- **Bug report template/form found**: use it. Fill in every required field. Preserve the exact field names, order, and structure.
- **Multiple templates exist but none is a clear bug report match**: report this to the user and ask which template to use.
- **No templates found**: use the default structure in step 5.
- **Template chooser disables blank issues and no bug template exists**: warn the user that the repo may not accept bug reports through issues.

### 5. Write the report

Write a markdown file to `<current-project>/<repo>-bug-report.md`.

**If using a template from step 4**, replicate its structure exactly: same headings, same field order, same placeholder comments replaced with actual content. For YAML issue forms, use each field label as a markdown heading and fill in the content.

**If no template exists**, use this default structure:

```markdown
# <Clear, specific title>

## Summary

One paragraph describing what fails and the impact.

## Steps to reproduce

Minimal, self-contained reproduction. Prefer a GitHub Actions workflow snippet if the bug is CI-specific.

## Expected behavior

What should happen.

## Actual behavior

What happens instead, with exact error output in code blocks.

## Environment

- Tool version
- OS / architecture
- Any relevant context (CI runner, Docker image, etc.)
```

### Writing guidelines

- Lead with facts. No preamble, no apologies, no "I love your project."
- Use first-person singular ("I", "my") per user conventions.
- Include exact error messages in code blocks, not paraphrases.
- If multiple distinct failures exist, group them under numbered sub-sections but keep them in one report if they share a root cause. File separate issues if root causes differ.
- Keep reproduction steps minimal: strip everything not needed to trigger the bug.
- Link to CI runs or logs when available.
- Do not speculate about fixes unless the root cause is clear from the evidence.
- Do not use em dashes; use colons for inline elaboration.
- Respect any tone, formatting, or content requirements found in the contribution guidelines. If the guidelines say "include output of `tool --version`", include it. If they say "use the template", use it verbatim.
- If the contribution guidelines mention a specific communication style or contain a content guide, follow it.

### Sanitizing output

Before including any error output, tracebacks, or logs in the report, scrub them for readability and privacy:

- **Strip local paths**: replace long absolute paths (`/Users/kde/code/project/venv/lib/python3.12/site-packages/...`) with short relative equivalents (`site-packages/...` or `.venv/.../`). The maintainer does not need the user's home directory or filesystem layout.
- **Remove private information**: usernames, home directory names, hostnames, IP addresses, API keys, tokens, internal domain names, email addresses. Scan the entire output before pasting.
- **Trim repetitive frames**: if a traceback has dozens of recursive or repetitive stack frames, keep the top few, the bottom few, and replace the middle with `... (N frames omitted) ...`. The diagnostic value is in the entry point and the crash site, not 40 identical recursion frames.
- **Collapse verbose logs**: if CI output is hundreds of lines, extract only the relevant section. Use `<details><summary>Full log</summary>` blocks for longer context the maintainer might need but should not have to scroll past.
- **Preserve error messages verbatim**: sanitize paths and private data, but never paraphrase or reword the actual error string. Maintainers grep their codebase for exact error messages.

### Code block formatting

Clean up code blocks before including them in the report:

- **Strip trailing whitespace**: remove trailing spaces and tabs from every line inside code blocks. They are invisible but inflate diffs and trigger linter warnings in some editors.
- **Dedent**: remove any common leading whitespace shared by all non-empty lines in the block. The content should start at column 0 inside the fence. If the original source was indented (e.g., a method body or a nested YAML key), strip the shared prefix so the block stands on its own.
- **Wrap long lines**: if a line exceeds ~120 characters and can be broken without disrupting syntax highlighting for the block's lexer, insert a line break at a natural boundary (after a comma, pipe, flag, or path separator). Do not wrap lines where a break would confuse the lexer or change semantics: single-line error messages, URLs, hash strings, and base64 blobs should stay intact.

### Code block language IDs

Use precise Pygments lexer IDs on fenced code blocks so GitHub renders them with proper syntax highlighting. Never use bare ```` ``` ```` when a specific lexer applies. Common IDs for bug reports:

| Content                    | Lexer ID                | Notes                                                                               |
| :------------------------- | :---------------------- | :---------------------------------------------------------------------------------- |
| Python traceback           | `pytb`                  | Full `Traceback (most recent call last):` output.                                   |
| Python console session     | `pycon`                 | `>>>` prompts with output.                                                          |
| Shell session (Unix)       | `shell-session`         | `$` prompts with output. Prefer over `bash` when showing command + output together. |
| Shell session (PowerShell) | `pwsh-session`          | `PS>` prompts with output.                                                          |
| PowerShell script          | `pwsh`                  | Pure PowerShell code without prompts.                                               |
| Plain shell commands       | `bash` / `zsh` / `fish` | Pure commands without output.                                                       |
| JSON output                | `json`                  | API responses, config dumps.                                                        |
| YAML config                | `yaml`                  | Workflow snippets, config files.                                                    |
| TOML config                | `toml`                  | `pyproject.toml` sections.                                                          |
| Rust panic / backtrace     | `rust`                  | `thread 'main' panicked at...` output.                                              |
| Go panic                   | `go`                    | `goroutine 1 [running]:` output.                                                    |
| JavaScript error           | `js`                    | Node.js stack traces.                                                               |
| Plain text / logs          | `text`                  | When no lexer fits. Still better than bare ```` ``` ````.                           |

Match the lexer to the content, not the project language. A Python project's bug report might include `yaml` for a workflow snippet, `shell-session` for a CLI invocation, and `pytb` for the traceback, all in the same report.
