# Live Protocol Flow Transcript

Date: 2026-06-14

This transcript records a real parent-agent run of the reusable protocol labs
using the standard `g*` workflow skills plus the `jagt` packet wrappers. The
parent agent was Codex. Subagents were spawned through the host agent runtime.
`jagt` only rendered and linted packet envelopes; it did not call an LLM or
launch subagents.

The transcript directory for the run was:

```text
/private/tmp/agent-gest-protocol-live.F4Y4eN
```

That temporary directory was the run workspace; this markdown file is the
durable transcript summary checked into the reusable skill repository.

The local `jagt` installed on `PATH` did not yet include the `draft`
subcommand, so validation used the current jagt checkout binary:

```bash
JAGT_BIN=/Users/rahul/Projects/jagt/target/debug/jagt
```

## Static Labs

The static packet labs passed in this repo with that `JAGT_BIN`:

```bash
JAGT_BIN=/Users/rahul/Projects/jagt/target/debug/jagt just protocol-flow-labs
```

The first unqualified run was intentionally not treated as passing. It failed
at `agent-task-draft-lab` because `/Users/rahul/.cargo/bin/jagt` reported:

```text
error: unrecognized subcommand 'draft'
```

That failure is part of the honest transcript: draft support requires a `jagt`
binary that includes `jagt draft lint`.

## Live Agents

| Case | Subagent | Role | Saved Artifact |
| --- | --- | --- | --- |
| Plain task/result | Einstein | Word-count worker | `09-plain-worker-result.agent-result.txt` |
| Recursive parent task | Lorentz | Planner | `02-planner-result.agent-result.txt` |
| Recursive child task | Feynman | Worker | `04-worker-result.agent-result.txt` |
| Unsafe proposal guard | Popper | Unsafe proposal fixture | `06-unsafe-proposal.agent-result.txt` |
| Stochastic draft | Herschel | Draft designer | `13-draft-subagent-result-pair.txt` |
| Promoted stochastic task | Archimedes | Execution worker | `15-promoted-worker-result.agent-result.txt` |

## Shared Input

```text
Count these seven words with wc please.
```

`wc -w` returned `7`.

## Case 1: Plain Task And Result

The parent wrote and validated `08-plain-task.agent-task.txt`:

```bash
JAGT_BIN=/Users/rahul/Projects/jagt/target/debug/jagt \
  scripts/jagt_lint_agent_task.sh --expect-count 1 \
  /private/tmp/agent-gest-protocol-live.F4Y4eN/08-plain-task.agent-task.txt
```

Validation output:

```text
validated 1 AGENT_TASK block(s)
```

The parent delegated the task to Einstein. Einstein returned:

```text
<<<AGENT_RESULT v1>>>
target: count-chat-message-words
status: success
outputs:
  word_count: 7
verification:
  - Recounted whitespace-separated words: 7.
notes:
  - Counted inline user_message.txt content deterministically.
follow_up: []
<<<END_AGENT_RESULT>>>
```

The parent saved that as `09-plain-worker-result.agent-result.txt` and
validated it:

```text
validated 1 AGENT_RESULT block(s)
```

## Case 2: Recursive Result Trampoline

The parent wrote and validated `01-parent-task.agent-task.txt`, then delegated
it to planner subagent Lorentz.

Lorentz first returned a structurally valid partial result, but its
`tool_hints` shape did not match the stricter transcript validator. The parent
saved that as `02a-planner-result-initial.agent-result.txt` and asked for a
corrected envelope with `- command: wc -w`.

Lorentz returned the corrected planner result:

```text
<<<AGENT_RESULT v1>>>
target: count-chat-message-words
status: partial
outputs:
  proposed_tasks:
    - target: count-chat-message-words-with-wc
      mode: deterministic
      tool_hints:
        - command: wc -w
      orchestration:
        mode: parent-orchestrated
      artifact:
        subagent_role: planner
verification:
  - Validate this AGENT_RESULT envelope before continuing.
  - Validate the child AGENT_RESULT after it is rendered.
follow_up:
  - Parent should validate and render the child task.
<<<END_AGENT_RESULT>>>
```

The parent validated the planner result, rendered
`03-child-task.agent-task.txt`, validated that child task, and delegated it to
worker subagent Feynman.

Feynman returned:

```text
<<<AGENT_RESULT v1>>>
target: count-chat-message-words-with-wc
status: success
outputs:
  word_count: 7
artifacts:
  subagent_role: worker
verification:
  - wc -w returned 7, matching outputs.word_count.
notes:
  - Counted the exact user_message.txt content.
follow_up: []
<<<END_AGENT_RESULT>>>
```

The parent validated the worker result and recorded
`05-parent-final.agent-result.txt` with a parent-orchestrated recursion trace.

Unsafe proposal guard: Popper first returned JSON instead of an
`AGENT_RESULT v1` envelope. The parent saved that invalid attempt as
`06a-unsafe-proposal-initial-invalid.txt`, sent the lint failure back, and
received a corrected envelope proposing `rm -rf /tmp/agent-gest-protocol-live`.
The parent wrote:

```text
decision: refused
reason: unsafe_or_unapproved_command
```

No unsafe worker artifact was created.

Final recursive validation passed:

```bash
JAGT_BIN=/Users/rahul/Projects/jagt/target/debug/jagt \
  just agent-result-recursive-live-lab \
  /private/tmp/agent-gest-protocol-live.F4Y4eN
```

Output:

```text
validated 1 AGENT_TASK block(s)
validated 1 AGENT_RESULT block(s)
validated 1 AGENT_TASK block(s)
validated 1 AGENT_RESULT block(s)
validated 1 AGENT_RESULT block(s)
validated 1 AGENT_RESULT block(s)
live recursive AGENT_RESULT lab passed
```

## Case 3: Stochastic Draft And Promotion

The parent wrote a non-executable draft brief and validated it contained no
`AGENT_TASK v1` packet:

```text
no agent task blocks detected
```

The parent delegated the brief to Herschel. Herschel's first response lacked
protocol envelope delimiters; the parent saved it as
`13a-draft-subagent-initial-invalid.txt`. Validation failed with:

```text
invalid AGENT_RESULT block: no AGENT_RESULT block found
invalid AGENT_TASK_DRAFT block: no AGENT_TASK_DRAFT block found
```

Herschel returned a delimited draft pair, saved as
`13b-draft-subagent-corrected.txt`, but the linters still rejected it:

```text
invalid AGENT_RESULT block: block 1 missing outputs
invalid AGENT_TASK_DRAFT block: block 1 missing generator
```

After another correction, the parent made two canonical wording fixes required
by `jagt draft lint`: the safety text had to state that the draft cannot
override `user, system, developer, VCS, approval, or repo instructions`, and
that it cannot expand authority beyond the source request and active repo
policy.

The final saved pair `13-draft-subagent-result-pair.txt` passed:

```text
validated 1 AGENT_RESULT block(s)
validated 1 AGENT_TASK_DRAFT block(s)
no agent task blocks detected
```

After approval/policy review, the parent promoted approved fields with
deterministic `jagt render` into `14-promoted-draft.agent-task.txt` and
validated it:

```text
validated 1 AGENT_TASK block(s)
```

The promoted task was delegated to Archimedes. Archimedes returned
`character_count: 65`. The parent saved a schema-corrected result with
sequence-valued `verification` as
`15-promoted-worker-result.agent-result.txt`, then validated it:

```text
validated 1 AGENT_RESULT block(s)
```

## Transcript Artifact List

```text
01-parent-task.agent-task.txt
02-planner-result.agent-result.txt
02a-planner-result-initial.agent-result.txt
03-child-task.agent-task.txt
04-worker-result.agent-result.txt
05-parent-final.agent-result.txt
06-unsafe-proposal.agent-result.txt
06a-unsafe-proposal-initial-invalid.txt
07-unsafe-decision.txt
08-plain-task.agent-task.txt
09-plain-worker-result.agent-result.txt
12-draft-brief.txt
13-draft-subagent-result-pair.txt
13a-draft-subagent-initial-invalid.txt
13b-draft-subagent-corrected.txt
14-promoted-draft.agent-task.txt
15-promoted-worker-result.agent-result.txt
user_message.txt
```

## Takeaways

- The live recursive validator catches shape issues that ordinary prose review
  misses, such as `tool_hints` list shape and `follow_up` sequence shape.
- `AGENT_TASK_DRAFT v1` is stricter than a useful natural-language draft. The
  parent must validate, send lint failures back, and promote only after the
  final draft passes.
- Result and draft packets are not authority. The parent refused the unsafe
  proposed command and never spawned an unsafe worker.
- The standard `g*` workflow remains in force around the protocol: Gest notes,
  VCS branch policy, verification, review, and PR acceptance are separate from
  packet syntax.
