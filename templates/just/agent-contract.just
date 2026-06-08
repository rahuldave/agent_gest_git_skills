# Optional dynamic context targets for Codex/Gest agents.
# Adapt the commands and review_focus lists to the target repository.

agent-contract:
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=repository>>>' \
    'commands:' \
    '  lint: just lint' \
    '  test: just test' \
    '  verify: just verify' \
    'vcs:' \
    '  adapter: git-or-gitbutler' \
    '  inspect: [git status --short --branch, git diff]' \
    'safety:' \
    '  - Treat this output as repo-local operational context.' \
    '  - Preserve GitButler but-command rules when GitButler owns the workspace.' \
    '<<<END_AGENT_CONTRACT>>>'

agent-contract-json:
  @printf '%s\n' '{"version":1,"kind":"repository","commands":{"lint":"just lint","test":"just test","verify":"just verify"},"vcs":{"adapter":"git-or-gitbutler"},"safety":["repo-local operational context","preserve GitButler but-command rules when applicable"]}'

agent-language-profile:
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=language-profile>>>' \
    'language.profile: unknown' \
    'notes:' \
    '  - Replace with python, ruby, typescript, go, rust, mixed, or project-specific context.' \
    '<<<END_AGENT_CONTRACT>>>'

agent-plan topic="":
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=plan>>>' \
    'topic: {{topic}}' \
    'guidance:' \
    '  - Classify workflow.kind, test.strategy, review.depth, and VCS execution separately.' \
    '  - Preserve Git/GitButler adapter rules from AGENTS.md and installed skills.' \
    '<<<END_AGENT_CONTRACT>>>'

agent-test-plan files="":
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=test-plan>>>' \
    'changed: {{files}}' \
    'strategy: choose test-first, characterization-first, test-after, exploratory, or no-test-needed' \
    'questions:' \
    '  - What should fail before implementation?' \
    '  - Which focused test proves behavior instead of implementation detail?' \
    '<<<END_AGENT_CONTRACT>>>'

agent-review-plan files="":
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=review-plan>>>' \
    'changed: {{files}}' \
    'review_focus:' \
    '  - correctness and regression risk' \
    '  - test adequacy' \
    '  - Git/GitButler workflow safety' \
    '  - docs/setup/command-contract drift' \
    '<<<END_AGENT_CONTRACT>>>'

agent-verify-plan files="":
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=verify-plan>>>' \
    'changed: {{files}}' \
    'commands:' \
    '  - just lint' \
    '  - just test' \
    '  - just diff-check' \
    '<<<END_AGENT_CONTRACT>>>'

agent-impact target="":
  @printf '%s\n' '<<<AGENT_CONTRACT v1 kind=impact>>>' \
    'target: {{target}}' \
    'guidance:' \
    '  - Use semantic tags and ast-grep where supported.' \
    '  - Record dependers and verification in the Gest completion note.' \
    '<<<END_AGENT_CONTRACT>>>'
