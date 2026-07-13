"""bge-m3 嵌入模型封装(走 Ollama)。"""
from __future__ import annotations

from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from app.config import settings


@lru_cache
def get_embeddings() -> OllamaEmbeddings:
    """返回单例嵌入模型。bge-m3 输出 1024 维向量。

    keep_alive=24h：嵌入模型常驻显存，闲置不会被卸载。
    """
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
        keep_alive=86400,  # 秒(24h)；防止闲置后被卸载，与LLM模型保持一致
    )
