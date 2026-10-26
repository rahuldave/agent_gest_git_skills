# Portable setup and commands

For the current review build (before merge), install from the actual topic:

```sh
git clone --branch codex/lanes-portable-tools --single-branch https://github.com/rahuldave/agent_gest_git_skills.git lanes-tools
cd lanes-tools
git rev-parse HEAD
# Compare this SHA with the reviewed PR head before running the installer.
node .agents/skills/lanes/scripts/install.mjs --dry-run
node .agents/skills/lanes/scripts/install.mjs
```

This installs both global native skills and the standalone CLI. The install
manifest records the exact source revision and content hashes. The review
branch is a source preview, not a tagged release.

After that PR is merged to main, install just the skill for the desired
provider globally with:

```sh
npx skills add rahuldave/agent_gest_git_skills -g -a codex -a claude-code --skill lanes --copy -y
```

The `npx` command above fetches main and is a post-merge path. The manifest in
`~/.local/share/lanes/install.json` records the exact content hashes and source
revision when available. Installation does not create credentials or project
bindings. Refresh explicitly; source publication does not update installed
copies. New agent sessions discover the installed skill; existing sessions can
read the installed SKILL.md explicitly. Skill discovery encourages reporting;
it cannot guarantee every session will invoke it.

Node.js 22 or newer is the only runtime prerequisite. After `npx` installs the
skill, invoke its bundled installer with `--cli-only` to add the PATH command.
No root-level repository scripts are needed. A skill-only install can invoke
`node <installed-skill>/scripts/lanes.mjs` directly without a PATH command.
Do not change native approval policies, add hooks or install servers.

The installer deliberately preserves shell startup files. This works
immediately whether or not your shell already includes the command directory:

```sh
~/.local/bin/lanes --help
export PATH="$HOME/.local/bin:$PATH"
lanes --version
```

The export applies to the current shell only. To make it persistent, add that
PATH entry to your own shell configuration, or continue using the full command
path. Restart agent sessions after skill installation. Existing sessions can
read the installed `~/.codex/skills/lanes/SKILL.md` or
`~/.claude/skills/lanes/SKILL.md` explicitly; Codex installations using a custom
`CODEX_HOME` use its `skills/lanes` directory instead.

## Register a project once

The owner first creates a project lane through the cloud API with stable IDs
and issues a separate revocable reporter credential scoped to that project.
Currently credential provisioning is operator-managed Worker configuration;
there is no self-service token UI. Installing a skill does not provision or
broaden authorization. Server operations must allow `workspace:read`,
`todo:write`, `attention:write` as needed; human handling/owner credentials are
separate. No execution capabilities are needed for reporting.

With those reviewed IDs, write the non-secret project binding explicitly:

```sh
lanes bind < reviewed-project-binding.json
```

Binding format:

```json
{"version":1,"apiUrl":"https://YOUR_LANES_API","workspaceId":"YOUR_WORKSPACE","projectId":"STABLE_PROJECT_ID","laneId":"STABLE_PROJECT_LANE"}
```

The command creates `.lanes.json` in the current directory, or use
`--project DIR`. It refuses to replace a different existing binding. Commit
this non-secret file if appropriate. Renamed directories and physical
worktrees retain the same project ID; copying the binding grants no authority.

Provision each reporter credential through stdin from a protected file,
never in command arguments, a committed binding, a transcript or a shell log:

```sh
lanes credential add < protected-reporter-grant.json
```

Grant format (the token is issued separately by the workspace operator):

```json
{"apiUrl":"https://YOUR_LANES_API","workspaceId":"YOUR_WORKSPACE","projectId":"STABLE_PROJECT_ID","principal":"codex","token":"ISSUED_SCOPED_TOKEN"}
```

Use `principal: "claude"` for the separate Claude grant. Saved credentials
default to `$XDG_CONFIG_HOME/lanes/credentials.json`, or
`~/.config/lanes/credentials.json`. `LANES_CREDENTIALS_FILE` can select an
absolute protected file. They must be owned by the current user and mode 0600;
symlinked credential files are refused. Credentials on one OS account are
accessible to programs running as that account; this is not a process sandbox.
Different machines need separate provisioned credentials. Remove the server
token hash to revoke; deleting a local file alone does not revoke a copied token.
Use `credential add --replace` only for deliberate rotation of the same grant.

## Command conventions

Choose `--principal codex|claude` explicitly, or set `LANES_PRINCIPAL` in
provider-specific tool configuration. No implicit owner fallback exists.
`--project DIR` finds that project's binding; `--lane ID` chooses a sublane.
Writes consume a JSON object on stdin, maximum 64 KiB. Use stable
`--key COMMAND_UUID` (or `LANES_COMMAND_KEY`) for reconciliation.

- `doctor`: local configuration check, no network and no secret output.
- `workspace get`: read the authorized workspace structure.
- `items list`: collect all index pages for the selected lane and descendants.
- `todo create|list|get ID|update ID`: ordinary todo resources.
- `attention create|list|get ID|update ID`: explicit attention resources.
- `attention respond|resolve|withdraw|dismiss ID`: explicit lifecycle commands;
  permission and revision checks are server-side. Agents usually create/read/
  resolve their own requests, and cannot use owner handling operations.

Creation generates an item UUID if omitted; supply one explicitly when the
source conversation needs an identity before sending. Successful writes print
the durable API receipt plus `client.commandKey` and `client.resourceId`.
If the response is lost the CLI makes at most three bounded calls with the
same body/key, then exits **not confirmed**. Keep the original JSON and IDs in
the conversation to retry or reconcile. There is no local queue.

Responses saved in the web UI are read on resumption. Lanes does not push a
new prompt into an idle/closed provider session. Use the stored source ID or
verified return link to return there; continue the agent manually as needed.
