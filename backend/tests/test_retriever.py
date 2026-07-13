"""测试「检索」零件里的纯逻辑：app/rag/retriever.py。

只测不依赖数据库/向量库的纯计算部分：
- _clip_parent：父块过长时以子块为中心裁剪，避免撑爆模型上下文。
- _Candidate.rrf_score：混合检索的排名融合打分(两路都靠前的得分更高)。
"""
from app.rag.retriever import _MAX_PARENT_CHARS, _Candidate, _clip_parent


def _mk(vec_rank=None, bm25_rank=None):
    return _Candidate(
        document_id=1, chunk_index=0, child="x",
        source="s", page_no=1, doc_type="t",
        vec_rank=vec_rank, bm25_rank=bm25_rank,
    )


def test_clip_短父块原样返回():
    text = "短内容"
    assert _clip_parent(text, "短") == text


def test_clip_长父块被裁剪到上限附近():
    long_text = "a" * 5000
    child = "a" * 80
    out = _clip_parent(long_text, child)
    # 裁剪后长度不应远超上限(含省略号余量)
    assert len(out) <= _MAX_PARENT_CHARS + 10


def test_clip_以子块为中心保留相关内容():
    # 子块内容在父块中间，裁剪后应仍包含它
    marker = "关键考点内容"
    long_text = "前文" * 500 + marker + "后文" * 500
    out = _clip_parent(long_text, marker)
    assert marker in out


def test_rrf_两路都命中得分高于单路():
    both = _mk(vec_rank=0, bm25_rank=0)
    only_vec = _mk(vec_rank=0)
    assert both.rrf_score() > only_vec.rrf_score()


def test_rrf_排名越靠前得分越高():
    top = _mk(vec_rank=0)
    lower = _mk(vec_rank=5)
    assert top.rrf_score() > lower.rrf_score()


def test_rrf_未命中任何一路得分为零():
    assert _mk().rrf_score() == 0.0
