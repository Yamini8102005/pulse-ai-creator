from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import BaseModel, HttpUrl


class Persona(BaseModel):
    name: str
    domain: str


class AgentInitRequest(BaseModel):
    persona: Persona


class AgentInitResponse(BaseModel):
    agentId: str


class PostResponse(BaseModel):
    id: str
    createdAt: datetime
    text: str
    rationale: str
    whyNow: str
    sources: List[HttpUrl]


class FeedResponse(BaseModel):
    posts: List[PostResponse]


class Topic(BaseModel):
    title: str
    summary: str
    url: HttpUrl
    publishedAt: datetime
    source: str


class EditorialSelection(BaseModel):
    selected_index: int | None
    decision_reason: str
    rejection_reasons: list[dict]
    post_outline: str | None


class PostDraft(BaseModel):
    text: str
    rationale: str
    why_now: str
    sources: list[HttpUrl]
