import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .config import settings
from .db import init_db, get_engine, get_sessionmaker, agents, posts
from .models import AgentInitRequest, AgentInitResponse, FeedResponse, PostResponse

DEFAULT_PERSONA_NAME = "PULSE"
DEFAULT_PERSONA_DOMAIN = "AI Engineering & Emerging Technology"
from .publisher import publish_cycle
from .llm_client import LLMClient
from .breeth_client import BreethClient
from .scheduler import scheduler_loop


def create_app(start_scheduler: bool = True, database_url: str | None = None, scheduler_poll_seconds: int | None = None) -> FastAPI:
    app = FastAPI(title="PULSE AI Creator")

    # Configure CORS
    if settings.frontend_origin == "*":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.state.engine = None
    app.state.sessionmaker = None
    app.state.scheduler_task = None
    app.state.database_url = database_url
    app.state.scheduler_poll_seconds = scheduler_poll_seconds

    @app.on_event("startup")
    async def startup_event():
        engine = get_engine(database_url)
        await init_db(engine)
        app.state.engine = engine
        app.state.sessionmaker = get_sessionmaker(engine)
        if start_scheduler:
            app.state.scheduler_task = asyncio.create_task(
                scheduler_loop(
                    app.state.sessionmaker,
                    poll_seconds=app.state.scheduler_poll_seconds,
                )
            )

    @app.on_event("shutdown")
    async def shutdown_event():
        task = app.state.scheduler_task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        engine = app.state.engine
        if engine is not None:
            await engine.dispose()

    def get_session():
        if app.state.sessionmaker is None:
            raise RuntimeError("Database sessionmaker is not configured")
        session = app.state.sessionmaker()
        return session

    @app.exception_handler(RuntimeError)
    async def runtime_exception_handler(request: Request, exc: RuntimeError):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.post("/api/agent/init", response_model=AgentInitResponse)
    async def init_agent(request: AgentInitRequest):
        agent_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        next_publish_at = created_at
        persona_name = request.persona.name.strip() or DEFAULT_PERSONA_NAME
        persona_domain = request.persona.domain.strip() or DEFAULT_PERSONA_DOMAIN
        if persona_name.lower() != DEFAULT_PERSONA_NAME.lower():
            persona_name = DEFAULT_PERSONA_NAME
        if persona_domain.lower() != DEFAULT_PERSONA_DOMAIN.lower():
            persona_domain = DEFAULT_PERSONA_DOMAIN
        async with get_session() as session:
            await session.execute(
                agents.insert().values(
                    id=agent_id,
                    persona_name=persona_name,
                    persona_domain=persona_domain,
                    created_at=created_at,
                    next_publish_at=next_publish_at,
                    last_published_at=None,
                    published_count=0,
                    last_cycle_started_at=None,
                )
            )
            await session.commit()
        return AgentInitResponse(agentId=agent_id)

    @app.get("/api/agent/feed", response_model=FeedResponse)
    async def get_feed(agentId: str):
        async with get_session() as session:
            result = await session.execute(
                select(posts)
                .where(posts.c.agent_id == agentId)
                .order_by(posts.c.created_at.desc())
            )
            rows = result.fetchall()
        feed_posts = [
            PostResponse(
                id=row.id,
                createdAt=row.created_at,
                text=row.text,
                rationale=row.rationale,
                whyNow=row.why_now,
                sources=row.sources,
            )
            for row in rows
        ]
        return FeedResponse(posts=feed_posts)

    return app


app = create_app()
