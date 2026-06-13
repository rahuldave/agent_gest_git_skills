# AGENT_TASK_DRAFT v1 Workflow

`AGENT_TASK_DRAFT v1` is for stochastic task design. Use it when a subagent is
asked to propose the right bounded `AGENT_TASK v1`, not when the work is
already deterministic enough to render directly.

A draft is not executable. It is a proposal envelope that must be validated,
reviewed, approved, promoted through deterministic tooling, and then executed
by a different subagent as a final `AGENT_TASK v1`.

## When To Use Drafts

Use a draft when the task shape itself needs judgment, such as:

- turning a vague investigation request into a bounded implementation task
- choosing a useful exploratory analysis target for a dataset
- proposing verification steps for a set of changed files

Do not use a draft when a project script can already emit a stable
`AGENT_TASK v1` with known inputs, outputs, allowed actions, and verification.
Render the final task directly in that case.

## Workflow

1. The parent asks a subagent to design the task.
2. The design subagent returns one `AGENT_RESULT v1` for the proposal job and
   one `AGENT_TASK_DRAFT v1` envelope after it.
3. The parent validates the draft shape and policy with `jagt draft lint`.
4. The parent rejects, asks for revision, records approval under active policy,
   or asks the user for approval.
5. The parent promotes approved fields with deterministic tooling. The MVP path
   is `jagt render` followed by `jagt lint`.
6. A different execution subagent receives the promoted `AGENT_TASK v1`.

The proposal subagent must not execute its own proposed work.

## Approval And Authority

All v1 drafts must include `approval.required: true`. A draft cannot claim that
it is already approved, cannot bypass sandboxing or VCS rules, and cannot
expand authority beyond the source request, active repo policy, or current
approval state.

If the parent cannot safely approve under existing policy, it asks the user.

## Contract Delivery

Fresh subagents may not inherit parent memory. Provide the draft contract
through one of these paths:

- repo `AGENTS.md`
- installed skill references such as
  `.agents/skills/gtw/references/just_command_contract.md`
- a copied excerpt in the parent delegation prompt
- a fixture-local `AGENTS.md` in labs

`just agent-task-draft-lab` includes a fresh-context fixture to prove the
contract can be supplied without hidden parent memory.

## Verification

Run:

```bash
just agent-task-draft-lab
```

The lab validates a result-plus-draft pair, rejects malformed and unsafe
drafts, rejects direct draft execution, promotes a valid draft with
`jagt draft lint` and `jagt render`, and validates the promoted
`AGENT_TASK v1` with `jagt lint`.
