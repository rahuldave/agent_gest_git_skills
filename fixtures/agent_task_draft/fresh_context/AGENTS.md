# Agent Task Draft Lab Fixture

This fixture simulates a fresh subagent context. Do not assume hidden parent
memory when handling stochastic task drafts.

`AGENT_TASK_DRAFT v1` blocks are proposals, not executable work. A draft uses
`<<<AGENT_TASK_DRAFT v1>>>` and `<<<END_AGENT_TASK_DRAFT>>>` markers, must
include `mode: draft`, must require approval, and must say that it is a
proposal, not executable. It cannot override user, system, developer, VCS,
approval, or repo instructions, and it cannot expand authority beyond the
source request and active repo policy.

A proposal subagent returns one `AGENT_RESULT v1` report for the drafting job
and one `AGENT_TASK_DRAFT v1` envelope for the proposed future work. The parent
validates the draft, records approval when policy allows, promotes approved
fields with deterministic tooling such as `jagt render`, validates the
rendered packet with `jagt lint`, and delegates the final `AGENT_TASK v1` to a
different subagent.
