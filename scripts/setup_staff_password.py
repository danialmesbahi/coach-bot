"""One-time, local operator setup for a seeded account with no password.

Run inside web-api after migration, passing an ignored JSON credentials file.
Never exposes the password/hash and never resets an already configured account.
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.services.staff import hash_password, audit


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--telegram-id', type=int, required=True)
    parser.add_argument('--credentials-file', type=Path, required=True)
    args = parser.parse_args()
    credentials = json.loads(args.credentials_file.read_text(encoding='utf-8'))
    username = credentials['username']
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,40}', username):
        raise ValueError('Invalid username')
    encoded = hash_password(credentials['password'])
    connection = await asyncpg.connect(get_settings().database_url)
    try:
        async with connection.transaction():
            await connection.execute('SELECT pg_advisory_xact_lock(917002)')
            account = await connection.fetchrow("""UPDATE staff_accounts SET username=$2,password_hash=$3,
                status='active',auth_mode='password',session_version=session_version+1,updated_at=NOW()
                WHERE telegram_id=$1 AND password_hash IS NULL AND status='invited' AND role='platform' RETURNING *""",
                args.telegram_id, username.lower(), encoded)
            if not account:
                raise RuntimeError('Refused: no unconfigured platform account matches. Existing passwords are never overwritten.')
            await audit(connection, account, 'staff_password_bootstrap', 'staff', account['id'])
        print('Initial password configured. Sign in and change it from My profile.')
    finally:
        await connection.close()


if __name__ == '__main__':
    asyncio.run(main())
