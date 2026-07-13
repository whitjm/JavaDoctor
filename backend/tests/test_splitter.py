"""测试「分段」零件：app/rag/splitter.py。

它把整篇文档按「题号」切成一个个问答块(父块)，过长再切成子块，
并按「篇名」自动打分类标签。测不依赖真实 PDF 的纯逻辑部分。
"""
from app.rag.loaders import PageText
from app.rag.splitter import _fixed_split, split_pages


def test_定长切分_短文本不切():
    assert _fixed_split("短文本", 800, 80) == ["短文本"]


def test_定长切分_长文本被切成多段():
    long_text = "句子。" * 500  # 远超 size
    parts = _fixed_split(long_text, 200, 20)
    assert len(parts) > 1
    assert all(len(p) <= 260 for p in parts)  # 含断句余量


def test_按题号切分成多个块():
    # 连续题号 1、2、3 应切成 3 个父块。
    # 注意：答案要足够长(>60字)，否则会被"过短块合并回前块"的降噪逻辑吃掉。
    ans = "这是一段足够长的答案内容，用来避免被过短块合并逻辑吞并，确保能独立成为一个父块。" * 2
    text = f"1、什么是Java\n{ans}\n2、什么是JVM\n{ans}\n3、什么是GC\n{ans}"
    chunks = split_pages([PageText(page_no=1, text=text)])
    titles = {c.title for c in chunks}
    assert "什么是Java" in titles
    assert "什么是JVM" in titles
    assert "什么是GC" in titles


def test_过短答案块被合并回前块_降噪():
    # 很短的题号块(像答案里的子列表)会被合并，不单独成块——这是有意的降噪
    text = "1、主题\n很长的答案" + "内容" * 40 + "\n2、短\n短"
    chunks = split_pages([PageText(page_no=1, text=text)])
    # "短"这个过短块应被合并，不会作为独立标题出现
    assert "短" not in {c.title for c in chunks} or len(chunks) == 1


def test_每个子块都带父块内容():
    text = "1、什么是Java\nJava是一门面向对象的编程语言"
    chunks = split_pages([PageText(page_no=1, text=text)])
    assert len(chunks) >= 1
    for c in chunks:
        assert c.parent_content  # 父块非空
        assert c.content         # 子块非空


def test_篇名自动分类():
    # 出现「JVM篇」后的题目应归类到 JVM
    text = "JVM\n1、什么是类加载\n类加载就是把class读进内存"
    chunks = split_pages([PageText(page_no=1, text=text)])
    assert any(c.doc_type == "JVM" for c in chunks)


def test_空页返回空结果():
    assert split_pages([PageText(page_no=1, text="")]) == []
