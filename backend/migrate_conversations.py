"""대화 테이블을 반복 가능하게 생성합니다. 비밀값은 출력하지 않습니다."""
import argparse
import asyncio
import os
import secrets
import subprocess
from pathlib import Path
from dotenv import dotenv_values, load_dotenv, set_key
from conversation_store import ConversationStore


def configure_secret(path: Path):
    if dotenv_values(path).get('CONVERSATION_SESSION_SECRET'):
        return
    ignored = subprocess.run(['git','check-ignore','--quiet',str(path)],cwd=path.parent.parent,check=False)
    if ignored.returncode != 0:
        raise ValueError('ENV_NOT_IGNORED')
    set_key(str(path), 'CONVERSATION_SESSION_SECRET', secrets.token_urlsafe(48))


async def migrate():
    load_dotenv(Path(__file__).with_name('.env'))
    store = ConversationStore(os.getenv('DATABASE_URL',''))
    try:
        async with store.connection() as conn:
            async with conn.transaction():
                for migration in sorted(Path(__file__).with_name('migrations').glob('*.sql')):
                    await conn.execute(migration.read_text(encoding='utf-8'))
        print('Conversation tables: ready')
    finally:
        await store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--init-session-secret',action='store_true')
    args = parser.parse_args()
    try:
        if args.init_session_secret:
            configure_secret(Path(__file__).with_name('.env'))
        asyncio.run(migrate())
    except Exception:
        print('Conversation setup failed. Check server configuration and network access.')
        raise SystemExit(1) from None
