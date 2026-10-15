import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

from conversation_store import ConversationStore, StorageError
from main import app


def test_cleanup_runs_without_requests_and_retries_storage_failure(monkeypatch, caplog):
    monkeypatch.setattr('conversation_store.RETENTION_INTERVAL_SECONDS', .001)

    async def run():
        retried = asyncio.Event()

        class Store(ConversationStore):
            attempts = 0

            async def delete_expired(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise StorageError('STORAGE_UNAVAILABLE')
                retried.set()
                return 0

        store = Store('postgresql://not-used')
        task = asyncio.create_task(store.cleanup_expired())
        try:
            await asyncio.wait_for(retried.wait(), 1)
            assert store.attempts >= 2
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())
    assert 'STORAGE_UNAVAILABLE' in caplog.text
    assert 'postgresql://' not in caplog.text


def test_lifespan_cancels_cleanup_before_closing_the_pool(monkeypatch):
    started = threading.Event()
    cancelled = threading.Event()
    closed = threading.Event()

    class Store(ConversationStore):
        async def delete_expired(self):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def close(self):
            assert cancelled.is_set()
            closed.set()

    monkeypatch.setattr('main.ConversationStore', Store)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://not-used')
    with TestClient(app):
        assert started.wait(1)
    assert closed.is_set()
