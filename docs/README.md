# Documentation map

Start with one document:

- `TUTORIAL.md`: a GitHub tutorial for a new user, step by step, with the same result each time.

Read the other documents only when you need reference material:

- `g_commands_cheatsheet.md`: a short guide to the `g*` skills.
- `integration_delivery_workflow.md`: integration targets, independent review, CI,
  release milestones, issue completion and the record of where an install came from.
- `gest_codex_workflow.md`: the advanced workflow for agents.
- `tag_dependency_workflow.md`: how to classify tags, and how to check dependencies with ast-grep.
- `protocol_flows.md`: a guide to the agentic packet flow of the Justfile, and a map of its labs.
  It covers `AGENT_TASK v1`, `AGENT_RESULT v1`, recursive results and
  `AGENT_TASK_DRAFT v1`, with the standard `g*` skills.
- `../notes/live_protocol_flow_transcript_2026-06-14.md`: the transcript of a real run of the
  protocol between a parent agent and a subagent. It shows validation failures, corrections, a
  recursive refusal, the promotion of a draft and the final output of the validator.
- `just_command_contract.md`: a pointer. The command contract of the Justfile is in
  the `just` skill of jnterfaces.
- `agent_task_draft_workflow.md`: a guide for the user. A subagent proposes a task that is not
  fixed in advance. You approve it, `jagt` promotes it the same way each time, and a fresh
  subagent gets the contract.
- `cx_incremental_pipelines.md`: a pointer. The `cx` guidance is in the
  `cx` skill of jnterfaces.
- `gsu_typescript_hello_world.md`: a small example of setup.
- `gsu_language_profile_labs.md`: live local labs that run setup from start to end with the
  setup and profile templates for Python, TypeScript, Go and Rust. The profiles are command
  contracts, and they are not skills for how to reason in a language.

The beginner tutorial is the source of truth for the review shapes that the package supports:

1. ordinary git branch PR
2. ordinary git multi-commit PR
3. stacked PRs with plain git for dependent slices
4. physical git worktrees for independent slices

The tutorial also classifies tags and checks dependencies with ast-grep, with the same result each
time. Every review shape uses plain git and `gh`.

For the agentic packet flow, read `protocol_flows.md` and then the live transcript. They explain the
protocol that the static labs of `just protocol-flow-labs` check. They also explain the validator of
the recursive transcript, which runs only when you ask for it.
