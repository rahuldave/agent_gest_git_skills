setup:
  @echo "No repository-local dependencies to install. Ensure git, gest, just, uv, rsync, and optional gh, but, ast-grep, direnv, cx are available."

lint:
  scripts/check_repo.sh

static: lint

test:
  scripts/run_gitbutler_workflow_lab.sh
  scripts/run_tag_dependency_agent_dry_run.sh
  scripts/run_tag_dependency_typescript_lab.sh
  scripts/run_language_profile_labs.sh
  scripts/run_cx_examples_lab.sh
  scripts/run_agentic_target_lab.sh
  scripts/run_agent_result_lab.sh

tag-dependency-dry-run:
  scripts/run_tag_dependency_agent_dry_run.sh

tag-dependency-live-lab:
  scripts/run_tag_dependency_typescript_lab.sh

language-profile-labs:
  scripts/run_language_profile_labs.sh

cx-examples-lab:
  scripts/run_cx_examples_lab.sh

agentic-target-lab:
  scripts/run_agentic_target_lab.sh

agent-result-lab:
  scripts/run_agent_result_lab.sh

agent-result-recursive-live-lab TRANSCRIPT_DIR:
  scripts/run_agent_result_recursive_live_lab.sh "{{TRANSCRIPT_DIR}}"

workflow-lab:
  scripts/run_gitbutler_workflow_lab.sh

integration-live:
  scripts/run_gitbutler_github_integration_lab.sh

diff-check:
  scripts/check_repo.sh --diff

verify: lint test diff-check
