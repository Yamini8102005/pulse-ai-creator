import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / 'pulse_test_run.db'
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ['DATABASE_URL'] = f'sqlite+aiosqlite:///{DB_PATH}'
os.environ['OPENAI_API_KEY'] = 'test'
os.environ['PUBLISH_INTERVAL_MINUTES'] = '0.01'
os.environ['SCHEDULER_POLL_SECONDS'] = '1'
os.environ['BREETH_API_KEY'] = 'fake-key'
os.environ['BREETH_BASE_URL'] = 'http://127.0.0.1:9000'

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_engine, get_sessionmaker, init_db, agents, posts
from app.models import Topic, EditorialSelection
import app.publisher as publisher
import app.scheduler as scheduler
from app.breeth_client import BreethClient

class DummyLLM:
    async def chat(self, messages, temperature=0.2):
        return '{"text": "generated text", "rationale": "generated rationale", "why_now": "generated why now", "sources": ["https://example.com"]}'

class MockBreeth(BreethClient):
    def __init__(self):
        super().__init__(api_key='fake-key', base_url='https://example.com')
        self.search_called = False
        self.record_called = False

    async def record_episode(self, group_id: str, content: str, source_description: str = 'pulse-ai-creator'):
        self.record_called = True
        print('breeth record called', group_id)
        return {'status': 'ok'}

    async def search_topic(self, group_id: str, query: str, limit: int = 10):
        self.search_called = True
        print('breeth search called', group_id, query)
        return {'edges': []}

async def main():
    engine = get_engine(os.environ['DATABASE_URL'])
    await init_db(engine)
    sessionmaker = get_sessionmaker(engine)

    async with sessionmaker() as session:
        await session.execute(
            agents.insert().values(
                id='agent-temp',
                persona_name='PULSE',
                persona_domain='AI Engineering & Emerging Technology',
                created_at=datetime.now(timezone.utc),
                next_publish_at=datetime.now(timezone.utc),
                last_published_at=None,
                published_count=0,
                last_cycle_started_at=None,
            )
        )
        await session.commit()

    async def fake_discover():
        return [
            Topic(
                title='Temp Topic',
                summary='Temporary topic for scheduler test',
                url='https://example.com/temp',
                publishedAt=datetime.now(timezone.utc),
                source='Test',
            )
        ]

    async def fake_judge(topics, persona, llm):
        return EditorialSelection(
            selected_index=0,
            decision_reason='Select topic.',
            rejection_reasons=[],
            post_outline='Outline.',
        )

    publisher.discover_topics = fake_discover
    publisher.judge_topics = fake_judge

    breeth = MockBreeth()
    task = asyncio.create_task(
        scheduler.scheduler_loop(sessionmaker, poll_seconds=1, llm=DummyLLM(), breeth=breeth)
    )
    await asyncio.sleep(4)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    async with sessionmaker() as session:
        result = await session.execute(posts.select().where(posts.c.agent_id == 'agent-temp'))
        posted = result.fetchall()
        print('post count', len(posted))
        if posted:
            row = posted[0]
            mapping = row._mapping
            print('post row', {
                'id': mapping['id'],
                'createdAt': mapping['created_at'],
                'text': mapping['text'],
                'rationale': mapping['rationale'],
                'why_now': mapping['why_now'],
                'sources': mapping['sources'],
            })
    print('breeth search called', breeth.search_called)
    print('breeth record called', breeth.record_called)

asyncio.run(main())