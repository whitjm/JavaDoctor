"""RAG 问答编排：检索 → 生成 → 落库。

对外暴露一个生成器 stream_answer，逐 token 产出，供 SSE 接口消费。
落库在生成结束后一次性完成，保证历史可回看且带引用。
"""
from __future__ import annotations

from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.rag import prompt as prompt_mod
from app.rag import retriever as retriever_mod
from app.rag import router as router_mod
from app.rag.llm import get_llm

# 多轮上下文：取最近 N 轮历史(user+assistant)喂模型，控制 token 开销
_HISTORY_ROUNDS = 3
_RETRIEVE_K = 5


def _history_messages(conv: Conversation) -> list:
    """把最近若干条历史转成 LangChain 消息，供多轮对话。"""
    msgs = conv.messages[-_HISTORY_ROUNDS * 2 :]
    out: list = []
    for m in msgs:
        if m.role == MessageRole.user:
            out.append(HumanMessage(content=m.content))
        else:
            out.append(AIMessage(content=m.content))
    return out


def stream_answer(
    db: Session, conv: Conversation, question: str
) -> Iterator[dict]:
    """执行一次 RAG 问答，逐步产出事件字典。

    产出事件：
      {"event": "citations", "data": [...]}   先发引用，前端可先渲染来源
      {"event": "token", "data": "片段"}       流式正文
      {"event": "done", "message_id": int}     结束，带 assistant 消息ID
      {"event": "error", "data": "..."}        出错
    """
    # 1. 先落库用户消息
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.user,
        content=question,
    )
    db.add(user_msg)
    # 首条消息时用问题给会话命名
    if conv.title in ("新会话", "") and not conv.messages:
        conv.title = question[:30]
    db.commit()

    # 1.5 意图路由：闲聊/自我介绍走人设直答，不检索(更快、更像助手)
    if router_mod.is_chitchat(question):
        yield {"event": "citations", "data": []}
        lang = router_mod.detect_language(question)
        yield from _stream_chitchat(db, conv, question, lang)
        return

    # 2. 检索 + 组装引用
    try:
        hits = retriever_mod.retrieve(db, question, k=_RETRIEVE_K)
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "data": f"检索失败: {exc}"}
        return

    citations = retriever_mod.to_citations(hits)
    yield {"event": "citations", "data": citations}

    # 无命中：不喂空上下文让模型瞎编，直接兜底回复
    if not hits:
        answer = "知识库中未找到相关内容，暂时无法回答该问题。"
        yield {"event": "token", "data": answer}
        assistant_msg = _save_assistant(db, conv, answer, [])
        yield {"event": "done", "message_id": assistant_msg.id}
        return

    # 3. 组装 Prompt(系统约束 + 历史 + 带编号上下文 + 问题)
    context = prompt_mod.build_context([h.passage for h in hits])
    messages = [SystemMessage(content=prompt_mod.SYSTEM_PROMPT)]
    messages.extend(_history_messages(conv))
    messages.append(
        HumanMessage(
            content=prompt_mod.USER_TEMPLATE.format(
                context=context, question=question, n=len(hits)
            )
        )
    )

    # 4. 流式生成(边生成边剥离思考段 + 剥离正文所有引用编号)
    # max_index=0：正文不展示任何 [n] 标注(来源由前端独立面板呈现)，
    # 所有形如 [数字] 的引用编号一律剥离，但代码数组下标 arr[0] 仍受保护。
    parts: list[str] = []
    filt = _ThinkFilter()
    cite_filt = _CitationFilter(max_index=0)
    try:
        for chunk in get_llm().stream(messages):
            text = chunk.content
            if not text:
                continue
            visible = cite_filt.feed(filt.feed(text))
            if visible:
                parts.append(visible)
                yield {"event": "token", "data": visible}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "data": f"生成失败: {exc}"}
        return

    tail = cite_filt.flush()
    if tail:
        parts.append(tail)
        yield {"event": "token", "data": tail}

    answer = "".join(parts).strip()
    if not answer:
        answer = "生成失败，请重试。"

    # 5. 落库 assistant 消息(含引用)
    assistant_msg = _save_assistant(db, conv, answer, citations)
    yield {"event": "done", "message_id": assistant_msg.id}


def _stream_chitchat(
    db: Session, conv: Conversation, question: str, lang: str = "zh"
) -> Iterator[dict]:
    """闲聊/自我介绍：用人设直答，不检索、不引用。按语言选 prompt。"""
    system_prompt = (
        prompt_mod.CHITCHAT_PROMPT_EN if lang == "en"
        else prompt_mod.CHITCHAT_PROMPT
    )
    messages = [SystemMessage(content=system_prompt)]
    messages.extend(_history_messages(conv))
    messages.append(HumanMessage(content=question))

    parts: list[str] = []
    filt = _ThinkFilter()
    try:
        for chunk in get_llm().stream(messages):
            text = chunk.content
            if not text:
                continue
            visible = filt.feed(text)
            if visible:
                parts.append(visible)
                yield {"event": "token", "data": visible}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "data": f"生成失败: {exc}"}
        return

    answer = "".join(parts).strip() or "你好，我是 JavaDoctor，可以帮你解答 Java 面试相关的问题。"
    assistant_msg = _save_assistant(db, conv, answer, [])
    yield {"event": "done", "message_id": assistant_msg.id}


def _save_assistant(
    db: Session, conv: Conversation, content: str, citations: list[dict]
) -> Message:
    msg = Message(
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content=content,
        citations=citations or None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


class _ThinkFilter:
    """流式剥离 qwen3 的 <think>...</think> 思考段。

    逐片喂入，返回本片中应对外可见的文本。跨片的 <think>/</think>
    标签靠缓冲兜底：只有确认不是标签起始的前缀才放行，避免半个标签泄漏。
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while self._buf:
            if self._in_think:
                idx = self._buf.find(self._CLOSE)
                if idx == -1:
                    # 未见结束标签：保留可能是 </think> 前缀的尾部
                    self._buf = self._keep_tail(self._buf, self._CLOSE)
                    break
                self._buf = self._buf[idx + len(self._CLOSE) :]
                self._in_think = False
            else:
                open_idx = self._buf.find(self._OPEN)
                close_idx = self._buf.find(self._CLOSE)
                # 兜底：模型漏了 <think> 起始却给了 </think>，则其之前均为思考段，丢弃
                if close_idx != -1 and (open_idx == -1 or close_idx < open_idx):
                    self._buf = self._buf[close_idx + len(self._CLOSE) :]
                    continue
                if open_idx == -1:
                    # 放行确定安全的部分，尾部可能是标签前缀则留存
                    safe = self._keep_tail(self._buf, self._OPEN) or self._keep_tail(
                        self._buf, self._CLOSE
                    )
                    emit = self._buf[: len(self._buf) - len(safe)] if safe else self._buf
                    if emit:
                        out.append(emit)
                    self._buf = safe
                    break
                if open_idx:
                    out.append(self._buf[:open_idx])
                self._buf = self._buf[open_idx + len(self._OPEN) :]
                self._in_think = True
        return "".join(out)

    @staticmethod
    def _keep_tail(buf: str, tag: str) -> str:
        """返回 buf 末尾可能是 tag 前缀的部分(需留在缓冲里)。"""
        for n in range(min(len(tag) - 1, len(buf)), 0, -1):
            if buf.endswith(tag[:n]):
                return buf[-n:]
        return ""


class _CitationFilter:
    """流式剥离正文中的引用编号 [n]。

    缓冲 `[...]` 片段，遇到方括号数字时校验：编号在 [1, max_index] 内则保留，
    否则丢弃。max_index=0 表示不保留任何 [数字] 编号(正文不展示引用标注，
    来源由前端独立面板呈现)。代码数组下标(如 arr[0])靠前导字符判断予以保护，
    非编号内容原样放行。跨 token 的 `[` 靠缓冲兜底。
    """

    def __init__(self, max_index: int) -> None:
        self._max = max_index
        self._buf = ""   # 缓冲一个未闭合的 [ 片段
        self._prev = ""  # 紧邻当前位置(或缓冲区)之前的一个字符

    @staticmethod
    def _is_code_context(prev: str) -> bool:
        """前导字符是标识符字符时，[n] 更像代码数组下标(如 arr[0])，不作引用处理。"""
        return bool(prev) and prev.isascii() and (prev.isalnum() or prev in "_]")

    def feed(self, text: str) -> str:
        if not text:
            return ""
        data = self._buf + text
        self._buf = ""
        out: list[str] = []
        i = 0
        while i < len(data):
            ch = data[i]
            if ch == "[":
                prev = data[i - 1] if i > 0 else self._prev
                close = data.find("]", i)
                if close == -1:
                    # 方括号未闭合，可能跨 token，缓冲等待后续
                    self._buf = data[i:]
                    self._prev = prev  # 记住缓冲 [ 之前的字符
                    break
                inner = data[i + 1 : close].strip()
                # 纯数字 + 非代码语境 → 当作引用编号校验；越界则丢弃
                if inner.isdigit() and not self._is_code_context(prev):
                    if 1 <= int(inner) <= self._max:
                        out.append(data[i : close + 1])
                    # else: 越界(幻觉/题号)，丢弃
                else:
                    out.append(data[i : close + 1])
                i = close + 1
            else:
                out.append(ch)
                i += 1
        result = "".join(out)
        if result:
            self._prev = result[-1]
        return result

    def flush(self) -> str:
        """收尾：残留缓冲若像越界引用编号则丢弃，否则原样返回。"""
        rest = self._buf
        self._buf = ""
        # 缓冲一定是未闭合的 [... ；仅当形如 [数字 且越界、且非代码语境时丢弃
        if rest.startswith("["):
            inner = rest[1:].strip()
            if (
                inner.isdigit()
                and not self._is_code_context(self._prev)
                and not (1 <= int(inner) <= self._max)
            ):
                return ""
        return rest
