"""测试「意图路由」零件：app/rag/router.py 的 is_chitchat。

它负责判断用户这句话是"闲聊/自我介绍"(直接人设回答、不查知识库)，
还是"真正的 Java 技术问题"(走完整检索)。判错了要么答非所问，要么白白变慢。
"""
import pytest

from app.rag.router import is_chitchat


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
