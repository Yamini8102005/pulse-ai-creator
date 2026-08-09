import asyncio
import os
import pathlib
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.db import get_engine, get_sessionmaker, posts, agents, rejection_records, init_db
from app.publisher import publish_cycle
from app.models import Topic, EditorialSelection
from app.scheduler import scheduler_loop
from app.topic_discovery import discover_topics


def get_db_url(path: pathlib.Path) -> str:
    return f"sqlite+aiosqlite:///{path.resolve()}"


@pytest.fixture
def db_path(tmp_path_factory):
    return tmp_path_factory.mktemp("pulse_test") / "test_pulse.db"


@pytest.fixture(autouse=True)
def setup_db(db_path):
    engine = get_engine(get_db_url(db_path))
    asyncio.run(init_db(engine))
    yield
    asyncio.run(engine.dispose())


@pytest.fixture
def client(db_path):
    app = create_app(
        start_scheduler=False,
        database_url=get_db_url(db_path),
    )
    with TestClient(app) as client:
        yield client


class DummyLLM:
    async def chat(self, messages, temperature: float = 0.2):
        prompt = messages[-1]["content"]
        if "Candidates:" in prompt:
            return '{"selected_index": 0, "decision_reason": "Select first topic.", "rejection_reasons": [], "post_outline": "Outline."}'
        return '{"text": "A sharp post.", "rationale": "This is relevant.", "why_now": "It matters now.", "sources": ["https://example.com"]}'


class MockBreeth:
    def __init__(self):
        self.recorded = []
        self.available = False

    async def record_episode(self, group_id: str, content: str, source_description: str = "pulse-ai-creator"):
        self.recorded.append((group_id, content))
        return {"status": "ok"}

    async def search_topic(self, group_id: str, query: str, limit: int = 10):
        return {"edges": []}


def test_init_returns_agent_id(client):
    response = client.post(
        "/api/agent/init",
        json={"persona": {"name": "PULSE", "domain": "AI Engineering & Emerging Technology"}},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "agentId" in data
    assert isinstance(data["agentId"], str)


def test_feed_empty(client):
    response = client.post(
        "/api/agent/init",
        json={"persona": {"name": "PULSE", "domain": "AI Engineering & Emerging Technology"}},
    )
    agent_id = response.json()["agentId"]
    feed_response = client.get(f"/api/agent/feed?agentId={agent_id}")
    assert feed_response.status_code == status.HTTP_200_OK
    assert feed_response.json() == {"posts": []}


def test_feed_ordering_and_unique_ids(client, db_path):
    response = client.post(
        "/api/agent/init",
        json={"persona": {"name": "PULSE", "domain": "AI Engineering & Emerging Technology"}},
    )
    agent_id = response.json()["agentId"]
    engine = get_engine(get_db_url(db_path))
    sessionmaker = get_sessionmaker(engine)

    now = datetime.now(timezone.utc)
    post1 = {
        "id": "1",
        "agent_id": agent_id,
        "created_at": now - timedelta(minutes=1),
        "text": "First post",
        "rationale": "First rationale",
        "why_now": "Still relevant.",
        "sources": ["https://example.com"],
        "topic_title": "topic 1",
        "topic_url": "https://example.com/1",
        "topic_source": "test",
        "topic_published_at": now - timedelta(minutes=2),
    }
    post2 = post1.copy()
    post2["id"] = "2"
    post2["created_at"] = now

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
    assert result[0]["createdAt"] > result[1]["createdAt"]
    assert result[0]["whyNow"] == "Still relevant."


async def create_agent_record(db_path: pathlib.Path, agent_id: str):
    engine = get_engine(get_db_url(db_path))
    sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:
        await session.execute(
            agents.insert().values(
                id=agent_id,
                persona_name="PULSE",
                persona_domain="AI Engineering & Emerging Technology",
                created_at=datetime.now(timezone.utc),
                next_publish_at=datetime.now(timezone.utc),
                last_published_at=None,
                published_count=0,
                last_cycle_started_at=None,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_editorial_rejection_records(monkeypatch, db_path):
    await create_agent_record(db_path, "agent-test")

    async def fake_discover():
        return [
            Topic(
                title="Test Topic",
                summary="Summary",
                url="https://example.com/test",
                publishedAt=datetime.now(timezone.utc),
                source="Test",
            )
        ]

    async def fake_judge(topics, persona, llm):
        return EditorialSelection(
            selected_index=None,
            decision_reason="Rejected all topics.",
            rejection_reasons=[{"topic_index": 0, "title": "Test Topic", "reason": "Weak signal."}],
            post_outline=None,
        )

    monkeypatch.setattr("app.publisher.discover_topics", fake_discover)
    monkeypatch.setattr("app.publisher.judge_topics", fake_judge)
    engine = get_engine(get_db_url(db_path))
    sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:
        await publish_cycle("agent-test", session, DummyLLM(), MockBreeth())
        posts_result = await session.execute(select(posts).where(posts.c.agent_id == "agent-test"))
        assert posts_result.fetchall() == []
        rejection_result = await session.execute(select(rejection_records).where(rejection_records.c.agent_id == "agent-test"))
        assert len(rejection_result.fetchall()) == 1


@pytest.mark.asyncio
async def test_breeth_failure_does_not_block_publishing(monkeypatch, db_path):
    await create_agent_record(db_path, "agent-publish")

    async def fake_discover():
        return [
            Topic(
                title="Publish Topic",
                summary="Summary",
                url="https://example.com/publish",
                publishedAt=datetime.now(timezone.utc),
                source="Test",
            )
        ]

    async def fake_judge(topics, persona, llm):
        return EditorialSelection(
            selected_index=0,
            decision_reason="Select the first topic.",
            rejection_reasons=[],
            post_outline="Outline.",
        )

    monkeypatch.setattr("app.publisher.discover_topics", fake_discover)
    monkeypatch.setattr("app.publisher.judge_topics", fake_judge)
    engine = get_engine(get_db_url(db_path))
    sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:
        await publish_cycle("agent-publish", session, DummyLLM(), MockBreeth())
        result = await session.execute(select(posts).where(posts.c.agent_id == "agent-publish"))
        assert len(result.fetchall()) == 1


@pytest.mark.asyncio
async def test_scheduler_autonomous_publishing(monkeypatch, db_path):
    await create_agent_record(db_path, "agent-scheduler")

    async def fake_discover():
        return [
            Topic(
                title="Scheduler Topic",
                summary="Summary",
                url="https://example.com/scheduler",
                publishedAt=datetime.now(timezone.utc),
                source="Test",
            )
        ]

    async def fake_judge(topics, persona, llm):
        return EditorialSelection(
            selected_index=0,
            decision_reason="Select topic.",
            rejection_reasons=[],
            post_outline="Outline.",
        )

    monkeypatch.setattr("app.publisher.discover_topics", fake_discover)
    monkeypatch.setattr("app.publisher.judge_topics", fake_judge)

    task = asyncio.create_task(
        scheduler_loop(
            get_sessionmaker(get_engine(get_db_url(db_path))),
            poll_seconds=1,
            llm=DummyLLM(),
            breeth=MockBreeth(),
        )
    )
    await asyncio.sleep(2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    engine = get_engine(get_db_url(db_path))
    sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:
        result = await session.execute(select(posts).where(posts.c.agent_id == "agent-scheduler"))
        assert len(result.fetchall()) == 1


@pytest.mark.asyncio
async def test_duplicate_scheduler_claim_protection(monkeypatch, db_path):
    await create_agent_record(db_path, "agent-duplicate")

    async def fake_discover():
        return [
            Topic(
                title="Duplicate Topic",
                summary="Summary",
                url="https://example.com/duplicate",
                publishedAt=datetime.now(timezone.utc),
                source="Test",
            )
        ]

    async def fake_judge(topics, persona, llm):
        return EditorialSelection(
            selected_index=0,
            decision_reason="Select topic.",
            rejection_reasons=[],
            post_outline="Outline.",
        )

    async def slow_publish(agent_id, session, llm, breeth):
        await asyncio.sleep(1)
        await session.execute(posts.insert().values({
            "id": "dup-1",
            "agent_id": agent_id,
            "created_at": datetime.now(timezone.utc),
            "text": "Duplicate safe post",
            "rationale": "Safe.",
            "why_now": "Now",
            "sources": ["https://example.com"],
            "topic_title": "Duplicate Topic",
            "topic_url": "https://example.com/duplicate",
            "topic_source": "Test",
            "topic_published_at": datetime.now(timezone.utc),
        }))
        await session.commit()

    monkeypatch.setattr("app.publisher.discover_topics", fake_discover)
    monkeypatch.setattr("app.publisher.judge_topics", fake_judge)
    monkeypatch.setattr("app.scheduler.publish_cycle", slow_publish)

    engine = get_engine(get_db_url(db_path))
    sessionmaker = get_sessionmaker(engine)
    task1 = asyncio.create_task(
        scheduler_loop(
            sessionmaker,
            poll_seconds=1,
            llm=DummyLLM(),
            breeth=MockBreeth(),
        )
    )
    task2 = asyncio.create_task(
        scheduler_loop(
            sessionmaker,
            poll_seconds=1,
            llm=DummyLLM(),
            breeth=MockBreeth(),
        )
    )
    await asyncio.sleep(3)
    task1.cancel()
    task2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task1
    with pytest.raises(asyncio.CancelledError):
        await task2

    async with sessionmaker() as session:
        result = await session.execute(select(posts).where(posts.c.agent_id == "agent-duplicate"))
        assert len(result.fetchall()) == 1


def test_discover_topics_live_source():
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Skipping live topic discovery because neither GEMINI_API_KEY nor OPENAI_API_KEY is configured")

    topics = asyncio.run(discover_topics())
    assert isinstance(topics, list)
    assert len(topics) > 0
    assert all(hasattr(topic, "title") for topic in topics)


def test_llm_provider_configuration(monkeypatch):
    from app.llm_client import LLMClient
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")

    client = LLMClient()
    assert client.provider == "openai"
    assert client.api_key == "fake-key"
    assert client.base_url == "https://api.openai.com/v1"
    assert client.model == "gpt-test"


def test_llm_gemini_provider_configuration(monkeypatch):
    from app.llm_client import LLMClient
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_API_BASE", "https://gemini.googleapis.com/v1")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    client = LLMClient()
    assert client.provider == "gemini"
    assert client.api_key == "fake-key"
    assert client.base_url == "https://gemini.googleapis.com/v1"
    assert client.model == "gemini-test"


def test_llm_ollama_provider_configuration(monkeypatch):
    from app.llm_client import LLMClient
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_API_BASE", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    client = LLMClient()
    assert client.provider == "ollama"
    assert client.api_key == ""
    assert client.base_url == "http://localhost:11434/v1"
    assert client.model == "gpt-test"


def test_llm_error_classification(monkeypatch):
    from app.llm_client import LLMClient, LLMClientError

    class FakeResponse:
        status_code = 429
        def json(self):
            return {"error": {"code": "credit_balance_exhausted", "message": "No credits"}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            class Resp:
                status_code = 429

                def raise_for_status(self):
                    raise httpx.HTTPStatusError("error", request=None, response=FakeResponse())

                def json(self):
                    return {"error": {"code": "credit_balance_exhausted", "message": "No credits"}}

            return Resp()

    async def fake_async_client(*args, **kwargs):
        return FakeClient()

    from app import llm_client
    original_client = httpx.AsyncClient
    try:
        monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())
        client = LLMClient(api_key="fake", base_url="https://example.com", model="gpt-test")
        with pytest.raises(LLMClientError) as exc_info:
            asyncio.run(client.chat([{"role": "system", "content": "ping"}]))
        assert exc_info.value.category == "quota_exhausted"
    finally:
        monkeypatch.setattr(httpx, "AsyncClient", original_client)
