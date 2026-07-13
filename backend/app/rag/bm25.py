"""BM25 关键词检索(中文 jieba 分词)。

纯向量检索对专有术语/短查询易失准(如"双亲委派模型"被语义近邻带偏到
ZooKeeper)。BM25 基于词项精确匹配，正好补上这块短板，与向量检索融合后
显著提升召回。索引在进程内构建为单例，文档增删后调用 invalidate 重建。
"""
from __future__ import annotations

import re
import threading

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk

# 停用词：过滤无区分度的高频词，提升 BM25 精度
_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "对", "为", "把", "被", "就",
    "都", "也", "而", "及", "等", "个", "中", "上", "下", "这", "那", "有",
    "什么", "怎么", "如何", "一个", "可以", "我们", "他们", "以及", "并且",
    "，", "。", "、", "；", "：", "？", "！", "（", "）", " ", "\n", "\t",
    "的话", "一种", "进行", "使用", "通过", "由于", "因为", "所以", "如果",
}


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 去停用词 + 去纯符号。"""
    tokens = jieba.lcut(text or "")
    out: list[str] = []
    for t in tokens:
        t = t.strip()
        if not t or t in _STOPWORDS:
            continue
        if re.fullmatch(r"[\W_]+", t):  # 纯标点/符号
            continue
        out.append(t.lower())
    return out


class _Bm25Index:
    """进程内 BM25 索引单例。

    存 chunk 的 (document_id, chunk_index, tokens)，查询时返回
    与向量检索可对齐的候选列表，供 RRF 融合。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bm25: BM25Okapi | None = None
        self._meta: list[tuple[int, int]] = []  # 每行对应 (document_id, chunk_index)

    def build(self, db: Session) -> None:
        """从关系库全量重建索引。"""
        rows = db.query(DocumentChunk).all()
        corpus: list[list[str]] = []
        meta: list[tuple[int, int]] = []
        for r in rows:
            corpus.append(_tokenize(r.content))
            meta.append((r.document_id, r.chunk_index))
        with self._lock:
            self._bm25 = BM25Okapi(corpus) if corpus else None
            self._meta = meta

    def invalidate(self) -> None:
        """文档增删后置空，下次检索惰性重建。"""
        with self._lock:
            self._bm25 = None
            self._meta = []

    def ready(self) -> bool:
        return self._bm25 is not None

    def search(self, db: Session, query: str, k: int) -> list[tuple[int, int, float]]:
        """返回 top-k 的 [(document_id, chunk_index, score)]，按分降序。"""
        if self._bm25 is None:
            self.build(db)
        if self._bm25 is None:  # 库为空
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:k]
        out: list[tuple[int, int, float]] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            doc_id, chunk_idx = self._meta[i]
            out.append((doc_id, chunk_idx, float(scores[i])))
        return out


_index = _Bm25Index()


def get_index() -> _Bm25Index:
    return _index
