#!/usr/bin/env python3
"""
传习录 7 概念标表 - 本地检索器
MVP 第 2 步最简版:不依赖外部知识库,直接 grep 7 个产物文件
支持 3 种检索:按概念 / 按条号 / 按关键词
"""
import re
import sys
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent

# 7 概念清单
CONCEPTS = [
    "心即理",
    "格物致知",
    "省察克治",
    "知行合一",
    "致良知",
    "万物一体",
    "事上磨练",
]

# 6 段产物文件映射
SEGMENTS = {
    "徐爱录": "传习录_徐爱录_7概念标表_中华文库.md",
    "陆澄录": "传习录_陆澄录_7概念标表_中华文库.md",
    "薛侃录": "传习录_薛侃录_7概念标表_中华文库.md",
    "中卷":   "传习录_中卷_7概念标表_中华文库.md",
    "下卷前半": "传习录_下卷前半_7概念标表_中华文库.md",
    "下卷后半": "传习录_下卷后半_7概念标表_中华文库.md",
}

# 一行 = 〔条号〕首句 → 概念标(逗号分隔)
LINE_PAT = re.compile(r"〔(\d+)〕(.+?)\s*→\s*([^\n]+)")


def load_all_lines():
    """加载所有产物文件的行 → [(seg, entry_no, first, concepts_str)]"""
    global _LINES_CACHE
    if _LINES_CACHE is not None:
        return _LINES_CACHE
    records = []
    for seg_name, fname in SEGMENTS.items():
        fpath = WORKDIR / fname
        if not fpath.exists():
            continue
        for line in fpath.read_text(encoding="utf-8").split("\n"):
            m = LINE_PAT.search(line)
            if m:
                records.append({
                    "seg": seg_name,
                    "no": m.group(1),
                    "first": m.group(2).strip(),
                    "concepts_str": m.group(3).strip(),
                    "concepts_list": [c.strip() for c in m.group(3).replace("**", "").split(",")],
                })
    _LINES_CACHE = records
    return records


_LINES_CACHE = None


def search_by_concept(concept: str, seg_filter: str = None) -> list:
    """按概念检索"""
    all_records = load_all_lines()
    results = []
    for r in all_records:
        if seg_filter and r["seg"] != seg_filter:
            continue
        if any(concept in c for c in r["concepts_list"]):
            results.append(r)
    return results


def search_by_entry(entry_no: str) -> list:
    """按条号检索"""
    all_records = load_all_lines()
    return [r for r in all_records if r["no"] == entry_no]


def search_by_keyword(keyword: str) -> list:
    """按关键词检索(在首句或概念标中找)"""
    all_records = load_all_lines()
    return [r for r in all_records if keyword in r["first"] or keyword in r["concepts_str"]]


def show_results(results: list, query: str, mode: str):
    if not results:
        print(f"\n❌ 未找到匹配: {query}")
        return
    print(f"\n✅ {mode} 检索:{query}")
    print(f"   命中 {len(results)} 条\n")
    for r in results:
        print(f"  [{r['seg']}] 〔{r['no']}〕")
        print(f"    首句: {r['first'][:70]}")
        print(f"    概念标: {r['concepts_str']}")
        print()


def main():
    if len(sys.argv) < 3:
        print("用法:")
        print("  python search_concepts.py concept <概念名> [段名]")
        print("  python search_concepts.py entry <条号>")
        print("  python search_concepts.py keyword <关键词>")
        print()
        print(f"7 概念: {', '.join(CONCEPTS)}")
        print(f"6 段: {', '.join(SEGMENTS.keys())}")
        sys.exit(1)

    mode = sys.argv[1]
    query = sys.argv[2]
    seg = sys.argv[3] if len(sys.argv) > 3 else None

    if mode == "concept":
        if query not in CONCEPTS:
            print(f"⚠️  '{query}' 不在 7 概念清单中,仍按字面检索...")
        results = search_by_concept(query, seg)
        show_results(results, query, "概念")
    elif mode == "entry":
        results = search_by_entry(query)
        show_results(results, query, "条号")
    elif mode == "keyword":
        results = search_by_keyword(query)
        show_results(results, query, "关键词")
    else:
        print(f"❌ 未知模式: {mode}")


if __name__ == "__main__":
    main()
