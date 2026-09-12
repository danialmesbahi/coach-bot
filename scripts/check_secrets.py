"""Small pre-push guard, not a substitute for provider secret scanning.

Inspect staged content by default, or HEAD with --tracked (CI). Only file names
are reported: never echo credentials. Local .env values are checked when present.
"""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess


PATTERNS = (
    rb'gh[pousr]_[A-Za-z0-9]{30,}',
    rb'github_pat_[A-Za-z0-9_]{40,}',
    rb'\b[0-9]{8,12}:[A-Za-z0-9_-]{35}\b',
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
)


def forbidden_path(name):
    path = PurePosixPath(name)
    return (
        (path.name.startswith('.env') and not path.name.endswith('.example'))
        or path.suffix.lower() in {'.pem', '.key', '.dump', '.sqlitedb', '.sqlite', '.rar'}
        or any(part in {'artifacts', 'node_modules', '.next', '.venv'} or part.startswith('.visual') for part in path.parts)
    )


def sensitive_content(body, local_secrets=()):
    return any(re.search(pattern, body) for pattern in PATTERNS) or any(secret in body for secret in local_secrets)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    secrets = []
    for file in (Path('.env'), Path('.env.live')):
        if not file.exists():
            continue
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            value = value.strip().strip('\"\'')
            if sep and re.search(r'TOKEN|PASSWORD|SECRET|MERCHANT', key) and len(value) >= 12:
                secrets.append(value.encode())
    command = ['git', 'ls-tree', '-r', '--name-only', '-z', 'HEAD'] if args.tracked else ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z']
    names = subprocess.check_output(command).decode('utf-8').split('\0')
    bad = []
    for name in filter(None, names):
        ref = f'HEAD:{name}' if args.tracked else f':{name}'
        try:
            body = subprocess.check_output(['git', 'show', ref], stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # Gitlinks/submodules are not auditable file content; require review.
            bad.append(name)
            continue
        if forbidden_path(name) or sensitive_content(body, secrets):
            bad.append(name)
    if bad:
        print('BLOCKED: review these paths; credential values intentionally hidden:')
        print('\n'.join(bad))
        return 1
    print('PASS: no blocked paths or recognized/local credentials in reviewed Git content')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
