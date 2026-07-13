"""测试两个「流式过滤器」零件：app/services/chat.py。

大模型是一个字一个字往外吐的，这两个过滤器要在流式过程中实时净化：
- _ThinkFilter：剥掉模型的思考过程 <think>...</think>，不让它泄漏给用户。
- _CitationFilter：剥掉越界的引用编号(如只有5条引用却冒出 [15])，但保护代码下标 arr[0]。
难点在于标签/编号可能被切成好几段送进来(跨 token)，过滤器必须能拼起来判断。
"""
from app.services.chat import _CitationFilter, _ThinkFilter


def _feed_think(chunks):
    f = _ThinkFilter()
    return "".join(f.feed(c) for c in chunks)


def _feed_cite(chunks, max_index):
    f = _CitationFilter(max_index=max_index)
    return "".join(f.feed(c) for c in chunks) + f.flush()


# ---------- _ThinkFilter ----------

def test_think_剥离完整思考段():
    assert _feed_think(["<think>我在想</think>正式答案"]) == "正式答案"


def test_think_无思考段原样输出():
    assert _feed_think(["这是普通回答"]) == "这是普通回答"


def test_think_跨分片的标签():
    # 标签被切成好几段送进来，也要能正确剥离
    assert _feed_think(["<th", "ink>思考", "内容</thi", "nk>答案"]) == "答案"


def test_think_漏了起始标签只有结束标签():
    # qwen 有时省略 <think> 只给 </think>，其前的内容视为思考段丢弃
    assert _feed_think(["直接思考</think>真正答案"]) == "真正答案"


# ---------- _CitationFilter ----------

def test_cite_保留有效引用编号():
    assert _feed_cite(["键值对[1]，散列表[3]。"], 5) == "键值对[1]，散列表[3]。"


def test_cite_丢弃越界编号():
    # 只有5条引用，[15][8] 是幻觉/原文题号，删掉
    assert _feed_cite(["数组[15]加链表[8]，树[2]。"], 5) == "数组加链表，树[2]。"


def test_cite_保护代码数组下标():
    # 前面是标识符字符(如 arr、int) → 是代码下标，不能删
    assert _feed_cite(["int[] a = new int[10];"], 5) == "int[] a = new int[10];"
    assert _feed_cite(["访问 arr[0] 和 nums[100]"], 5) == "访问 arr[0] 和 nums[100]"


def test_cite_跨分片的编号():
    # [12] 越界应删，[2] 有效应留，且编号被切片送入
    assert _feed_cite(["值[", "1", "2", "]和值[", "2", "]"], 5) == "值和值[2]"


def test_cite_边界值():
    # [5] 恰好有效，[6] 越界
    assert _feed_cite(["恰好[5]和越界[6]"], 5) == "恰好[5]和越界"


def test_cite_max0_剥离所有引用编号():
    # max_index=0：正文不展示任何 [n]，全部剥离
    assert _feed_cite(["基础[1]，进阶[2]，实战[5]。"], 0) == "基础，进阶，实战。"


def test_cite_max0_仍保护代码下标():
    # 即使全剥离模式，代码数组下标也不能误删
    assert _feed_cite(["int[] a = new int[10]; arr[0]=1;"], 0) == "int[] a = new int[10]; arr[0]=1;"
