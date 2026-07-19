"""查询意图路由 + 语言检测。

意图路由：不是所有输入都该走 RAG。打招呼/元问题走人设直答，只有技术问题进 RAG。
语言检测：用 Unicode 范围（零依赖），判断中文/英文，决定使用哪套 prompt。

规则优先(零成本、可解释)，是企业级 RAG 常见的 intent routing 做法。
"""
from __future__ import annotations

import re

# 问候 / 寒暄（中英文）
_GREETING = re.compile(
    r"^(你好|您好|哈喽|哈啰|hi|hello|hey|在吗|在么|早上好|下午好|晚上好|"
    r"早安|晚安|嗨|谢谢|多谢|感谢|辛苦了|再见|拜拜|bye|howdy|greetings|"
    r"what'?s up|yo)[\s!。，.,~]*$",
    re.IGNORECASE,
)

# 身份 / 能力等元问题（中文）
_META_KEYWORDS_ZH = (
    "你是谁", "你叫什么", "你的名字", "你是什么", "你是啥",
    "介绍一下你", "介绍下你", "自我介绍", "你能做什么", "你能干什么",
    "你会什么", "你有什么功能", "你能帮我做什么", "你是机器人吗",
    "你是ai吗", "你是人工智能", "你是gpt", "你是哪个模型",
)

# 身份 / 能力等元问题（英文，单词形式以便 lower+去空格后匹配）
_META_KEYWORDS_EN = (
    "whoareyou", "whatareyou", "yourname", "introduceyourself",
    "whatcanyoudo", "whatdoyoudo", "areyouabot", "areyouanai",
    "whatareyoumadeof", "whobuiltyou", "whatisyourpurpose",
    "hello", "hi", "hey", "hithere", "howdy",
)


def detect_language(text: str) -> str:
    """检测输入语言，返回 'zh'（中文）或 'en'（英文）。

    依据中文字符占比：超过 30% 判为中文，否则英文。
    纯符号/数字输入默认中文（知识库中文为主）。
    零依赖，纯 Unicode 范围判断。
    """
    if not text or not text.strip():
        return "zh"
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return "zh"
    zh_count = sum(1 for c in chars if "一" <= c <= "鿿")
    ratio = zh_count / len(chars)
    return "zh" if ratio >= 0.3 else "en"


def is_chitchat(text: str) -> bool:
    """判断是否为闲聊/元问题（应走人设直答而非 RAG）。"""
    q = text.strip()
    if not q:
        return True
    if _GREETING.match(q):
        return True
    low = q.lower().replace(" ", "")
    if any(k in low for k in _META_KEYWORDS_ZH):
        return True
    if any(k in low for k in _META_KEYWORDS_EN):
        return True
    # 很短且不含中文/英文实义词的输入，多半是寒暄
    if len(q) <= 3 and not re.search(r"[A-Za-z一-鿿]{2,}", q):
        return True
    return False
