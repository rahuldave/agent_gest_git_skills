# The recipes of the tasker role: Git worktrees for the g* skills. just install imports this file in a project that
# jnterfaces started. The script is in the gtw skill: .agents/skills/gtw/scripts/worktree.py.

jn_worktree := "uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gtw/scripts/worktree.py"

# Print the tasker variant: git (a branch in the main checkout) or gitwt (each task in its own worktree)
tasker-mode:
    @{{jn_worktree}} mode

# Make branch NAME from BASE (default main) in ../<repo>.worktrees/NAME, set it up, then run just setup. --no-setup skips just setup
[positional-arguments]
worktree-new NAME *args:
    @{{jn_worktree}} new "$@"

# Set up this worktree from the main checkout: copy the files of .worktreeinclude, link the paths of .worktreelink, seed the build folders of .worktreeseed
worktree-sync:
    @{{jn_worktree}} sync

# List the worktrees: clean or dirty, merged or not, and whether each is ready to prune
[positional-arguments]
worktrees *args:
    @{{jn_worktree}} list "$@"

# Remove the worktrees that are clean, merged and idle for 2 hours, with git worktree remove and no --force. Takes --dry-run and --min-age HOURS
[positional-arguments]
worktrees-prune *args:
    @{{jn_worktree}} prune "$@"

# The agentic targets of the commit gates. Each prints an AGENT_TASK v1 packet. Give the packet to a fresh agent,
# which returns an AGENT_RESULT v1 packet; the record of the result lets a commit through the gate.
jn_target := "uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gcm/scripts/agentic_target.py render"

# An adversarial review of the changes by a fresh agent, on the strongest model. Prints the packet
review:
    @{{jn_target}} review

# Run the added and changed test files on the parent commit; test-review runs it first and its packet holds the result
test-parent:
    @uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gcm/scripts/test_parent.py

# A fresh agent checks that each new behavior has a test that checks a result. Prints the packet
test-review: test-parent
    @{{jn_target}} test-review

# A fresh agent writes or changes the docs that the change affects, in AREA when given. Prints the packet
[positional-arguments]
update-docs *args:
    @{{jn_target}} update-docs "$@"

# A fresh agent applies the writing guide to the changed pages and docstrings, under PATH when given. Prints the packet
[positional-arguments]
prose *args:
    @{{jn_target}} prose "$@"

# A fresh agent runs the app through a flow in a browser and takes screenshots. Prints the packet
[positional-arguments]
visual-check *args:
    @{{jn_target}} visual-check "$@"

# A fresh agent draws a diagram of a part of the code, for a doc or for you. Prints the packet
[positional-arguments]
visualize *args:
    @{{jn_target}} visualize "$@"

jn_record := "uv run --no-project --quiet --no-python-downloads --python '>=3.9' --with pyyaml python .agents/skills/gcm/scripts/record_result.py"

# Write the record of the AGENT_RESULT v1 in FILE, for a harness whose fresh agents stop without a record hook
[positional-arguments]
record target file:
    @{{jn_record}} record "$1" "$2"

# Let the worktree tree through without the record of TARGET, for REASON. The agent hooks ask you first
[positional-arguments]
record-skip target +reason:
    @{{jn_record}} skip "$@"

jn_gate := "uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gcm/scripts/commit_gate.py"

# JN_CI_BASE selects the verified PR base for an existing-topic push; the hook keeps its pushed head.
# Without selection use the push range; new history checks all commits. Outside a push use JN_CI_BASE, else the base
# branch on origin. ci-gate is a step of just check and of just ci, so CI runs only steps of just check. It skips
# merge commits, commits by GitHub bots, and commits from before the gate, and names each one.

# Check that each commit since the base branch has the trailer of the commit gate that names its change
ci-gate:
    @{{jn_gate}} --trailers
    jlog step ci-gate

# The PR of each branch has the branch below it as its base, and the bottom one has BASE. A branch with no upstream,
# or ahead of its upstream, is pushed first, never with force.

# Open the PRs of a stack in order, from the bottom branch up, on the branch below each. Takes --dry-run first
[positional-arguments]
stack-prs *args:
    @uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gcm/scripts/stack_prs.py "$@"

# The release tag comes from the commits since the last tag. Run it after the post-merge CI passed. The CI starter
# release.yml runs it on each push to main. When the profiles give a lower version, it writes the bump into their
# version files, commits it as chore(release): vX.Y.Z, and pushes the commit and the tag together. It reads the TOML
# files with tomllib, so it asks for Python 3.11 or later.

# Tag the next release vX.Y.Z by semver, writing the version files first when they are lower. Takes --dry-run first
[positional-arguments]
release *args:
    @uv run --no-project --quiet --no-python-downloads --python '>=3.11' python .agents/skills/gpa/scripts/release_tag.py "$@"

# The step release-check of just check, so CI checks it through just check. It needs no network and no remote. The
# index of jnterfaces sets jlog as the shell, and the last line records the step; where the role is not installed,
# the index has a no-op release-check.

# Fail when the profiles give different versions, or a version below the last tag. A branch keeps the version of the tag
release-check:
    uv run --no-project --quiet --no-python-downloads --python '>=3.9' python .agents/skills/gpa/scripts/release_tag.py --check
    jlog step release-check
