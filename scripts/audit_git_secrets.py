"""Read-only credential audit. Reports paths/categories, never matched values.

Checks candidate/index files and all reachable Git blobs and commit messages.
Configured local credentials are read only for in-memory exact comparisons.
This is a targeted credential-pattern audit, not a claim of perfect detection.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def git_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GIT_TRACE', 'GCM_TRACE')) and k not in ('GIT_CURL_VERBOSE', 'GCM_DEBUG')}
    env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    return env


def git(*args):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', *args], cwd=ROOT,
                            env=git_env(), capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('A required Git audit read failed; no clean verdict is possible.')
    return result.stdout


PATTERNS = {
    'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github_credential': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})'),
    'aws_access_key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'jwt_credential': re.compile(rb'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b'),
    'signed_or_token_url': re.compile(rb'[?&](?:X-Amz-(?:Signature|Credential|Security-Token)|access_token|refresh_token|token)=([^\s"\x27&<>]+)', re.I),
    'literal_credential': re.compile(rb'\b(?:EARTHDATA_TOKEN|EDL_PASSWORD|GITHUB_TOKEN|GH_TOKEN|AWS_SECRET_ACCESS_KEY)["\x27]?\s*[:=]\s*["\x27]([^ \t\r\n"\x27=+()][^"\x27\r\n]{5,})["\x27]', re.I),
    'env_credential': re.compile(rb'^[ \t]*(?:EARTHDATA_TOKEN|EDL_PASSWORD|GITHUB_TOKEN|GH_TOKEN|AWS_SECRET_ACCESS_KEY)[ \t]*=[ \t]*([^ \t\r\n#]+)[ \t]*$', re.I | re.M),
}


def placeholder(value):
    value = value.strip(b'"\x27').lower()
    return (value in {b'', b'x', b'...', b'redacted', b'secret', b'token', b'password', b'configured', b'signed', b'false', b'true'}
            or value.startswith((b'fake', b'test', b'example', b'placeholder', b'synthetic', b'sensitive-'))
            or b'redacted' in value or b'${' in value or b'<' in value)


def audit():
    secrets = []
    # Both sources are checked: an empty inherited variable must not hide a
    # credential still present in the ignored local .env file.
    for configured in (dotenv_values(ROOT / '.env'), os.environ):
        for key, value in configured.items():
            if value and re.search(r'(?:PASSWORD|TOKEN|SECRET|EDL_USERNAME|API_KEY)', key, re.I):
                if value.lower() in {'true', 'false'}:
                    continue
                if len(value) >= 6:
                    for variant in (value, quote(value, safe=''), json.dumps(value)[1:-1]):
                        encoded = variant.encode()
                        if encoded not in secrets:
                            secrets.append(encoded)
    findings = set()

    def scan(chunk, location):
        if any(value in chunk for value in secrets):
            findings.add((location, 'configured_local_credential_value'))
        for category, pattern in PATTERNS.items():
            for match in pattern.finditer(chunk):
                if match.groups() and placeholder(match.group(1)):
                    continue
                # Reviewed invalid bearer marker in this unit-test fixture only.
                # Exact configured values and high-confidence token formats above
                # remain checked independently, including inside test files.
                if (category == 'literal_credential' and location.endswith('scripts/test_password_redirect_unit.py')
                        and match.group(0).upper().startswith(b'EARTHDATA_TOKEN')
                        and re.fullmatch(rb'[A-Z_ -]+', match.group(1))
                        and any(word in match.group(1).lower() for word in (b'not', b'never', b'forbidden', b'ignore', b'wrong'))):
                    continue
                findings.add((location, category))

    def stream_scan(stream, size, location):
        tail = b''
        while size:
            chunk = stream.read(min(size, 1024 * 1024))
            if not chunk:
                raise RuntimeError('A credential audit input was truncated.')
            scan(tail + chunk, location)
            tail = chunk[-16384:]
            size -= len(chunk)

    candidates = sorted(set(p.decode() for p in git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if p))
    total = 0
    for name in candidates:
        path = ROOT / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            findings.add((name, 'unsafe_source_path'))
            continue
        if name != '.env.example' and (Path(name).name.startswith('.env') or name.startswith(('artifacts/', '.aws/', '.ssh/'))):
            findings.add((name, 'sensitive_or_cached_file_in_git_candidates'))
        size = path.stat().st_size
        if size > 20 * 1024 * 1024:
            findings.add((name, 'unexpected_large_file'))
        with path.open('rb') as stream:
            stream_scan(stream, size, name)
        total += size

    records = git('rev-list', '--objects', '--all').decode().splitlines()
    for record in git('ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        _, oid, stage = metadata.decode().split()
        if stage != '0':
            raise RuntimeError('Unresolved index entries prevent a clean audit.')
        records.append(oid + ' index:' + name.decode())
    count = index_count = 0
    if records:
        process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT, env=git_env(),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            for record in records:
                oid, _, name = record.partition(' ')
                process.stdin.write((oid + '\n').encode()); process.stdin.flush()
                header = process.stdout.readline().decode().split()
                if len(header) != 3:
                    raise RuntimeError('Git object audit failed.')
                kind, size = header[1], int(header[2])
                location = name if name.startswith('index:') else 'history:' + (name or oid)
                if kind == 'blob':
                    stream_scan(process.stdout, size, location)
                    if name.startswith('index:'):
                        index_count += 1
                    else:
                        count += 1
                else:
                    content = process.stdout.read(size)
                    if kind in ('commit', 'tag'):
                        scan(content.partition(b'\n\n')[2], location)
                if process.stdout.read(1) != b'\n':
                    raise RuntimeError('Git object boundary audit failed.')
        finally:
            process.stdin.close(); process.wait(timeout=10)
    history_count = int(git('rev-list', '--all', '--count').strip() or b'0')
    report = {'status': 'clean' if not findings else 'STOP: findings require review',
              'candidate_files': len(candidates), 'candidate_bytes': total,
              'reachable_commits': history_count, 'history_blobs_scanned': count,
              'index_blobs_scanned': index_count,
              'configured_credential_comparison': bool(secrets),
              'findings': [{'location': location, 'category': category} for location, category in sorted(findings)],
              'scope': 'All candidate/index files, reachable history blobs and commit/tag messages; configured credential values and high-confidence credential patterns. No matched values are reported.'}
    return report


if __name__ == '__main__':
    try:
        report = audit()
        print(json.dumps(report, indent=2))
        sys.exit(0 if report['status'] == 'clean' else 1)
    except Exception:
        print(json.dumps({'status': 'STOP: credential audit could not complete; no clean verdict claimed'}))
        sys.exit(2)
