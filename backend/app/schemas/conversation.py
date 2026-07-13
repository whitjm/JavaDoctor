"""会话 / 消息请求响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.message import FeedbackType, MessageRole


class ConversationCreate(BaseModel):
    title: str = "新会话"


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    citations: list | None = None
    feedback: FeedbackType | None = None
    created_at: datetime


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    feedback: FeedbackType
