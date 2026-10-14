"""Dispatcher chat agent endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.agent import chat
from app.db import get_db

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = []


@router.post("/chat")
def agent_chat(body: ChatIn, db: Session = Depends(get_db)) -> dict:
    reply = chat(db, body.message, [t.model_dump() for t in body.history])
    return {"answer": reply.answer, "tool_calls": reply.tool_calls, "mode": reply.mode,
            "latency_ms": reply.latency_ms, "cost_usd": reply.usage.cost_usd}
