from fastapi.testclient import TestClient
from main import app


def test_storage_status_and_consent(monkeypatch):
    monkeypatch.setenv('CONVERSATION_SESSION_SECRET','s'*40)
    monkeypatch.setenv('DATABASE_URL','postgresql://unused/db')
    with TestClient(app) as client:
        assert client.get('/api/conversations/status').json() == {'configured':True,'sessionAvailable':True}
        assert client.post('/api/conversations/session',json={'storageConsent':False}).status_code == 422
        response = client.post('/api/conversations/session',json={'storageConsent':True})
        assert response.status_code == 200
        token = response.json()['token']
        assert client.post('/api/conversations/session',headers={'x-ton-session':token},json={'storageConsent':True}).json()['token'] == token
        assert client.get('/api/conversations').status_code == 401
        assert client.get('/api/conversations',headers={'x-ton-session':'invalid'}).status_code == 401


def test_storage_errors_do_not_expose_secrets(monkeypatch):
    monkeypatch.setenv('CONVERSATION_SESSION_SECRET','')
    monkeypatch.setenv('DATABASE_URL','postgresql://private:secret@unused/db')
    with TestClient(app) as client:
        response=client.post('/api/conversations/session',json={'storageConsent':True})
        assert response.status_code == 503
        assert 'private' not in response.text and 'secret' not in response.text
        assert client.post('/api/conversations',content='x'*524289).status_code == 413


def test_bulk_delete_requires_session_and_never_exposes_secrets(monkeypatch):
    monkeypatch.setenv('CONVERSATION_SESSION_SECRET','s'*40)
    monkeypatch.setenv('DATABASE_URL','postgresql://private:secret@unused/db')
    with TestClient(app) as client:
        assert client.delete('/api/conversations').status_code == 401
        token = client.post('/api/conversations/session',json={'storageConsent':True}).json()['token']
        failed = client.delete('/api/conversations',headers={'x-ton-session':token})
        assert failed.status_code == 503
        assert 'private' not in failed.text and 'secret' not in failed.text


def test_creation_uses_signed_session_expiry_instead_of_another_thirty_days(monkeypatch):
    from datetime import datetime, timezone
    from uuid import uuid4
    from conversation_contracts import Conversation
    from conversation_session import issue_session

    recorded = []

    class Store:
        url = ''

        async def close(self):
            pass

        async def create(self, owner, payload, *, expires_at):
            recorded.append((owner, expires_at))
            return Conversation(id=uuid4(), title=payload.title,
                                createdAt=datetime.now(timezone.utc), updatedAt=datetime.now(timezone.utc))

    monkeypatch.setattr('main.ConversationStore', lambda url: Store())
    monkeypatch.setattr('conversation_api.time.time', lambda: 5000)
    monkeypatch.setenv('CONVERSATION_SESSION_SECRET', 's' * 40)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://unused/db')
    token = issue_session('s' * 40, 1000)
    with TestClient(app) as client:
        response = client.post('/api/conversations', headers={'x-ton-session': token}, json={
            'storageConsent': True, 'createRequestId': str(uuid4()), 'title': 'Retention test',
        })
    assert response.status_code == 200
    assert recorded[0][1] == datetime.fromtimestamp(1000 + 30 * 86400, timezone.utc)
