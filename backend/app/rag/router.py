"""查询意图路由。

不是所有输入都该走 RAG：打招呼、问"你是谁""你能干嘛"这类闲聊/元问题
若强行检索，只会让模型干读向量库、又慢又答非所问。这里用轻量规则先分流，
闲聊走人设直答(无检索、低延迟)，只有 Java 知识问题才进完整 RAG 管线。

规则优先(零成本、可解释)，是企业级 RAG 常见的 intent routing 做法。
"""
from __future__ import annotations

import re

# 问候 / 寒暄
_GREETING = re.compile(
    r"^(你好|您好|哈喽|哈啰|hi|hello|hey|在吗|在么|早上好|下午好|晚上好|"
    r"早安|晚安|嗨|谢谢|多谢|感谢|辛苦了|再见|拜拜|bye)[\s!！。.~]*$",
    re.IGNORECASE,
)

# 身份 / 能力等元问题(问的是助手本身，不是 Java 知识)
_META_KEYWORDS = (
    "你是谁", "你叫什么", "你的名字", "你是什么", "你是啥",
    "介绍一下你", "介绍下你", "自我介绍", "你能做什么", "你能干什么",
    "你会什么", "你有什么功能", "你能帮我做什么", "你是机器人吗",
    "你是ai吗", "你是人工智能", "你是gpt", "你是哪个模型",
)


def is_chitchat(text: str) -> bool:
    """判断是否为闲聊/元问题(应走人设直答而非 RAG)。"""
    q = text.strip()
    if not q:
        return True
    if _GREETING.match(q):
        return True
    low = q.lower().replace(" ", "")
    if any(k in low for k in _META_KEYWORDS):
        return True
    # 很短且不含中文/英文实义词的输入，多半是寒暄
    if len(q) <= 3 and not re.search(r"[A-Za-z]{2,}", q):
        return True
    return False
