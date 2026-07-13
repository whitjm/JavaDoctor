"""问答接口：SSE 流式返回真实 RAG 结果。

流式事件用 JSON 编码逐行发送(text/event-stream)：
  citations → token(多次) → done / error
落库在服务层完成，此处只负责取会话、鉴权、编码转发。
"""
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.base import SessionLocal, get_db
from app.models.conversation import Conversation
from app.models.message import FeedbackType, Message
from app.models.user import User
from app.schemas.conversation import ChatRequest, FeedbackRequest
from app.services import chat as chat_service

router = APIRouter(tags=["chat"])


def _sse(payload: dict) -> str:
    """把事件字典编码成一条 SSE 行。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/{conversation_id}")
def chat(
    conversation_id: int,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提问 → SSE 流式回答。检索 → Qwen 生成 → 引用回填 → 落库。"""
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "会话不存在")

    def event_stream():
        # 用独立 session：StreamingResponse 生成器在请求依赖已释放后仍在迭代
        session = SessionLocal()
        try:
            conv_local = session.get(Conversation, conversation_id)
            for evt in chat_service.stream_answer(session, conv_local, req.question):
                yield _sse(evt)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"event": "error", "data": str(exc)})
        finally:
            session.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{message_id}/feedback")
def submit_feedback(
    message_id: int,
    req: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """点赞 / 点踩。校验消息归属当前用户后写入反馈。"""
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "消息不存在")
    conv = db.get(Conversation, msg.conversation_id)
    if not conv or conv.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "消息不存在")
    msg.feedback = req.feedback
    db.commit()
    return {"detail": "ok", "feedback": req.feedback}
