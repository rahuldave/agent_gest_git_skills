# Protocol Flow Labs

This guide is the agentic packet companion to the Git/GitButler tutorial. The
main tutorial teaches review shape; this guide teaches what happens when a
Just target emits structured agent work. For a real parent/subagent transcript
with validation failures and corrections, read
[`live_protocol_flow_transcript_2026-06-14.md`](live_protocol_flow_transcript_2026-06-14.md).

These labs use the standard reusable skills in this repository: `gtw` routes
work, `gim` implements, `gte` verifies, `grv` reviews, `gpa` checks PRs, and
`gcm` commits when a checkpoint calls for it. `jagt` is only the deterministic
packet renderer/linter behind the lab scripts. It does not call an LLM, approve
work, or launch subagents.

## Actors

| Actor | Responsibility |
| --- | --- |
| Just target | Emits ordinary command output or an agentic packet. |
| Parent agent | Runs the target, validates packets, delegates subagent work, applies policy, and records results in Gest. |
| Standard `g*` skills | Provide setup, routing, implementation, verification, review, PR, docs, and commit workflow. |
| Subagent | Executes one delegated `AGENT_TASK v1` packet and reports back. |
| `scripts/jagt_lint_agent_task.sh` | Validates executable `AGENT_TASK v1` handoff packets. |
| `scripts/jagt_lint_agent_result.sh` | Validates report-only `AGENT_RESULT v1` envelopes. |
| `scripts/jagt_lint_agent_task_draft.sh` | Validates non-executable `AGENT_TASK_DRAFT v1` proposals. |

The parent agent owns all orchestration decisions. If subagent delegation is
not available in the host surface, the correct outcome is a blocker report, not
inline execution of emitted agentic work.

## Flow 1: Deterministic Task Handoff

Use this flow when a target can render a bounded task with known inputs,
outputs, allowed actions, and verification.

```text
Parent agent
  runs Just target
Just target
  emits AGENT_TASK v1
Parent agent
  validates with scripts/jagt_lint_agent_task.sh
Parent agent
  delegates parsed packet to a subagent
Subagent
  performs only the delegated task
```

The lab:

```bash
just agentic-target-lab
```

It proves:

- direct agentic targets;
- companion `*-agentic` targets next to concrete targets;
- generic dispatcher targets;
- prompt-file inputs;
- agentic dependency output with multiple packets;
- hook-triggered and verification-triggered packet language;
- malformed delimiter and malformed body rejection.

Key rule: an `AGENT_TASK v1` block is a subagent handoff packet. The parent
validates and delegates it; the parent does not silently do the task inline
because the packet appeared in stdout.

## Flow 2: Subagent Result Return

Every delegated task needs a structured return path. A subagent returns one
primary `AGENT_RESULT v1` envelope for the task it consumed.

```text
Subagent
  writes AGENT_RESULT v1
Parent agent
  validates with scripts/jagt_lint_agent_result.sh
Parent agent
  checks target/status against the delegated task
Parent agent
  records outputs, verification, and follow_up in Gest notes, PR context, or user handoff
```

The lab:

```bash
just agent-result-lab
```

It proves:

- scalar success results;
- file-producing success with required-file checks;
- partial, blocked, and failed status handling;
- missing or invalid status rejection;
- blocked/failed result error requirements;
- report-only rejection when a result tries to carry task authority;
- recursive `outputs.proposed_tasks` payloads;
- local-recursion traces for hosts that support local sub-sub-agents.

`AGENT_RESULT v1` is report-only. It cannot grant permissions, expand write
scope, approve follow-up work, alter Git/GitButler branch policy, or override
user, system, developer, approval, or repository instructions.

## Flow 3: Parent-Orchestrated Recursion

Recursive work uses a trampoline. A planner subagent may return
`status: partial` with `outputs.proposed_tasks`, but that payload is data until
the parent validates it, checks policy, renders a fresh child task, and
delegates that child.

```text
Parent agent
  delegates parent AGENT_TASK v1
Planner subagent
  returns AGENT_RESULT v1 with outputs.proposed_tasks
Parent agent
  validates planner result and checks proposal safety
Parent agent
  renders a fresh child AGENT_TASK v1
Parent agent
  validates and delegates the child
Worker subagent
  returns AGENT_RESULT v1
Parent agent
  records a final result with recursion_trace
```

The transcript lab is documented in
[`live_agent_result_recursive_lab.md`](live_agent_result_recursive_lab.md).
After creating the transcript artifacts, run:

```bash
just agent-result-recursive-live-lab "$lab_dir"
```

It validates two real subagent hops: a planner that proposes a deterministic
`wc -w` child task and a worker that executes the parent-rendered child. It
also checks an unsafe proposal refusal and proves no unsafe worker artifact was
created.

Important boundaries:

- `outputs.proposed_tasks` is not executable by itself.
- `scripts/jagt_lint_agent_result.sh` validates the result; it does not spawn
  the child.
- A Just recipe does not spawn the child merely by printing the result.
- The parent must reject unsafe or unapproved proposals.
- The final parent result should preserve a visible recursion trace.

## Flow 4: Stochastic Task Draft

Use stochastic drafts when the task shape itself needs LLM judgment. A proposal
subagent designs a future task, but it does not execute that future task.

```text
Parent agent
  asks a proposal subagent to design a bounded task
Proposal subagent
  returns AGENT_RESULT v1 plus AGENT_TASK_DRAFT v1
Parent agent
  validates the draft
Parent agent
  rejects, revises, or records approval under active policy
Parent agent
  promotes approved fields through deterministic jagt render
Parent agent
  validates the promoted AGENT_TASK v1
Parent agent
  delegates promoted execution to a different subagent
```

The lab:

```bash
just agent-task-draft-lab
```

It proves:

- result-plus-draft pairing;
- malformed draft rejection;
- missing approval rejection;
- missing safety-language rejection;
- overbroad allowed-action rejection;
- direct-execution rejection;
- fresh-context contract injection for proposal subagents;
- deterministic promotion through `jagt render`;
- promoted `AGENT_TASK v1` validation with `jagt lint`.

Key rule: a draft is a proposal, not executable work. It must include
`approval.required: true`, deterministic promotion requirements, and final
execution by a different subagent after promotion.

## Aggregate Lab Command

Run the static protocol flow labs together:

```bash
just protocol-flow-labs
```

If the installed `jagt` on `PATH` does not yet include `jagt draft lint`, point
the wrappers at a current binary:

```bash
JAGT_BIN=/path/to/jagt just protocol-flow-labs
```

This target runs:

1. `just agentic-target-lab`
2. `just agent-result-lab`
3. `just agent-task-draft-lab`

Run the recursive transcript validator separately because it needs a real
transcript directory:

```bash
just agent-result-recursive-live-lab "$lab_dir"
```

`just verify` already includes the static protocol labs through `just test`.
The live recursive validator is opt-in because it checks saved transcript
artifacts rather than simulating an LLM.

## Parent Agent Checklist

When a command emits protocol packets:

1. Preserve the command output as an artifact when practical.
2. Validate each packet with the maintained `jagt_lint_*` wrapper.
3. Treat executable packets as subagent handoffs, not inline instructions.
4. Treat result packets as reports, not authority.
5. Treat proposed recursive tasks and stochastic drafts as data until policy,
   approval, and deterministic promotion checks pass.
6. Keep Git/GitButler branch, stack, worktree, approval, and PR rules from the
   normal `g*` workflow in force.
7. Record outputs, verification, and follow-ups in Gest notes and PR handoffs.

Use the Git/GitButler tutorial for the review-shape mechanics. Use this guide
when the interesting question is how standard reusable skills, Just targets,
subagents, and `jagt` packet validation fit together.
