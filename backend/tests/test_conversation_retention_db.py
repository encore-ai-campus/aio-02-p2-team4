"""실제 PostgreSQL의 임시 테이블에서만 만료·이관·연쇄 삭제를 검증합니다."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import ssl
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest

from conversation_contracts import ConversationCreate
from conversation_store import ConversationStore


async def check_retention_database(url):
    tls = ssl.create_default_context() if (urlsplit(url).hostname or '').endswith('.render.com') else None
    connection = await asyncpg.connect(url, ssl=tls, timeout=10, command_timeout=10)
    await connection.execute('SET search_path = pg_temp')
    transaction = connection.transaction()
    await transaction.start()

    class PinnedConnection:
        async def acquire(self):
            return connection

        async def release(self, acquired):
            assert acquired is connection

    # 실제 DSN은 저장소에 넘기지 않으며, 모든 연산은 같은 임시 스키마 연결로 고정합니다.
    store = ConversationStore('')
    store.pool = PinnedConnection()
    migrations = Path(__file__).parents[1] / 'migrations'
    now = datetime.now(timezone.utc)
    expired_owner, live_owner = uuid4(), uuid4()
    rows = [(uuid4(), expired_owner, 40, False), (uuid4(), expired_owner, 20, False),
            (uuid4(), uuid4(), 35, True), (uuid4(), live_owner, 5, False)]
    try:
        async with store.connection() as conn:
            # 임시 테이블은 같은 이름의 실제 서비스 테이블을 가립니다.
            initial = (migrations / '001_conversations.sql').read_text(encoding='utf-8')
            await conn.execute(initial.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
            for name in ('conversations', 'messages'):
                assert await conn.fetchval(
                    "SELECT to_regclass($1)::oid IN (SELECT oid FROM pg_class WHERE relnamespace=pg_my_temp_schema())", name)
            for identifier, owner, days, deleted in rows:
                await conn.execute(
                    'INSERT INTO conversations(id,owner_id,create_request_id,title,created_at,deleted_at) VALUES($1,$2,$3,$4,$5,$6)',
                    identifier, owner, uuid4(), 'Synthetic retention', now-timedelta(days=days), now if deleted else None)
                await conn.execute(
                    'INSERT INTO messages(id,conversation_id,sequence,request_id,role,content,status) VALUES($1,$2,1,$3,$4,$5,$6)',
                    uuid4(), identifier, uuid4(), 'user', 'Synthetic retention', 'completed')
            migration = (migrations / '002_conversation_expiry.sql').read_text(encoding='utf-8')
            await conn.execute(migration)
            await conn.execute(migration)
            expiries = await conn.fetch('SELECT expires_at FROM conversations WHERE owner_id=$1', expired_owner)
            assert all(row['expires_at'] == now-timedelta(days=10) for row in expiries)

        assert await store.delete_expired() == 3
        async with store.connection() as conn:
            assert await conn.fetchval('SELECT count(*) FROM conversations') == 1
            assert await conn.fetchval('SELECT count(*) FROM messages') == 1

        deadline = now+timedelta(days=2)
        payload = ConversationCreate(storageConsent=True, createRequestId=uuid4(), title='New conversation')
        created = await store.create(live_owner, payload, expires_at=deadline)
        assert (await store.create(live_owner, payload, expires_at=deadline)).id == created.id
        async with store.connection() as conn:
            assert await conn.fetchval('SELECT count(*) FROM conversations WHERE expires_at=$1', deadline) == 2
            await conn.execute('UPDATE conversations SET expires_at=clock_timestamp() WHERE id=$1', created.id)
        assert await store.delete_expired() == 1
        assert len((await store.list(live_owner)).items) == 1
        assert await store.delete_expired() == 0
        return {'temporary_tables_only': True, 'migration_repeated': True,
                'expired_conversations_deleted': 4, 'unexpired_preserved': True, 'messages_cascaded': True}
    finally:
        try:
            await transaction.rollback()
        finally:
            await connection.close()


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='TEST_DATABASE_URL is not configured')
def test_expiration_migration_and_cascade_in_postgresql():
    asyncio.run(check_retention_database(os.environ['TEST_DATABASE_URL']))
