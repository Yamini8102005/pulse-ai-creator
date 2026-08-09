import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from .db import agents
from .publisher import publish_cycle
from .llm_client import LLMClient
from .breeth_client import BreethClient
from .config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _claim_due_agent(session: AsyncSession) -> list[str]:
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(minutes=settings.scheduler_claim_stale_minutes)
    stmt = (
        update(agents)
        .where(
            agents.c.next_publish_at <= now,
            (agents.c.last_cycle_started_at.is_(None)) | (agents.c.last_cycle_started_at < stale_at),
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
        due_agent_ids = []
        async with sessionmaker() as session:
            try:
                due_agent_ids = await _claim_due_agent(session)
            except Exception:
                logger.exception("Scheduler claim operation failed")
        for agent_id in due_agent_ids:
            async with sessionmaker() as session:
                try:
                    await publish_cycle(agent_id, session, llm, breeth)
                except Exception as exc:
                    logger.exception("Scheduler failed while publishing for agent %s: %s", agent_id, exc)
                    try:
                        await session.execute(
                            update(agents)
                            .where(agents.c.id == agent_id)
                            .values(last_cycle_started_at=None)
                        )
                        await session.commit()
                    except Exception:
                        logger.exception("Failed to reset last_cycle_started_at for agent %s", agent_id)
        await asyncio.sleep(delay)
