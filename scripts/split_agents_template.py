"""Split AGENTS.template.md into the two files of the parts of the tasker role.

The jnterfaces installer writes AGENTS.starter.md once, as the start of a new AGENTS.md, and the project fills it in.
It writes AGENTS.instructions.md as the own file .agents/instructions/tasker.md, and a line in AGENTS.md points to
it. AGENTS.template.md stays whole for one release, for installers from before the parts and for gsu.

    uv run --no-project python scripts/split_agents_template.py          write the two files
    uv run --no-project python scripts/split_agents_template.py --check  fail when they differ from the template
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTEXT, NEXT = '## Project Context\n', '## Tag And Dependency Impact\n'
# The sentences of the project context that ask the project to fill it in. The rest of its paragraph are rules.
FILL_IN = ('Replace this section with project-specific invariants, runtime commands, and\n'
           'verification commands. Declare the default branch, persistent integration\n'
           'branches, default target for this work, required CI checks and release triggers.\n')


def split(text):
    head, rest = text.split(CONTEXT, 1)
    context, tail = rest.split(NEXT, 1)
    facts, paragraph = context.split('\n\n', 1)
    if not paragraph.startswith(FILL_IN):
        raise SystemExit('The project context of AGENTS.template.md does not start its paragraph as expected')
    rules = paragraph[len(FILL_IN):].strip() + '\n'
    starter = f'{head.splitlines()[0]}\n\n{CONTEXT}{facts}\n\n{FILL_IN}'
    instructions = f'{head}## Branches And Review\n\n{rules}\n\n{NEXT}{tail}'
    return starter, instructions


def main():
    starter, instructions = split((ROOT / 'AGENTS.template.md').read_text())
    files = {'AGENTS.starter.md': starter, 'AGENTS.instructions.md': instructions}
    if '--check' in sys.argv:
        stale = [name for name, text in files.items()
                 if not (ROOT / name).is_file() or (ROOT / name).read_text() != text]
        if stale:
            raise SystemExit(f'{", ".join(stale)} differ from AGENTS.template.md; run '
                             f'uv run --no-project python scripts/split_agents_template.py')
        return
    for name, text in files.items():
        (ROOT / name).write_text(text)


if __name__ == '__main__':
    main()
