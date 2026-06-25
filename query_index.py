#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传习录索引查询器 - SQLite 快路径
=================================
共享 rag_query 的意图识别,SQLite 查得毫秒级召回。
"""
import sys
import sqlite3
from pathlib import Path

# 路径:用脚本所在目录(云电脑和 Railway 容器都通)
WORKDIR = Path(__file__).resolve().parent
DB_PATH = WORKDIR / "entries.db"
sys.path.insert(0, str(WORKDIR))
from rag_query import parse_intent  # noqa: E402

# 导入兜底:原 file 解析(慢,但不依赖索引)
from search_concepts import load_all_lines as fallback_load  # noqa: E402

# 7 概念
CONCEPTS = [
    "心即理", "格物致知", "省察克治", "知行合一",
    "致良知", "万物一体", "事上磨练",
]


# 单例 conn(避免每次都新建)
_CONN = None
_PARSE_CACHE = {}


def get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        if not DB_PATH.exists():
            raise FileNotFoundError(f"索引库不存在:{DB_PATH},请先跑 build_index.py --rebuild")
        _CONN = sqlite3.connect(DB_PATH)
        _CONN.execute("PRAGMA journal_mode=WAL")  # 加速读
    return _CONN


def parse_intent_cached(question: str):
    """缓存 parse_intent 结果"""
    if question not in _PARSE_CACHE:
        _PARSE_CACHE[question] = parse_intent(question)
    return _PARSE_CACHE[question]


def rows_to_records(rows) -> list:
    """rows((seg, no, first, concepts_str, concepts_csv), ...) → records list"""
    return [
        {
            "seg": r[0],
            "no": r[1],
            "first": r[2],
            "concepts_str": r[3],
            "concepts_list": [c.strip() for c in r[4].split(",") if c.strip()],
        }
        for r in rows
    ]


def query_index(question: str, top_k: int = 5) -> tuple:
    """主入口:自然语言问题 → (results, mode, query, mode_label)
    走 SQLite 快路径(毫秒级)"""
    intent_type, query_data = parse_intent_cached(question)
    conn = get_conn()
    cur = conn.cursor()

    if intent_type == "entry":
        # 按条号精确
        rows = cur.execute(
            "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE no = ?",
            (query_data,),
        ).fetchall()
        return rows_to_records(rows), intent_type, query_data, f"按条号 〔{query_data}〕"

    if intent_type == "concept_earliest":
        # 某概念按条号找最早
        rows = cur.execute(
            "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE concepts_csv LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT ?",
            (f"%{query_data}%", top_k),
        ).fetchall()
        return rows_to_records(rows), intent_type, query_data, f"按概念『{query_data}』按条号找最早"

    if intent_type == "concept_pair":
        # rag_query 兼容:parse_intent 只返回第一个概念 + mode=concept_pair
        # 第二个概念要从 question 字符串里再扫
        other_concepts = [c for c in CONCEPTS if c in question and c != query_data]
        if not other_concepts:
            # 没有第二个概念,退回 concept_all
            rows = cur.execute(
                "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE concepts_csv LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT ?",
                (f"%{query_data}%", top_k),
            ).fetchall()
            return rows_to_records(rows), "concept_all", query_data, f"按概念『{query_data}』全召回"
        other = other_concepts[0]
        # 2 基线(只标 query) + N 共现(同时标 query 和 other)
        baseline1 = cur.execute(
            "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE concepts_csv LIKE ? AND concepts_csv NOT LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT 1",
            (f"%{query_data}%", f"%{other}%"),
        ).fetchall()
        baseline2 = cur.execute(
            "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE concepts_csv LIKE ? AND concepts_csv NOT LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT 1",
            (f"%{other}%", f"%{query_data}%"),
        ).fetchall()
        co_occur = cur.execute(
            "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE concepts_csv LIKE ? AND concepts_csv LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT ?",
            (f"%{query_data}%", f"%{other}%", top_k),
        ).fetchall()
        all_rows = baseline1 + baseline2 + co_occur
        return rows_to_records(all_rows), intent_type, query_data, f"按概念『{query_data}』和『{other}』共现(补基线)"

    if intent_type == "concept_all":
        # 某概念全召回(限制 top_k)
        rows = cur.execute(
            "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE concepts_csv LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT ?",
            (f"%{query_data}%", top_k),
        ).fetchall()
        return rows_to_records(rows), intent_type, query_data, f"按概念『{query_data}』全召回"

    # keyword:首句 LIKE 或 概念 LIKE
    like = f"%{query_data}%"
    rows = cur.execute(
        "SELECT seg, no, first, concepts_str, concepts_csv FROM entries WHERE first LIKE ? OR concepts_str LIKE ? OR concepts_csv LIKE ? ORDER BY CAST(no AS INTEGER) LIMIT ?",
        (like, like, like, top_k),
    ).fetchall()
    return rows_to_records(rows), intent_type, query_data, f"关键词『{query_data}』"


def fallback_query(question: str, top_k: int = 5) -> tuple:
    """兜底:原 file 解析(慢,但能跑)"""
    from search_concepts import search_by_concept, search_by_entry, search_by_keyword
    intent_type, query_data = parse_intent_cached(question)
    if intent_type == "entry":
        results = search_by_entry(query_data)
        return results, intent_type, query_data, f"按条号 〔{query_data}〕"
    if intent_type == "concept_earliest":
        results = search_by_concept(query_data)[:top_k]
        return results, intent_type, query_data, f"按概念『{query_data}』按条号找最早"
    if intent_type == "concept_pair":
        # rag_query 兼容:parse_intent 只返回第一个概念 + mode=concept_pair
        # 第二个概念要从 question 字符串里再扫
        other_concepts = [c for c in CONCEPTS if c in question and c != query_data]
        if not other_concepts:
            results = search_by_concept(query_data)[:top_k]
            return results, "concept_all", query_data, f"按概念『{query_data}』全召回"
        other = other_concepts[0]
        all_records = load_all_lines()
        b1 = [r for r in all_records if any(query_data in x for x in r["concepts_list"]) and not any(other in x for x in r["concepts_list"])][:1]
        b2 = [r for r in all_records if any(other in x for x in r["concepts_list"]) and not any(query_data in x for x in r["concepts_list"])][:1]
        co = [r for r in all_records if any(query_data in x for x in r["concepts_list"]) and any(other in x for x in r["concepts_list"])][:top_k]
        return b1 + b2 + co, intent_type, query_data, f"按概念『{query_data}』和『{other}』共现(补基线)"
    if intent_type == "concept_all":
        results = search_by_concept(query_data)[:top_k]
        return results, intent_type, query_data, f"按概念『{query_data}』全召回"
    results = search_by_keyword(query_data)[:top_k]
    return results, intent_type, query_data, f"关键词『{query_data}』"


def load_all_lines():
    """暴露给外部的兜底(从 search_concepts 拿)"""
    return fallback_load()


# 给主入口用
def query(question: str, top_k: int = 5, use_index: bool = True) -> tuple:
    """主入口:use_index=True 走 SQLite(快);False 走 file(慢)"""
    if use_index:
        try:
            return query_index(question, top_k)
        except FileNotFoundError:
            print("⚠️  索引库缺失,自动走兜底")
            return fallback_query(question, top_k)
    return fallback_query(question, top_k)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:python query_index.py 问什么")
        sys.exit(1)
    q = " ".join(sys.argv[1:])
    import time
    t0 = time.time()
    results, mode, query, label = query(q)
    dt = (time.time() - t0) * 1000
    print(f"\n🔍 问题:{q}")
    print(f"📌 模式:{label}")
    print(f"⏱️  耗时:{dt:.1f}ms")
    print(f"📚 命中:{len(results)} 条\n")
    for r in results:
        print(f"  〔{r['seg']}·{r['no']}〕 {r['first'][:60]}...  [{r['concepts_str']}]")
