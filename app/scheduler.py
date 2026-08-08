import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from .db import agents
from .publisher import publish_cycle
from .llm_client import LLMClient
from .breeth_client import BreethClient
from .config import settings


async def _claim_due_agent(session: AsyncSession) -> list[str]:
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(minutes=settings.scheduler_claim_stale_minutes)
    stmt = (
        update(agents)
        .where(
            agents.c.next_publish_at <= now,
            (agents.c.last_cycle_started_at == None) | (agents.c.last_cycle_started_at < stale_at),
        )
        .values(last_cycle_started_at=now)
        .returning(agents.c.id)
    )
    result = await session.execute(stmt)
    await session.commit()
    return [row[0] for row in result.fetchall()]


async def scheduler_loop(sessionmaker, poll_seconds: int | None = None, llm: LLMClient | None = None, breeth: BreethClient | None = None):
    llm = llm or LLMClient()
    breeth = breeth or BreethClient()
    delay = poll_seconds or settings.scheduler_poll_seconds
    while True:
        async with sessionmaker() as session:
            due_agent_ids = await _claim_due_agent(session)
        for agent_id in due_agent_ids:
            try:
                async with sessionmaker() as session:
                    await publish_cycle(agent_id, session, llm, breeth)
            except Exception:
                pass
        await asyncio.sleep(delay)
