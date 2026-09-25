# Working on the Gest Git skills

Use `.agents/skills/gtw/SKILL.md` to track substantial work and
`docs/integration_delivery_workflow.md` for branch, review, CI and delivery rules.
This repository is the reusable source; target projects retain their own runtime
invariants. Preserve adapters and the distinction between GitButler stack
curation and physical worktrees for parallel writers.

- Default/integration branch: `main`. Work on temporary `codex/*` topic branches
  and submit reviewed PRs to `main`, unless the user selects another target.
- Canonical policy: `docs/gest_codex_workflow.md` and
  `docs/integration_delivery_workflow.md`. Keep skill-local reference copies and
  the GSU copy of `AGENTS.template.md` synchronized.
- Serialize Gest operations; it maintains graphs automatically. No export step.
- Use independent adversarial review for executable and reusable policy changes.
- Run `just lint`, relevant focused labs and installer regression tests. Consult
  `Justfile` for the full local suite and automatic CI contract. Authenticated
  live GitHub labs require explicit opt-in and are not ordinary PR checks.
- Validate the skill package and scratch installation before delivery.
- PR integration publishes source only. A tagged release is a separate explicit
  request; never claim installed copies updated merely because source merged.
- Preserve settings/instructions when installing into another repository; record
  exact source revision. Stop only owned test processes and remove only owned
  temporary paths.
