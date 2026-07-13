"""检索与引用组装。

小-大策略(small-to-big)：用子块做向量检索保证命中精度，
再按 document_id + chunk_index 回查关系库拿父块喂给模型，
兼顾召回精度与上下文完整度。返回的 passages 与 citations 顺序一致，
编号即 Prompt 中的 [n]。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.rag import bm25 as bm25_mod
from app.rag import vectorstore


@dataclass
class Retrieved:
    """一条检索结果：喂模型的正文 + 前端展示的引用信息。"""
    passage: str          # 喂给模型的文本(父块优先)
    snippet: str          # 前端展示的片段(截断)
    source: str           # 来源文件名
    page_no: int          # 页码
    doc_type: str         # 分类
    chunk_id: int         # 分段序号
    score: float          # 距离分(越小越相关)


# 单个父块喂模型的字数上限。个别父块因整段未切开可达 2 万+ 字，
# 会撑爆 num_ctx 拖慢首字甚至截断，这里封顶并以子块为中心取窗口。
_MAX_PARENT_CHARS = 1200


def _clip_parent(parent: str, child: str) -> str:
    """父块过长时以子块位置为中心截取窗口，保住最相关内容。"""
    if len(parent) <= _MAX_PARENT_CHARS:
        return parent
    pos = parent.find(child[:80]) if child else -1
    if pos == -1:
        return parent[:_MAX_PARENT_CHARS]
    half = _MAX_PARENT_CHARS // 2
    start = max(0, pos - half)
    end = min(len(parent), start + _MAX_PARENT_CHARS)
    clip = parent[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(parent) else ""
    return f"{prefix}{clip}{suffix}"


def _parent_text(db: Session, document_id: int, chunk_index: int, child: str) -> str:
    """按 document_id + chunk_index 回查父块；查不到则退回子块。父块过长则裁剪。"""
    row = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index == chunk_index,
        )
        .first()
    )
    if row and row.parent_content:
        return _clip_parent(row.parent_content, child)
    return child


# RRF(Reciprocal Rank Fusion)常数：排名第 r 位贡献 1/(RRF_K + r)。
# 60 是文献常用默认值，弱化尾部排名、突出两路都靠前的结果。
_RRF_K = 60
# 每路检索的候选池大小(取比最终 k 更大的池子再融合)
_CANDIDATE_POOL = 10


@dataclass
class _Candidate:
    """融合前的候选：定位键 + 内容 + 元数据 + 两路排名。"""
    document_id: int
    chunk_index: int
    child: str
    source: str
    page_no: int
    doc_type: str
    vec_rank: int | None = None   # 向量检索中的排名(0-based)，未命中为 None
    bm25_rank: int | None = None  # BM25 检索中的排名

    @property
    def key(self) -> tuple[int, int]:
        return (self.document_id, self.chunk_index)

    def rrf_score(self) -> float:
        s = 0.0
        if self.vec_rank is not None:
            s += 1.0 / (_RRF_K + self.vec_rank)
        if self.bm25_rank is not None:
            s += 1.0 / (_RRF_K + self.bm25_rank)
        return s


def _vector_candidates(query: str, k: int, doc_type: str | None) -> dict[tuple[int, int], _Candidate]:
    """向量检索候选，按命中顺序记录排名。"""
    hits = vectorstore.similarity_search(query, k=k, doc_type=doc_type)
    out: dict[tuple[int, int], _Candidate] = {}
    for rank, (doc, _score) in enumerate(hits):
        meta = doc.metadata or {}
        document_id = meta.get("document_id")
        if document_id is None:
            continue
        chunk_index = int(meta.get("chunk_id", 0) or 0)
        cand = _Candidate(
            document_id=int(document_id),
            chunk_index=chunk_index,
            child=doc.page_content,
            source=meta.get("source", "未知来源"),
            page_no=int(meta.get("page_no", 0) or 0),
            doc_type=meta.get("doc_type", "未分类"),
            vec_rank=rank,
        )
        out[cand.key] = cand
    return out


def _merge_bm25(
    db: Session,
    cands: dict[tuple[int, int], _Candidate],
    query: str,
    k: int,
    doc_type: str | None,
) -> None:
    """把 BM25 命中并入候选表；已存在的补 bm25_rank，新增的从关系库补元数据。"""
    bm_hits = bm25_mod.get_index().search(db, query, k=k)
    for rank, (document_id, chunk_index, _s) in enumerate(bm_hits):
        key = (document_id, chunk_index)
        if key in cands:
            cands[key].bm25_rank = rank
            continue
        row = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index == chunk_index,
            )
            .first()
        )
        if not row:
            continue
        doc = db.get(Document, document_id)
        if doc_type and doc and doc.doc_type != doc_type:
            continue
        cands[key] = _Candidate(
            document_id=document_id,
            chunk_index=chunk_index,
            child=row.content,
            source=doc.filename if doc else "未知来源",
            page_no=row.page_no or 0,
            doc_type=doc.doc_type if doc else "未分类",
            bm25_rank=rank,
        )


def retrieve(db: Session, query: str, k: int = 5, doc_type: str | None = None) -> list[Retrieved]:
    """混合检索：向量(语义) + BM25(关键词) → RRF 融合 → 父块回填 → 结构化返回。

    纯向量对专有术语易失准，BM25 补关键词精确匹配，RRF 融合两路排名。
    """
    cands = _vector_candidates(query, _CANDIDATE_POOL, doc_type)
    _merge_bm25(db, cands, query, _CANDIDATE_POOL, doc_type)

    ranked = sorted(cands.values(), key=lambda c: c.rrf_score(), reverse=True)[:k]

    results: list[Retrieved] = []
    for c in ranked:
        passage = _parent_text(db, c.document_id, c.chunk_index, c.child)
        results.append(
            Retrieved(
                passage=passage,
                snippet=c.child[:200],
                source=c.source,
                page_no=c.page_no,
                doc_type=c.doc_type,
                chunk_id=c.chunk_index,
                score=c.rrf_score(),
            )
        )
    return results


def to_citations(items: list[Retrieved]) -> list[dict]:
    """转成落库 / 前端展示用的引用结构，编号与 passages 顺序对应。"""
    return [
        {
            "index": i + 1,
            "source": r.source,
            "page_no": r.page_no,
            "doc_type": r.doc_type,
            "chunk_id": r.chunk_id,
            "snippet": r.snippet,
        }
        for i, r in enumerate(items)
    ]
