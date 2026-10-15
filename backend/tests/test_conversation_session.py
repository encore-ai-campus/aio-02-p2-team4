from uuid import UUID
import pytest
from conversation_session import issue_session, verify_session


def test_session_roundtrip_and_expiry():
    token = issue_session('s' * 40, 1000)
    assert isinstance(verify_session(token, 's' * 40, 1001), UUID)
    for now in (999, 1000 + 30 * 86400):
        with pytest.raises(ValueError):
            verify_session(token, 's' * 40, now)


def test_session_rejects_tampering_and_missing_secret():
    token = issue_session('s' * 40, 1000)
    for changed, secret in ((token + 'x', 's' * 40), (token, 'x' * 40), (token, '')):
        with pytest.raises(ValueError):
            verify_session(changed, secret, 1001)
    with pytest.raises(ValueError):
        issue_session('', 1000)


def test_verified_session_exposes_its_original_expiry():
    from datetime import datetime, timezone
    from conversation_session import verify_session_details

    token = issue_session('s' * 40, 1000)
    owner, expires = verify_session_details(token, 's' * 40, 5000)
    assert owner == verify_session(token, 's' * 40, 5000)
    assert expires == datetime.fromtimestamp(1000 + 30 * 86400, timezone.utc)
    with pytest.raises(ValueError):
        verify_session_details(token + 'x', 's' * 40, 5000)
