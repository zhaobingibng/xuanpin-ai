"""Assistant API endpoints — AI-powered Q&A for product selection."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.assistant_repository import AssistantRepository
from app.database.base import get_async_session_factory
from app.services.assistant.assistant import SelectionAssistant

router = APIRouter()


class AskRequest(BaseModel):
    question: str


@router.post("/assistant/ask")
async def assistant_ask(req: AskRequest) -> dict:
    """AI问答接口。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            assistant = SelectionAssistant(session)
            return await assistant.ask(req.question)
    except Exception:
        raise HTTPException(status_code=500, detail="AI回答失败")


@router.get("/assistant/history")
async def assistant_history(limit: int = 30) -> list[dict]:
    """查看问答历史。"""
    try:
        async_session_factory = get_async_session_factory()
        async with async_session_factory() as session:
            repo = AssistantRepository(session)
            records = await repo.history(limit=limit)
            return [
                {
                    "id": r.id,
                    "question": r.question,
                    "answer": json.loads(r.answer) if r.answer else {},
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]
    except Exception:
        raise HTTPException(status_code=500, detail="获取问答历史失败")
