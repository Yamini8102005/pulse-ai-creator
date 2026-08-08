import asyncio
import os
import pathlib
from datetime import datetime, timezone

TEST_DB_PATH = pathlib.Path("./test_pulse.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.resolve()}"

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import create_app
from app.db import init_db, get_engine, get_sessionmaker, posts


@pytest.fixture(autouse=True)
def setup_db():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    engine = get_engine(f"sqlite+aiosqlite:///{TEST_DB_PATH.resolve()}")
    asyncio.run(init_db(engine))
    yield
    asyncio.run(engine.dispose())


@pytest.fixture
def client():
    app = create_app(
        start_scheduler=False,
        database_url=f"sqlite+aiosqlite:///{TEST_DB_PATH.resolve()}",
    )
    with TestClient(app) as client:
        yield client


def test_agent_init_and_feed_empty(client):
    response = client.post(
        "/api/agent/init",
        json={"persona": {"name": "PULSE", "domain": "AI Engineering & Emerging Technology"}},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "agentId" in data

    feed_response = client.get(f"/api/agent/feed?agentId={data['agentId']}")
    assert feed_response.status_code == status.HTTP_200_OK
    assert feed_response.json() == {"posts": []}


def test_feed_returns_newest_first(client):
    response = client.post(
        "/api/agent/init",
        json={"persona": {"name": "PULSE", "domain": "AI Engineering & Emerging Technology"}},
    )
    agent_id = response.json()["agentId"]
    now = datetime.now(timezone.utc)
    post1 = {
        "id": "1",
        "agent_id": agent_id,
        "created_at": now,
        "text": "First post",
        "rationale": "First rationale",
        "why_now": "Still relevant.",
        "sources": ["https://example.com"],
        "topic_title": "topic 1",
        "topic_url": "https://example.com/1",
        "topic_source": "test",
        "topic_published_at": now,
    }
    post2 = post1.copy()
    post2["id"] = "2"
    post2["created_at"] = datetime.now(timezone.utc)

    engine = get_engine(f"sqlite+aiosqlite:///{TEST_DB_PATH.resolve()}")
    sessionmaker = get_sessionmaker(engine)

    async def insert_posts():
        async with sessionmaker() as session:
            await session.execute(posts.insert().values(post1))
            await session.execute(posts.insert().values(post2))
            await session.commit()

    asyncio.run(insert_posts())

    feed_response = client.get(f"/api/agent/feed?agentId={agent_id}")
    assert feed_response.status_code == status.HTTP_200_OK
    result = feed_response.json()["posts"]
    assert result[0]["id"] == "2"
    assert result[1]["id"] == "1"
