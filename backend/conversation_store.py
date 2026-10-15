"""소유권 조건과 짧은 제한 시간을 적용하는 PostgreSQL 저장소입니다."""
import asyncio
import base64
import json
import logging
import ssl
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4
import asyncpg
from conversation_contracts import Conversation, ConversationCreate, ConversationPage, MessageCreate, MessagePage, StoredMessage

RETENTION_INTERVAL_SECONDS = 3600
logger = logging.getLogger(__name__)


class StorageError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def conversation(row):
    return Conversation(id=row['id'], title=row['title'], createdAt=row['created_at'], updatedAt=row['updated_at'])


def message(row):
    return StoredMessage(id=row['id'], sequence=row['sequence'], requestId=row['request_id'], role=row['role'], content=row['content'], status=row['status'], snapshot=json.loads(row['snapshot']) if row['snapshot'] else None, createdAt=row['created_at'])


def decode_cursor(cursor: str):
    try:
        if len(cursor) > 256:
            raise ValueError()
        stamp, identifier = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        stamp = datetime.fromisoformat(stamp)
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp, UUID(identifier)
    except Exception:
        raise StorageError('INVALID_REQUEST') from None


class ConversationStore:
    def __init__(self, url: str, timeout: float = 3):
        self.url = url
        self.timeout = timeout
        self.pool = None
        self._lock = asyncio.Lock()

    async def open(self):
        if not self.url:
            raise StorageError('NOT_CONFIGURED')
        async with self._lock:
            if self.pool is None:
                hostname = urlsplit(self.url).hostname or ''
                tls = ssl.create_default_context() if hostname.endswith('.render.com') else None
                self.pool = await asyncpg.create_pool(self.url, min_size=0, max_size=4, timeout=self.timeout, command_timeout=self.timeout, ssl=tls)

    async def close(self):
        if self.pool:
            try:
                await asyncio.wait_for(self.pool.close(), self.timeout)
            except TimeoutError:
                self.pool.terminate()
            self.pool = None

    @asynccontextmanager
    async def connection(self):
        try:
            async with asyncio.timeout(self.timeout):
                if self.pool is None:
                    await self.open()
                connection = await self.pool.acquire()
                try:
                    yield connection
                finally:
                    await self.pool.release(connection)
        except StorageError:
            raise
        except Exception:
            raise StorageError('STORAGE_UNAVAILABLE') from None

    async def delete_expired(self):
        async with self.connection() as conn:
            result = await conn.execute('DELETE FROM conversations WHERE expires_at <= clock_timestamp()')
            return int(result.rsplit(' ', 1)[-1])

    async def cleanup_expired(self):
        while True:
            try:
                await self.delete_expired()
            except StorageError as error:
                logger.warning('Conversation expiry cleanup unavailable code=%s', error.code)
            await asyncio.sleep(RETENTION_INTERVAL_SECONDS)

    async def create(self, owner: UUID, payload: ConversationCreate, *, expires_at: datetime):
        async with self.connection() as conn:
            async with conn.transaction():
                await conn.execute('UPDATE conversations SET expires_at=$2 WHERE owner_id=$1 AND expires_at>$2', owner, expires_at)
                row = await conn.fetchrow('INSERT INTO conversations(id,owner_id,create_request_id,title,expires_at) VALUES($1,$2,$3,$4,$5) ON CONFLICT(owner_id,create_request_id) DO NOTHING RETURNING *', uuid4(), owner, payload.createRequestId, payload.title, expires_at)
                if row is None:
                    row = await conn.fetchrow('SELECT * FROM conversations WHERE owner_id=$1 AND create_request_id=$2', owner, payload.createRequestId)
                    if row['deleted_at'] is not None:
                        raise StorageError('NOT_FOUND')
                    if row['title'] != payload.title:
                        raise StorageError('IDEMPOTENCY_CONFLICT')
                return conversation(row)

    async def list(self, owner: UUID, cursor: str | None = None):
        boundary = decode_cursor(cursor) if cursor else None
        async with self.connection() as conn:
            rows = await conn.fetch('SELECT * FROM conversations WHERE owner_id=$1 AND deleted_at IS NULL AND ($2::timestamptz IS NULL OR (updated_at,id)<($2,$3::uuid)) ORDER BY updated_at DESC,id DESC LIMIT 31', owner, boundary[0] if boundary else None, boundary[1] if boundary else None)
            items = [conversation(row) for row in rows[:30]]
            next_cursor = base64.urlsafe_b64encode(json.dumps([items[-1].updatedAt.isoformat(), str(items[-1].id)]).encode()).decode().rstrip('=') if len(rows) > 30 else None
            return ConversationPage(items=items, nextCursor=next_cursor)

    async def get(self, owner: UUID, id: UUID, before: int | None = None):
        if before is not None and (before < 1 or before > 2147483647):
            raise StorageError('INVALID_REQUEST')
        async with self.connection() as conn:
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                row = await conn.fetchrow('SELECT * FROM conversations WHERE id=$1 AND owner_id=$2 AND deleted_at IS NULL', id, owner)
                if row is None:
                    raise StorageError('NOT_FOUND')
                rows = await conn.fetch('SELECT * FROM messages WHERE conversation_id=$1 AND ($2::int IS NULL OR sequence<$2) ORDER BY sequence DESC LIMIT 101', id, before)
                selected = list(reversed(rows[:100]))
                page = MessagePage(conversation=conversation(row), messages=[message(item) for item in selected], beforeSequence=selected[0]['sequence'] if len(rows)>100 else None)
                while len(page.messages)>1 and len(page.model_dump_json().encode('utf-8'))>491520:
                    page.messages.pop(0)
                    page.beforeSequence=page.messages[0].sequence
                return page

    async def append(self, owner: UUID, id: UUID, payload: MessageCreate):
        snapshot = payload.snapshot.model_dump(mode='json') if payload.snapshot else None
        async with self.connection() as conn:
            async with conn.transaction():
                row = await conn.fetchrow('SELECT id FROM conversations WHERE id=$1 AND owner_id=$2 AND deleted_at IS NULL FOR UPDATE', id, owner)
                if row is None:
                    raise StorageError('NOT_FOUND')
                existing = await conn.fetchrow('SELECT * FROM messages WHERE conversation_id=$1 AND request_id=$2 AND role=$3', id, payload.requestId, payload.role)
                if existing:
                    previous = message(existing)
                    if previous.content != payload.content or previous.status != payload.status or (previous.snapshot.model_dump(mode='json') if previous.snapshot else None) != snapshot:
                        raise StorageError('IDEMPOTENCY_CONFLICT')
                    return previous
                sequence = await conn.fetchval('SELECT COALESCE(MAX(sequence),0)+1 FROM messages WHERE conversation_id=$1', id)
                row = await conn.fetchrow('INSERT INTO messages(id,conversation_id,sequence,request_id,role,content,status,snapshot) VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb) RETURNING *', uuid4(), id, sequence, payload.requestId, payload.role, payload.content, payload.status, json.dumps(snapshot,ensure_ascii=False) if snapshot else None)
                await conn.execute('UPDATE conversations SET updated_at=clock_timestamp() WHERE id=$1 AND owner_id=$2', id, owner)
                return message(row)

    async def delete(self, owner: UUID, id: UUID):
        async with self.connection() as conn:
            async with conn.transaction():
                row=await conn.fetchrow('SELECT id FROM conversations WHERE id=$1 AND owner_id=$2 AND deleted_at IS NULL FOR UPDATE',id,owner)
                if row is None:
                    raise StorageError('NOT_FOUND')
                await conn.execute('DELETE FROM messages WHERE conversation_id=$1',id)
                await conn.execute("UPDATE conversations SET title='',deleted_at=clock_timestamp() WHERE id=$1 AND owner_id=$2",id,owner)

    async def delete_all(self, owner: UUID):
        async with self.connection() as conn:
            async with conn.transaction():
                await conn.execute('DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE owner_id=$1 AND deleted_at IS NULL)',owner)
                result=await conn.execute("UPDATE conversations SET title='',deleted_at=clock_timestamp() WHERE owner_id=$1 AND deleted_at IS NULL",owner)
                return int(result.rsplit(' ',1)[-1])
