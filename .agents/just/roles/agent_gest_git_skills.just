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

# Set up this worktree from the main checkout: copy the files of .worktreeinclude, link the paths of .worktreelink
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

# A fresh agent checks that each new behavior has a test that checks a result. Prints the packet
test-review:
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
