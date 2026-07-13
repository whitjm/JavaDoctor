"""ChromaDB 向量库封装(嵌入式, 本地持久化)。

每个向量的 metadata 存 document_id / chunk_id / page_no / source / doc_type,
删除文档时按 document_id 批量清理,保证与关系库一致。
"""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_chroma import Chroma

from app.config import settings
from app.rag.embeddings import get_embeddings


@lru_cache
def get_vectorstore() -> Chroma:
    """返回单例 Chroma 向量库。"""
    os.makedirs(settings.chroma_dir, exist_ok=True)
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_dir,
    )


def add_texts(
    texts: list[str],
    metadatas: list[dict],
    ids: list[str],
    batch_size: int = 32,
) -> None:
    """分批写入向量。ids 由调用方生成(如 doc{id}_chunk{idx})。

    分批(默认 32/批)是必要的：一次性把数百条文本丢给 Ollama 嵌入运行器
    会压垮其内部进程(表现为 tokenize 端口拒连崩溃)。每批失败重试一次。
    """
    import time

    vs = get_vectorstore()
    total = len(texts)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        b_texts = texts[start:end]
        b_metas = metadatas[start:end]
        b_ids = ids[start:end]
        for attempt in range(2):
            try:
                vs.add_texts(texts=b_texts, metadatas=b_metas, ids=b_ids)
                break
            except Exception:
                if attempt == 0:
                    time.sleep(1.5)  # 运行器可能瞬时重启，稍等重试
                    continue
                raise


def delete_by_document(document_id: int) -> None:
    """按 document_id 删除该文档的全部向量。"""
    vs = get_vectorstore()
    vs.delete(where={"document_id": document_id})


def count_vectors() -> int:
    """当前集合内向量总数。"""
    vs = get_vectorstore()
    try:
        return vs._collection.count()
    except Exception:
        return 0


def similarity_search(query: str, k: int = 5, doc_type: str | None = None):
    """向量检索。doc_type 非空时按分类过滤。"""
    vs = get_vectorstore()
    where = {"doc_type": doc_type} if doc_type else None
    return vs.similarity_search_with_score(query, k=k, filter=where)
