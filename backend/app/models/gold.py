from typing import Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal['assistant', 'user']
    content: str


class GoldQuery(BaseModel):
    question: str
    conversation_history: list[ChatTurn] = Field(default_factory=list)


class GoldResponse(BaseModel):
    answer: str