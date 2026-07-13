"""Ollama 对话模型封装(qwen3:4b)。

qwen3 系列默认开启 thinking，会输出 <think>...</think> 段。
问答场景不需要展示思考过程，这里通过 reasoning=False 关闭，
若模型不支持该参数则由调用方剥离 <think> 段兜底。
"""
from __future__ import annotations

from functools import lru_cache

from langchain_ollama import ChatOllama

from app.config import settings


@lru_cache
def get_llm() -> ChatOllama:
    """返回单例对话模型。

    - temperature 调低：答案贴合知识库、减少发散。
    - num_ctx=6144：容纳 5 个父块上下文即可，过大会拖慢 prompt 处理。
    - num_predict=2048：给足生成长度，避免面向小白的详细讲解被中途截断。
    - keep_alive=24h：模型常驻显存(RTX 4070 8GB 绰绰有余)，闲置不会被卸载。
    """
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.2,
        num_ctx=6144,
        num_predict=2048,
        reasoning=False,
        keep_alive=86400,  # 秒(24h)，防止闲置时被Ollama卸载导致下次请求卡死
        timeout=120,      # 秒，单次推理超时，防止压测时请求堆积
    )
