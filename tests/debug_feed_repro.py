import os
import pathlib
import asyncio
import sys
from datetime import datetime, timezone
from fastapi.testclient import TestClient

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(ROOT_DIR / 'test_pulse.db').resolve()}"
from app.main import create_app
from app.db import get_engine, get_sessionmaker, posts

app = create_app(start_scheduler=False)
with TestClient(app) as client:
    init_response = client.post("/api/agent/init", json={"persona": {"name": "PULSE", "domain": "AI Engineering & Emerging Technology"}})
    print("init status", init_response.status_code, init_response.json())
    agent_id = init_response.json()["agentId"]
    now = datetime.now(timezone.utc)
    post1 = {
        "id": "1",
        "agent_id": agent_id,
        "created_at": now,
        "text": "First post",
        "rationale": "First rationale",
        "sources": ["https://example.com"],
        "topic_title": "topic 1",
        "topic_url": "https://example.com/1",
        "topic_source": "test",
        "topic_published_at": now,
    }
    post2 = post1.copy()
    post2["id"] = "2"
    post2["created_at"] = datetime.now(timezone.utc)

    engine = get_engine(f"sqlite+aiosqlite:///{pathlib.Path('./test_pulse.db').resolve()}")
    sessionmaker = get_sessionmaker(engine)

    async def insert_posts():
        async with sessionmaker() as session:
            await session.execute(posts.insert().values(post1))
            await session.execute(posts.insert().values(post2))
            await session.commit()

    asyncio.run(insert_posts())

    feed_response = client.get(f"/api/agent/feed?agentId={agent_id}")
    print("feed status", feed_response.status_code)
    print("feed json", feed_response.json())
