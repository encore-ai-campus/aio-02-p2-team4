import asyncio
import pytest
from conversation_store import ConversationStore, StorageError


def test_missing_database_is_storage_error():
    async def run():
        with pytest.raises(StorageError, match='NOT_CONFIGURED'):
            await ConversationStore('').open()
    asyncio.run(run())


def test_db_acquisition_is_bounded_and_diagnostics_are_hidden():
    class SlowPool:
        async def acquire(self):
            await asyncio.sleep(10)
    async def run():
        store = ConversationStore('postgres://unused', timeout=.02)
        store.pool = SlowPool()
        with pytest.raises(StorageError, match='STORAGE_UNAVAILABLE'):
            async with store.connection():
                pass
    asyncio.run(run())


def test_delete_all_removes_only_owned_conversations():
    from contextlib import asynccontextmanager
    from uuid import uuid4
    calls = []

    class FakeConn:
        @asynccontextmanager
        async def transaction(self):
            yield self

        async def execute(self, sql, *args):
            calls.append((sql, args))
            return 'UPDATE 2'

    class FakePool:
        async def acquire(self):
            return FakeConn()

        async def release(self, connection):
            pass

    async def run():
        store = ConversationStore('postgres://unused')
        store.pool = FakePool()
        return await store.delete_all(uuid4())

    assert asyncio.run(run()) == 2
    assert len(calls) == 2
    assert 'DELETE FROM messages' in calls[0][0]
    assert 'deleted_at IS NULL' in calls[1][0]
    assert calls[0][1][0] == calls[1][1][0]
