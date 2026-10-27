#!/usr/bin/env python3
"""Check links from shipped files into the jnterfaces skills.

Each paragraph that names a jnterfaces skill path needs a fallback for a target without jnterfaces.
With --jnterfaces DIR, each named path must exist in that checkout, as a file or a folder.
"""
import argparse
from pathlib import Path
import re
import sys

LINK = re.compile(r'(?<![A-Za-z0-9_./-])(?:\.agents/)?skills/(?:just|jagt-protocol|cx)(?![A-Za-z0-9_-])(?:/[A-Za-z0-9_./-]*)?')
FALLBACK = re.compile(r'jnterfaces is (?:not )?installed|(?:when|if) it is (?:not )?installed', re.I)


def problems(path, text, jnterfaces=None):
    found = []
    for paragraph in re.split(r'\n\s*\n', text):
        links = LINK.findall(paragraph)
        if not links:
            continue
        flat = ' '.join(paragraph.split())
        if 'jnterfaces' not in flat or not FALLBACK.search(flat):
            found.append(f'{path}: a link into jnterfaces has no fallback in its paragraph: {links[0]}')
        if jnterfaces is not None:
            for link in links:
                link = link.rstrip('./')
                if not link.startswith('.agents/'):
                    link = '.agents/' + link
                if '..' in Path(link).parts or not (jnterfaces / link).exists():
                    found.append(f'{path}: link to a path that jnterfaces does not have: {link}')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--jnterfaces', type=Path)
    args = parser.parse_args()
    if args.jnterfaces is not None and not (args.jnterfaces / 'skill-package.json').is_file():
        print(f'No jnterfaces package at {args.jnterfaces}', file=sys.stderr)
        return 1
    found = [line for path in args.files for line in problems(path, path.read_text(), args.jnterfaces)]
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
