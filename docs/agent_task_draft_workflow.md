# AGENT_TASK_DRAFT v1 workflow

`AGENT_TASK_DRAFT v1` is for stochastic task design, where a model proposes the
shape of the task. Use it when the parent wants a subagent to propose the
right bounded `AGENT_TASK v1`. If the work is deterministic enough to render
directly, do not use it.

A draft is a proposal envelope, and nobody executes it. Before any work runs,
the parent validates the draft, reviews it and approves it. Deterministic tools
then promote it to a final `AGENT_TASK v1`, and a different subagent executes
that task.

## When to use drafts

Use a draft when the shape of the task itself needs judgment, for example in
these cases:

- to turn a vague request for an investigation into a bounded implementation task
- to choose a useful target for an exploratory analysis of a dataset
- to propose the verification steps for a set of changed files

Do not use a draft when a project script can already emit a stable
`AGENT_TASK v1`. Such a task has known inputs, outputs, allowed actions and
verification. In that case, render the final task directly.

## Workflow

1. The parent asks a subagent to design the task.
2. The design subagent returns one `AGENT_RESULT v1` for the proposal job and
   one `AGENT_TASK_DRAFT v1` envelope after it.
3. The parent validates the shape of the draft and its policy with
   `jagt draft lint`.
4. The parent rejects the draft, asks for a revision, records approval under
   the active policy, or asks the user for approval.
5. The parent promotes the approved fields with deterministic tools. In the
   minimum viable product (MVP), the path is `jagt render` followed by
   `jagt lint`.
6. A different execution subagent receives the promoted `AGENT_TASK v1`.

The proposal subagent must not execute the work that it proposed.

## Approval and authority

All v1 drafts must include `approval.required: true`. A draft cannot claim that
it is already approved, and it cannot bypass the sandbox or the VCS rules. It
also cannot expand authority beyond the source request, the active policy of
the repo or the current state of approval.

If the parent cannot approve safely under the current policy, it asks the user.

## Contract delivery

A fresh subagent does not always inherit the memory of the parent. Give it the draft
contract through one of these paths:

- the `AGENTS.md` of the repo
- the references of an installed skill, such as
  `.agents/skills/just/references/command_contract.md` from jnterfaces
- an excerpt copied into the delegation prompt of the parent
- an `AGENTS.md` local to the fixture, in labs

`just agent-task-draft-lab` includes a fresh-context fixture, which has no
memory of a parent. The fixture proves that the parent can supply the contract
without hidden memory.

## Verification

Run:

```bash
just agent-task-draft-lab
```

The lab validates a pair of a result and a draft, and it rejects malformed and
unsafe drafts. It also rejects the direct execution of a draft. Then it
promotes a valid draft with `jagt draft lint` and `jagt render`, and it
validates the promoted `AGENT_TASK v1` with `jagt lint`.
