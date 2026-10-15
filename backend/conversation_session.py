"""익명 대화 소유권의 서명과 검증을 제공합니다."""
import base64
import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID, uuid4

SESSION_SECONDS = 30 * 86400


def _key(secret: str) -> bytes:
    if len(secret) < 32:
        raise ValueError('NOT_CONFIGURED')
    return secret.encode()


def issue_session(secret: str, now: int) -> str:
    payload = f'{uuid4()}.{now}.{now + SESSION_SECONDS}'
    signature = hmac.new(_key(secret), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f'{payload}.{signature}'.encode()).decode().rstrip('=')


def verify_session_details(token: str, secret: str, now: int) -> tuple[UUID, datetime]:
    key = _key(secret)
    try:
        if len(token) > 256 or not token or '=' in token:
            raise ValueError()
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True).decode('ascii')
        owner, issued, expires, signature = raw.split('.')
        payload = f'{owner}.{issued}.{expires}'
        expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        if not int(issued) <= now < int(expires) or int(expires) - int(issued) != SESSION_SECONDS:
            raise ValueError()
        return UUID(owner), datetime.fromtimestamp(int(expires), timezone.utc)
    except Exception:
        raise ValueError('SESSION_INVALID') from None


def verify_session(token: str, secret: str, now: int) -> UUID:
    return verify_session_details(token, secret, now)[0]
