"""测试「意图路由」零件：app/rag/router.py 的 is_chitchat + detect_language。

is_chitchat：判断是"闲聊/自我介绍"(直答)还是"技术问题"(走 RAG)。
detect_language：判断中文/英文，零依赖，纯 Unicode 范围。
"""
import pytest

from app.rag.router import detect_language, is_chitchat


@pytest.mark.parametrize("text", [
    "你好", "您好", "hi", "hello", "在吗", "谢谢", "再见",
    "你是谁", "你叫什么", "你能做什么", "你会什么", "自我介绍一下",
    "你是什么模型", "你是机器人吗",
])
def test_闲聊和元问题_应识别为闲聊(text):
    assert is_chitchat(text) is True


@pytest.mark.parametrize("text", [
    "什么是双亲委派模型", "HashMap的底层原理",
    "谈谈你对Spring IOC的理解", "JVM内存结构",
    "你知道volatile关键字吗", "讲讲多态",
])
def test_技术问题_不应识别为闲聊(text):
    assert is_chitchat(text) is False


def test_空输入_当作闲聊():
    assert is_chitchat("") is True
    assert is_chitchat("   ") is True


# ── 语言检测 ──────────────────────────────────────────────


@pytest.mark.parametrize("text,lang", [
    ("你好，Java是什么", "zh"),
    ("什么是HashMap", "zh"),
    ("请问Spring的依赖注入有几种方式", "zh"),
    ("介绍一下JVM内存模型", "zh"),
    ("hi, what is HashMap", "en"),
    ("Explain JVM memory model", "en"),
    ("How does Spring IOC work", "en"),
    ("What is the difference between ArrayList and LinkedList", "en"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


def test_detect_language_mixed_chinese_dominant():
    # 混用时中文字符多，判为中文
    assert detect_language("我想了解Java的HashMap实现原理") == "zh"


def test_detect_language_mixed_english_dominant():
    # 混用但中文字符少，判为英文
    assert detect_language("Can you explain how HashMap works in Java") == "en"


def test_detect_language_pure_symbols_defaults_to_en():
    # 无语言信号时默认英文（知识库以英文为主的用户场景）
    assert detect_language("!!! ???") == "en"
    assert detect_language("") == "zh"
    assert detect_language("   ") == "zh"


def test_detect_language_numbers_defaults_to_en():
    assert detect_language("123456") == "en"


@pytest.mark.parametrize("text", [
    "who are you", "what can you do", "are you an ai",
    "hello world", "hi there",
])
def test_英文闲聊_识别为闲聊(text):
    assert is_chitchat(text) is True
