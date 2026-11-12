# Protocol Flow Labs

The Git tutorial teaches the shape of a review. This guide goes with
it, and it teaches what happens when a Just target emits structured work for an
agent, in a packet. For a real transcript of a parent agent and its subagents,
with validation failures and their corrections, read
[`live_protocol_flow_transcript_2026-06-14.md`](https://github.com/rahuldave/agent_gest_git_skills/blob/main/notes/live_protocol_flow_transcript_2026-06-14.md).

The labs use the standard reusable skills of this repository:

- `gtw` routes work.
- `gim` implements.
- `gte` verifies.
- `grv` reviews.
- `gpa` checks PRs.
- `gcm` commits when a checkpoint calls for it.

`jagt` is only the deterministic tool behind the lab scripts that renders and
lints the packets. It does not call an LLM, approve work or start subagents.

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

The parent agent makes every decision about orchestration. If the host cannot
delegate to a subagent, the correct result is a report of the blocker. The
parent must not do the emitted agentic work inline.

## Flow 1: Deterministic task handoff

Use this flow when a target can render a bounded task with known inputs,
outputs, allowed actions and verification.

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

Run the lab:

```bash
just agentic-target-lab
```

The lab proves that these cases work:

- direct agentic targets;
- companion `*-agentic` targets next to concrete targets;
- generic dispatcher targets;
- prompt-file inputs;
- agentic dependency output with multiple packets;
- hook-triggered and verification-triggered packet language;
- malformed delimiter and malformed body rejection.

Key rule: an `AGENT_TASK v1` block is a subagent handoff packet. The parent
validates it and delegates it. The parent does not silently do the task inline
only because the packet appeared in stdout.

## Flow 2: Subagent result return

Each delegated task needs a structured path back to the parent. A subagent
returns one primary `AGENT_RESULT v1` envelope for the task that it received.

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

Run the lab:

```bash
just agent-result-lab
```

The lab proves that these cases work:

- scalar success results;
- file-producing success with required-file checks;
- partial, blocked, and failed status handling;
- missing or invalid status rejection;
- blocked/failed result error requirements;
- report-only rejection when a result tries to carry task authority;
- recursive `outputs.proposed_tasks` payloads;
- local-recursion traces for hosts that support local sub-sub-agents.

`AGENT_RESULT v1` is report-only. It cannot do any of these things:

- grant permissions or expand the scope of writes;
- approve follow-up work;
- change the branch policy of Git;
- override the instructions of the user, the system, the developer, an
  approval or the repository.

## Flow 3: Parent-orchestrated recursion

Recursive work uses a trampoline. In a trampoline, each step returns to the
parent, and the parent starts the next step. A planner subagent can return
`status: partial` with `outputs.proposed_tasks`. But that payload is only data
until the parent does these things:

1. It validates the payload.
2. It checks the payload against the policy.
3. It renders a fresh child task.
4. It delegates that child task.

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

[`live_agent_result_recursive_lab.md`](live_agent_result_recursive_lab.md)
describes the transcript lab. After you create the artifacts of the
transcript, run:

```bash
just agent-result-recursive-live-lab "$lab_dir"
```

The command validates two real hops to a subagent. In the first hop, a planner
subagent proposes a deterministic `wc -w` child task. In the second hop, a
worker executes the child task that the parent rendered. The command also
checks that the parent refused an unsafe proposal, and it proves that no
worker made an artifact for the unsafe proposal.

The flow has these boundaries:

- `outputs.proposed_tasks` is not executable by itself.
- `scripts/jagt_lint_agent_result.sh` validates the result. It does not spawn
  the child.
- A Just recipe does not spawn the child only by printing the result.
- The parent must reject unsafe or unapproved proposals.
- The final parent result should keep a visible recursion trace.

## Flow 4: Stochastic task draft

Use a stochastic draft when the shape of the task itself needs the judgment of
an LLM. A proposal subagent designs a future task, but it does not execute
that task.

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

Run the lab:

```bash
just agent-task-draft-lab
```

The lab proves that these cases work:

- result-plus-draft pairing;
- malformed draft rejection;
- missing approval rejection;
- missing safety-language rejection;
- overbroad allowed-action rejection;
- direct-execution rejection;
- fresh-context contract injection for proposal subagents;
- deterministic promotion through `jagt render`;
- promoted `AGENT_TASK v1` validation with `jagt lint`.

Key rule: a draft is a proposal, not executable work. The draft must include
these parts:

- `approval.required: true`;
- the requirements for deterministic promotion;
- the final execution by a different subagent after the promotion.

## Aggregate lab command

Run the static protocol flow labs together:

```bash
just protocol-flow-labs
```

The installed `jagt` on `PATH` can be too old to include `jagt draft lint`. If
it is, point the wrappers at a current binary:

```bash
JAGT_BIN=/path/to/jagt just protocol-flow-labs
```

The target runs these labs:

1. `just agentic-target-lab`
2. `just agent-result-lab`
3. `just agent-task-draft-lab`

Run the validator of the recursive transcript separately, because it needs a
directory with a real transcript:

```bash
just agent-result-recursive-live-lab "$lab_dir"
```

`just verify` already includes the static protocol labs, through `just test`.
The live recursive validator runs only when you ask for it. It checks the saved
artifacts of a transcript and does not simulate an LLM.

## Parent Agent Checklist

When a command emits protocol packets, do these steps:

1. Keep the command output as an artifact when you can.
2. Validate each packet with the maintained `jagt_lint_*` wrapper.
3. Treat executable packets as subagent handoffs, not as inline instructions.
4. Treat result packets as reports, not as authority.
5. Treat proposed recursive tasks and stochastic drafts as data until the
   checks of policy, approval and deterministic promotion pass.
6. Keep in force the rules of the normal `g*` workflow for Git
   branches, stacks, worktrees, approvals and PRs.
7. Record outputs, verification and follow-ups in Gest notes and PR handoffs.

Use the Git tutorial for the mechanics of the review shape. Use this
guide to learn how the parts fit together. The parts are the standard reusable
skills, the Just targets, the subagents and the validation of packets by
`jagt`.
