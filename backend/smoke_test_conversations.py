"""실제 DB에서 합성 대화만 시험하고 종료 시 시험 대화를 삭제합니다."""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from conversation_contracts import ConversationCreate, MessageCreate
from conversation_store import ConversationStore, StorageError


async def smoke():
    load_dotenv(Path(__file__).with_name('.env'))
    store = ConversationStore(os.getenv('DATABASE_URL',''))
    owner, other = uuid4(), uuid4()
    identifier = None
    started = time.monotonic()
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    try:
        create = ConversationCreate(storageConsent=True,createRequestId=uuid4(),title='Synthetic persistence check')
        current = await store.create(owner,create,expires_at=expires_at)
        identifier = current.id
        assert (await store.create(owner,create,expires_at=expires_at)).id == identifier
        data = MessageCreate(storageConsent=True,requestId=uuid4(),role='user',content='합성 시험입니다.',status='completed')
        a,b = await asyncio.gather(store.append(owner,identifier,data),store.append(owner,identifier,data))
        assert a.id == b.id and a.sequence == 1
        try:
            await store.append(owner,identifier,data.model_copy(update={'content':'변경됨'}))
            raise AssertionError('Changed retry accepted')
        except StorageError as error:
            assert error.code == 'IDEMPOTENCY_CONFLICT'
        for call in (lambda:store.get(other,identifier),lambda:store.append(other,identifier,data),lambda:store.delete(other,identifier)):
            try:
                await call()
                raise AssertionError('Foreign owner accepted')
            except StorageError as error:
                assert error.code == 'NOT_FOUND'
        await store.close()
        assert (await store.get(owner,identifier)).messages[0].content == data.content
        async with store.connection() as conn:
            await conn.executemany('INSERT INTO messages(id,conversation_id,sequence,request_id,role,content,status) VALUES($1,$2,$3,$4,$5,$6,$7)',[(uuid4(),identifier,n,uuid4(),'assistant','합성 답변','completed') for n in range(2,102)])
        page = await store.get(owner,identifier)
        assert len(page.messages) == 100 and page.beforeSequence == 2
        assert [item.sequence for item in page.messages] == list(range(2,102))
        earlier = await store.get(owner,identifier,page.beforeSequence)
        assert len(earlier.messages) == 1 and earlier.messages[0].sequence == 1
        assert earlier.beforeSequence is None
        async with store.connection() as conn:
            await conn.executemany('INSERT INTO messages(id,conversation_id,sequence,request_id,role,content,status) VALUES($1,$2,$3,$4,$5,$6,$7)',[(uuid4(),identifier,n,uuid4(),'assistant','가'*60000,'completed') for n in range(102,106)])
        bounded = await store.get(owner,identifier)
        print({'largePageBytes':len(bounded.model_dump_json().encode('utf-8'))})
        assert len(bounded.model_dump_json().encode('utf-8')) < 524288
        assert bounded.beforeSequence is not None
        assert bounded.messages[-1].sequence == 105
        assert any(item.id == identifier for item in (await store.list(owner)).items)
        await store.delete(owner,identifier)
        try:
            await store.append(owner,identifier,data)
            raise AssertionError('Deleted conversation resurrected')
        except StorageError as error:
            assert error.code == 'NOT_FOUND'
        try:
            recreated = await store.create(owner,create,expires_at=expires_at)
            identifier = recreated.id
            raise AssertionError('Deleted create request resurrected')
        except StorageError as error:
            assert error.code == 'NOT_FOUND'
        identifier = None
        print({'passed':True,'checks':['create','duplicate','concurrent duplicate','changed retry','owner isolation','reconnect','101-message pagination','delete','no resurrection'],'seconds':round(time.monotonic()-started,2)})
    finally:
        async with store.connection() as conn:
            await conn.execute('DELETE FROM conversations WHERE owner_id=$1',owner)
        await store.close()


if __name__ == '__main__':
    try:
        asyncio.run(smoke())
    except Exception:
        print('Conversation DB smoke test failed; credentials and test messages are not printed.')
        raise SystemExit(1) from None
