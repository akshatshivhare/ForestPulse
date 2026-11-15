"""Synthetic secret fixtures in isolated temporary Git repositories only."""
import json
from pathlib import Path
import subprocess

import pytest
from scripts import audit_git_secrets as audit


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    def git(*args):
        result = subprocess.run(['git', *args], cwd=tmp_path, env=audit.git_env(), capture_output=True, timeout=20)
        assert result.returncode == 0
        return result
    git('init', '-b', 'main')
    git('config', 'user.name', 'ForestPulse Test')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'commit.gpgsign', 'false')
    hooks = tmp_path / 'empty-hooks'; hooks.mkdir()
    git('config', 'core.hooksPath', str(hooks))
    (tmp_path / '.gitignore').write_text('.env\nempty-hooks/\n')
    (tmp_path / 'README.md').write_text('Harmless synthetic test repository.\n')
    return tmp_path, git


def test_empty_env_template_does_not_consume_next_line():
    assert not audit.PATTERNS['env_credential'].search(b'EARTHDATA_TOKEN=\nHARMONY_PROCESSING_ENABLED=false\n')
    assert not audit.PATTERNS['literal_credential'].search(b'EDL_PASSWORD=' + b"' + value + '")


def test_strong_patterns_detect_constructed_synthetic_tokens():
    # Construct in memory so no credential-shaped token is embedded in source.
    token = b'ghp_' + b'A' * 40
    key_header = b'-----BEGIN ' + b'PRIVATE KEY-----'
    assert audit.PATTERNS['github_credential'].search(token)
    assert audit.PATTERNS['private_key'].search(key_header)


def test_clean_repository_and_ignored_credentials(repository):
    root, _ = repository
    (root / '.env').write_text('EDL_PASSWORD=synthetic-password-for-tests\n')
    result = audit.audit()
    assert result['status'] == 'clean' and result['reachable_commits'] == 0
    assert result['findings'] == []


def test_exact_local_values_are_checked_even_when_environment_is_empty(repository, monkeypatch):
    root, _ = repository
    value = 'synthetic-password-for-tests'
    monkeypatch.setenv('EDL_PASSWORD', '')
    (root / '.env').write_text('EDL_PASSWORD=' + value + '\n')
    (root / 'README.md').write_text(value)
    result = audit.audit()
    assert any(f['category'] == 'configured_local_credential_value' for f in result['findings'])
    assert value not in json.dumps(result)


def test_reachable_history_is_scanned_after_worktree_is_clean(repository):
    root, git = repository
    token = 'ghp_' + 'A' * 40
    (root / 'README.md').write_text(token)
    git('add', '.')
    git('commit', '-m', 'Synthetic audit fixture')
    (root / 'README.md').write_text('Clean current worktree.\n')
    git('add', '.')
    git('commit', '-m', 'Synthetic fixture update')
    result = audit.audit()
    assert result['reachable_commits'] == 2
    assert any(f['location'].startswith('history:') and f['category'] == 'github_credential' for f in result['findings'])
    assert token not in json.dumps(result)


def test_staged_snapshot_is_scanned_independently_of_worktree(repository):
    root, git = repository
    token = 'ghp_' + 'B' * 40
    (root / 'README.md').write_text(token)
    git('add', '.')
    (root / 'README.md').write_text('Harmless working file; index differs.\n')
    result = audit.audit()
    assert result['index_blobs_scanned'] >= 1
    assert any(f['location'] == 'index:README.md' and f['category'] == 'github_credential' for f in result['findings'])
    assert token not in json.dumps(result)
