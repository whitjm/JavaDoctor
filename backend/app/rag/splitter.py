"""混合分段器：按「题号」语义切分，过长块再用定长二次切分。

同时根据「篇名」自动识别 doc_type 分类，并支持父子分段(small-to-big)：
- 父块 = 完整题目(问+答)，喂给模型用
- 子块 = 父块本身或其二次切分片段，用于向量检索

针对 javaQuestions.pdf 这类天然编号问答资料设计。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag.loaders import PageText

# 题号行: 行首「数字、」或「数字，」或「数字 、」等，后接标题
# 例: "1、Java语言有哪些特点"  "26 ，什么是空闲列表？"  "12 、 Ribbon"
_QUESTION_RE = re.compile(r"^\s*(\d{1,3})\s*[、，,\.]\s*(.+?)\s*$")

# 篇名/分类标题: 独立成行的「XX篇」或已知专题词
_SECTION_RE = re.compile(
    r"^\s*(基础篇|集合|容器|多线程|并发编程|JVM|虚拟机|异常|IO|反射|注解|"
    r"网络|Spring\s*Boot|Spring\s*Cloud|Spring|MyBatis|微服务|分布式|"
    r"数据库|MySQL|Redis|消息队列|设计模式|数据结构|算法|项目|"
    r"面试技巧|简历|职业规划|八股文)[篇]?\s*$",
    re.IGNORECASE,
)

# 篇名归一化到标准 doc_type
_SECTION_NORMALIZE = [
    (re.compile(r"基础", re.I), "Java基础"),
    (re.compile(r"集合|容器", re.I), "集合"),
    (re.compile(r"多线程|并发", re.I), "并发编程"),
    (re.compile(r"JVM|虚拟机", re.I), "JVM"),
    (re.compile(r"Spring\s*Cloud|微服务|分布式", re.I), "微服务"),
    (re.compile(r"Spring\s*Boot|Spring|MyBatis", re.I), "Spring全家桶"),
    (re.compile(r"数据库|MySQL|Redis|消息队列", re.I), "数据库与中间件"),
    (re.compile(r"设计模式|数据结构|算法", re.I), "数据结构与算法"),
    (re.compile(r"网络|IO|异常|反射|注解", re.I), "Java进阶"),
    (re.compile(r"项目", re.I), "项目面试"),
    (re.compile(r"面试技巧|简历|职业规划", re.I), "面试技巧"),
]


@dataclass
class Chunk:
    chunk_index: int
    content: str                    # 子块(检索用)
    parent_content: str             # 父块(喂模型)
    doc_type: str
    page_no: int | None = None
    title: str = ""


def _normalize_section(raw: str) -> str:
    for pattern, name in _SECTION_NORMALIZE:
        if pattern.search(raw):
            return name
    return raw.strip()


def _fixed_split(text: str, size: int, overlap: int) -> list[str]:
    """对过长文本做定长二次切分,尽量在换行/句号处断开。"""
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # 优先在换行或中文句号处断开
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind("。"))
            if cut > size // 2:
                end = start + cut + 1
        parts.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


@dataclass
class _Block:
    title: str
    lines: list[str] = field(default_factory=list)
    page_no: int | None = None
    doc_type: str = "未分类"


def _merge_short_blocks(blocks: list[_Block], min_len: int) -> list[_Block]:
    """把过短的块合并回前一个块。

    这些短块多为被误判成题号的答案子列表项(如"可靠安全""支持多线程"),
    合并回上一题的答案里语义更完整,也消除检索噪声。
    """
    merged: list[_Block] = []
    for blk in blocks:
        body = "\n".join(l for l in blk.lines).strip()
        if merged and len(body) < min_len:
            merged[-1].lines.append(body)
        else:
            merged.append(blk)
    return merged


def split_pages(
    pages: list[PageText],
    default_doc_type: str = "未分类",
    max_chunk_size: int = 800,
    chunk_overlap: int = 80,
    min_block_len: int = 60,
) -> list[Chunk]:
    """混合分段主入口。

    1. 逐行扫描，识别篇名(更新当前 doc_type)与题号(切分点)。
    2. 每个题目(问+答)聚成一个父块。
    3. 父块过长则二次切分为子块；否则子块=父块。
    """
    blocks: list[_Block] = []
    current = _Block(title="", doc_type=default_doc_type)
    current_doc_type = default_doc_type
    last_qno = 0  # 上一个被认定为真题号的编号，用于连续性判断

    for page in pages:
        for line in page.text.split("\n"):
            stripped = line.strip()
            if not stripped:
                if current.lines:
                    current.lines.append("")
                continue

            # 篇名行 → 更新分类并重置题号序列，不作为题目内容
            if _SECTION_RE.match(stripped) and len(stripped) <= 20:
                current_doc_type = _normalize_section(stripped)
                last_qno = 0
                continue

            # 题号行候选:仅当编号延续主序列(上一题号+1，或从1重开新篇)才认定为真题号，
            # 从而避免把答案里的子列表项(1、2、)误判成新面试题。
            m = _QUESTION_RE.match(stripped)
            qno = int(m.group(1)) if m else None
            is_question = (
                m is not None
                and len(m.group(2)) <= 60
                and (qno == last_qno + 1 or (qno == 1 and last_qno == 0))
            )
            if is_question:
                if current.lines:
                    blocks.append(current)
                current = _Block(
                    title=m.group(2).strip(),
                    lines=[stripped],
                    page_no=page.page_no,
                    doc_type=current_doc_type,
                )
                last_qno = qno
            else:
                if not current.lines:
                    current.page_no = page.page_no
                    current.doc_type = current_doc_type
                current.lines.append(stripped)

    if current.lines:
        blocks.append(current)

    # 后处理:把过短的块(多为被误判的答案子列表项)合并回前一个块。
    blocks = _merge_short_blocks(blocks, min_len=min_block_len)

    # 组装 Chunk(父子分段)
    chunks: list[Chunk] = []
    idx = 0
    for blk in blocks:
        parent = "\n".join(l for l in blk.lines).strip()
        if not parent:
            continue
        for sub in _fixed_split(parent, max_chunk_size, chunk_overlap):
            chunks.append(
                Chunk(
                    chunk_index=idx,
                    content=sub,
                    parent_content=parent,
                    doc_type=blk.doc_type,
                    page_no=blk.page_no,
                    title=blk.title,
                )
            )
            idx += 1
    return chunks


def preview_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """管理端分段预览：对纯文本做与入库一致的分段，返回子块列表。"""
    pages = [PageText(page_no=1, text=text)]
    chunks = split_pages(
        pages, max_chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    return [c.content for c in chunks]
