"""测试「文本清洗」零件：app/rag/loaders.py 的 clean_text。

它负责把 PDF 抠出来的脏文本洗干净：还原连字、去掉引用编号 [2]、
压掉中文间多余空格，同时不能误伤代码里的数组下标 arr[0]。
"""
from app.rag.loaders import clean_text


def test_去引用编号_中文后的方括号数字():
    # 「散列表[3]」这种引用编号要删掉
    assert clean_text("这是键值对[1]，也叫散列表[3]。") == "这是键值对,也叫散列表。"


def test_去引用编号_越界大编号也删():
    assert clean_text("底层是数组[15]加链表[8]。") == "底层是数组加链表。"


def test_保护代码_数组声明和大小():
    # 代码里的 int[] 和 int[10] 绝不能删
    assert clean_text("int[] arr = new int[10];") == "int[] arr = new int[10];"


def test_保护代码_下标访问():
    assert clean_text("访问arr[0]和nums[100]") == "访问arr[0]和nums[100]"


def test_保护代码_变量下标():
    assert clean_text("list[i] = map[key];") == "list[i] = map[key];"


def test_混合_删引用保代码():
    assert clean_text("引用[2]后接代码arr[5]") == "引用后接代码arr[5]"


def test_连字还原():
    # PDF 常见连字 ﬂ ﬁ 应还原成普通字母(中英文间空格会被一并压掉，属正常清洗)
    assert clean_text("ﬂoat 和 ﬁle") == "float和file"


def test_连字还原_纯英文不受空格影响():
    # ﬂ→fl, ﬁ→fi, ﬃ→ffi(三字母)。oﬃce = o+ffi+ce = office
    assert clean_text("ﬂoat ﬁle oﬃce") == "float file office"


def test_中文间多余空格压掉():
    assert clean_text("你  好   世界") == "你好世界"


def test_空字符串():
    assert clean_text("") == ""


def test_保留换行结构():
    # 清洗不能吃掉换行(分段依赖行结构)
    out = clean_text("第一行\n第二行")
    assert "\n" in out
