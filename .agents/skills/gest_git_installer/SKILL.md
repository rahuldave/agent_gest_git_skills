---
name: gest_git_installer
description: Install Git/GitButler Gest package extras after npx installs the skills, including hooks/settings and AGENTS guidance.
---

# Gest Git Installer

Use this package-specific installer after a user has installed the Git/GitButler
Gest skills with:

```bash
npx skills add rahuldave/agent_gest_git_skills -a codex --skill '*' -y
```

`npx skills add` installs skill folders only. It does not run hooks or copy
root-level package extras. Runtime references, helper scripts, and setup
templates are vendored inside the installed skill folders. When the user asks
to install the Git/GitButler Gest hooks/settings or AGENTS guidance, run the
bundled helper from this skill directory:

```bash
bash .agents/skills/gest_git_installer/scripts/install_gest_git_package.sh .
```

For a normal fresh install, explain the flow plainly: `npx skills add` got the
skills, this installer adds hooks/settings and optional AGENTS starter guidance,
and `gsu` handles ordinary project setup afterward.

Resolve the script relative to the installed `gest_git_installer` skill if it
is installed globally or in another agent skill root. The helper fetches this
package repository into a temporary directory and runs the repo-level installer
script against the target repo.

The installer preserves existing AGENTS.md and unrelated Claude/Codex settings
and hooks. It fails with a clear conflict if an existing hook script or managed
hook command differs. Re-run after resolving the conflict. To install a
particular source revision, set `AGENT_GEST_GIT_SKILLS_COMMIT` to its commit SHA;
for a local clone also set `AGENT_GEST_GIT_SKILLS_SOURCE`. The installed revision
and source dirty status are recorded in `.agents/gest-git-install.json`.

Missing workflow tools should be reported clearly; they should not be treated
as a reason that `npx skills add` itself failed.
