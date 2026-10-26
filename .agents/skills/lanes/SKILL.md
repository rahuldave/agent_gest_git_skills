---
name: lanes
description: Report explicit human attention requests and manage ordinary todos in a configured Lanes project from Codex, Claude or a terminal. Use before yielding for a real answer, decision, review or action, and check saved replies on resumption. Also install the portable client when requested. Routine running/completed status is not a request.
---

# Lanes

Lanes is a durable cloud inbox. This skill and the short-lived `lanes` command
work from any registered project. They do not require Gest, the Lanes source
checkout, a local server, hooks, a watcher, a queue or an MCP bridge.

## Set up or check availability

Use `lanes --help`. If it is absent, use `node scripts/lanes.mjs` relative to
this skill directory. When the user asks to install it globally, run the bundled
`node scripts/install.mjs --dry-run`, inspect conflicts, then run without
`--dry-run`. It copies the CLI to `~/.local/bin/lanes` and the skill to the native
Codex and Claude skill directories. It preserves unrelated files and refuses
overwriting user edits. Never replace conflicting files without the user's
authorization. Use `--cli-only` if skills are already installed through `npx`.
No hooks, provider settings, approval behavior or shell files are changed.

In the working project, run:

```sh
lanes --principal codex doctor
# In Claude use --principal claude instead.
```

The nearest `.lanes.json`, bounded by the Git root, supplies the project/lane
binding. Another worktree of the same project can reuse its stable IDs.
Credentials are separate, mode 0600, and must match the API origin, workspace,
project and principal. Never use the human owner's token. If configuration or
permission is missing, say **publication not confirmed**, keep the actual
request in the source conversation, and use the setup reference below. Do not
invent a new project identity or grant yourself access.

## Report a real request

Before yielding because the human needs to answer, decide, review, approve or
act, send a specific request through stdin. Choose a UUID once and retain it and
the command key in the source conversation for reconciliation:

```sh
lanes --principal codex attention create --key STABLE_COMMAND_UUID <<'JSON'
{
  "itemId": "STABLE_REQUEST_UUID",
  "title": "Review the proposed import",
  "actionNeeded": "Review the preview and tell me which projects to include.",
  "kind": "review",
  "source": {
    "provider": "codex",
    "sessionId": "ACTUAL_SESSION_ID",
    "sessionLabel": "Import review"
  }
}
JSON
```

Use the real provider and session locator. Only include `source.url` when an
actual supported HTTPS return link is known. Session labels/IDs remain useful
when deep linking is unavailable. The CLI fills the bound project ID. Never
fabricate an attention request to demonstrate reporting. Do not report routine
running, successful completion or an ordinary open todo as waiting for a human.

Require `receipt.durable: true`. The receipt confirms storage, not delivery to
an agent. On failure say **not confirmed**, retain the same item ID, key and
payload, and read/retry deliberately; do not enqueue locally or create a
replacement request. Native approval prompts remain controlled by the provider.

## Resume and reconcile

```sh
lanes --principal codex items list
lanes --principal codex attention get REQUEST_UUID
```

Reads never resolve a request. A saved Lanes reply is waiting for pickup: it
does not wake an agent, submit a prompt, guarantee delivery or launch an app.
On resumption read it, perform the authorized action, then explicitly resolve
the request with its current revision and actual outcome:

```sh
lanes --principal codex attention resolve REQUEST_UUID --key RESOLUTION_UUID <<'JSON'
{"expectedRevision":2,"outcome":"satisfied"}
JSON
```

Use `denied` only when the human actually declined. If your own request is no
longer needed, use `attention withdraw ID` with its current `expectedRevision`;
withdrawal does not satisfy an execution prerequisite. The `no_longer_required`
outcome is a human-only transition. Do not
resolve merely because you sent another prompt, finished a turn, read the item
or saved a reply. Retain unresolved requests across handoffs. Do not promise
automatic wake-up, remote process termination or exactly-once external effects.

## Ordinary work

Create a first-class todo using `todo create` with `{itemId,title,description?,timing?}`.
It is ordinary non-executing work. Dates use `timing.plannedDate` (YYYY-MM-DD),
`dueDate`, `dueAt` or `remindAt`; do not invent a numeric priority policy.
`todo update ID` requires `expectedRevision`. `--lane ID` selects an explicitly
authorized sublane; the server enforces scope. Listing is bounded and paginated.
This reporting client does not implement task claiming or grant execution.

For first-time project registration, credential provisioning, other machines,
copy-only installation and command details, read
[setup and commands](references/setup.md).
