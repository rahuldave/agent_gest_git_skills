setup:
  @echo "No repository-local dependencies to install. Ensure gest, but, gh, just, and ast-grep are available."

lint:
  scripts/check_repo.sh

static: lint

test:
  scripts/run_gitbutler_workflow_lab.sh
  scripts/run_tag_dependency_agent_dry_run.sh
  scripts/run_tag_dependency_typescript_lab.sh
  scripts/run_language_profile_labs.sh
  scripts/run_cx_examples_lab.sh

tag-dependency-dry-run:
  scripts/run_tag_dependency_agent_dry_run.sh

tag-dependency-live-lab:
  scripts/run_tag_dependency_typescript_lab.sh

language-profile-labs:
  scripts/run_language_profile_labs.sh

cx-examples-lab:
  scripts/run_cx_examples_lab.sh

workflow-lab:
  scripts/run_gitbutler_workflow_lab.sh

integration-live:
  scripts/run_gitbutler_github_integration_lab.sh

diff-check:
  scripts/check_repo.sh --diff

verify: lint test diff-check
