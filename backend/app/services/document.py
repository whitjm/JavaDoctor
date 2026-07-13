"""文档入库编排：解析 → 分段 → 嵌入 → 写 Chroma → 落库分段元数据。

删除文档时级联清理向量,保证双库一致。
"""
from __future__ import annotations

import os
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.rag import bm25, loaders, splitter, vectorstore


def save_upload(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """落盘上传文件,返回(存储路径, 文件类型)。"""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext not in loaders.SUPPORTED_TYPES:
        raise ValueError(f"不支持的文件类型: {ext}")
    os.makedirs(settings.upload_dir, exist_ok=True)
    unique = f"{uuid.uuid4().hex}_{filename}"
    path = os.path.join(settings.upload_dir, unique)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path, ext


def ingest_document(db: Session, document_id: int) -> None:
    """对一个已登记的文档执行入库管线。异常时置为 failed。"""
    doc = db.get(Document, document_id)
    if not doc:
        return
    try:
        # 1. 解析 + 清洗
        pages = loaders.load_document(doc.file_path, doc.file_type)
        if not pages:
            raise ValueError("未能从文档中提取到文本")

        # 2. 混合分段(题号语义 + 过长再切) + 篇名分类
        chunks = splitter.split_pages(pages, default_doc_type=doc.doc_type)
        if not chunks:
            raise ValueError("分段结果为空")

        # 3. 组装向量写入数据
        texts = [c.content for c in chunks]
        ids = [f"doc{document_id}_chunk{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "document_id": document_id,
                "chunk_id": c.chunk_index,
                "page_no": c.page_no or 0,
                "source": doc.filename,
                "doc_type": c.doc_type,
                "title": c.title,
            }
            for c in chunks
        ]

        # 4. 写 Chroma
        vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

        # 5. 落库分段元数据
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()
        for c, vid in zip(chunks, ids):
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    parent_content=c.parent_content,
                    vector_id=vid,
                    page_no=c.page_no,
                )
            )

        # 6. 更新文档状态
        doc.chunk_count = len(chunks)
        doc.status = DocumentStatus.indexed
        # 分类取出现最多的 doc_type 作为整篇标签
        type_counts: dict[str, int] = {}
        for c in chunks:
            type_counts[c.doc_type] = type_counts.get(c.doc_type, 0) + 1
        if type_counts:
            doc.doc_type = max(type_counts, key=type_counts.get)
        doc.error_msg = None
        db.commit()
        # 分段已变，BM25 索引失效，下次检索惰性重建
        bm25.get_index().invalidate()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        doc = db.get(Document, document_id)
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_msg = str(exc)[:500]
            db.commit()
        raise


def delete_document(db: Session, document_id: int) -> bool:
    """删除文档:先删向量,再删关系库记录与磁盘文件。"""
    doc = db.get(Document, document_id)
    if not doc:
        return False
    # 1. 删向量(按 document_id)
    try:
        vectorstore.delete_by_document(document_id)
    except Exception:
        pass
    # 2. 删磁盘文件
    try:
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except Exception:
        pass
    # 3. 删关系库(chunks 级联)
    db.delete(doc)
    db.commit()
    # BM25 索引失效
    bm25.get_index().invalidate()
    return True
