import os
import pathlib
import sys
from app.config import settings

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

print('cwd', pathlib.Path.cwd())
print('root', root)
print('settings db url', settings.database_url)
print('os env DATABASE_URL', os.environ.get('DATABASE_URL'))

from app.db import get_engine, get_sessionmaker
from app.main import create_app

engine = get_engine(settings.database_url)
print('engine url', engine.url)

print('db file exists?', pathlib.Path('test_pulse.db').exists())
print('abs db file', pathlib.Path('test_pulse.db').resolve())

import sqlite3
path = pathlib.Path('test_pulse.db').resolve()
if path.exists():
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    print('tables', [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
    for table in ['agents','posts']:
        try:
            print(table, cur.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
        except Exception as e:
            print(table, 'error', e)
    print('posts rows', cur.execute('SELECT id, agent_id, created_at, text FROM posts ORDER BY created_at DESC').fetchall())
    conn.close()
