from scripts.check_secrets import forbidden_path, sensitive_content


def test_pre_push_guard_blocks_secrets_but_keeps_examples():
    assert forbidden_path('.env.live')
    assert forbidden_path('web/.env.local')
    assert forbidden_path('artifacts/session.json')
    assert not forbidden_path('.env.live.example')
    assert sensitive_content(b'ghp_' + b'a' * 36)
    assert sensitive_content(b'123456789:' + b'a' * 35)
    assert sensitive_content(b'password=known-local-secret', [b'known-local-secret'])
    assert not sensitive_content(b'TOKEN=replace-me')
