"""bge-m3 嵌入模型封装(走 Ollama)。"""
from __future__ import annotations

from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from app.config import settings


@lru_cache
def get_embeddings() -> OllamaEmbeddings:
    """返回单例嵌入模型。bge-m3 输出 1024 维向量。

    keep_alive=30m：嵌入模型常驻显存，避免每次检索都与对话模型互相挤出重载。
    """
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
        keep_alive=1800,  # 秒；OllamaEmbeddings 只接受整数，不认 "30m" 字符串
    )
