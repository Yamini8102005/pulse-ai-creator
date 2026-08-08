import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from .config import settings

metadata = sa.MetaData()

agents = sa.Table(
    "agents",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True),
    sa.Column("persona_name", sa.String(length=128), nullable=False),
    sa.Column("persona_domain", sa.String(length=128), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("next_publish_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("published_count", sa.Integer, nullable=False, default=0),
    sa.Column("last_cycle_started_at", sa.DateTime(timezone=True), nullable=True),
)

posts = sa.Table(
    "posts",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True),
    sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("rationale", sa.Text, nullable=False),
    sa.Column("why_now", sa.Text, nullable=False),
    sa.Column("sources", sa.JSON, nullable=False),
    sa.Column("topic_title", sa.String(length=512), nullable=False),
    sa.Column("topic_url", sa.String(length=1024), nullable=False),
    sa.Column("topic_source", sa.String(length=128), nullable=False),
    sa.Column("topic_published_at", sa.DateTime(timezone=True), nullable=False),
)

rejection_records = sa.Table(
    "rejection_records",
    metadata,
    sa.Column("id", sa.String(length=36), primary_key=True),
    sa.Column("agent_id", sa.String(length=36), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
    sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("topic_title", sa.String(length=512), nullable=False),
    sa.Column("topic_url", sa.String(length=1024), nullable=False),
    sa.Column("topic_source", sa.String(length=128), nullable=False),
    sa.Column("reason", sa.Text, nullable=False),
)


def get_engine(database_url: str | None = None):
    return create_async_engine(database_url or settings.database_url, future=True, echo=False)


def get_sessionmaker(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine=None):
    engine = engine or get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    return engine
