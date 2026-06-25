#!/usr/bin/env python3
"""
传习录 7 概念标表 - RAG 检索器
MVP 第 2 步:自然语言问题 → 意图识别 → 检索召回 → RAG prompt 模板
不依赖外部 LLM;主对话里我直接调用,自己当 LLM 用
"""
import re
import sys
from pathlib import Path

# 复用 search_concepts
sys.path.insert(0, str(Path(__file__).parent))
from search_concepts import search_by_concept, search_by_entry, search_by_keyword, CONCEPTS

# 7 概念清单(同 search_concepts)
CONCEPTS_SET = set(CONCEPTS)


def parse_intent(question: str) -> tuple:
    """
    简单意图识别 → (mode, query)
    mode ∈ {entry, concept_earliest, concept_all, concept_pair, keyword}
    """
    q = question.strip()

    # 1. 条号意图:含"第 X 条"或"X 条"
    m = re.search(r"第\s*(\d+)\s*条", q)
    if m:
        return ("entry", m.group(1))
    m = re.search(r"(\d+)\s*条", q)
    if m:
        return ("entry", m.group(1))

    # 2. 概念意图:问"起源/出现/最早/哪里/提出"
    earliest_kw = ["起源", "出现", "首次", "最早", "哪里", "提出", "源", "始"]
    relation_kw = ["关系", "区别", "联系", "对比", "和", "与"]
    hit_concepts = [c for c in CONCEPTS if c in q]

    if hit_concepts:
        if len(hit_concepts) >= 2 and any(k in q for k in relation_kw):
            # 概念关系类:用第一个概念全召回
            return ("concept_pair", hit_concepts[0])
        if any(k in q for k in earliest_kw):
            return ("concept_earliest", hit_concepts[0])
        return ("concept_all", hit_concepts[0])

    # 3. 关键词兜底:候选关键词 → 优先选阳明高频术语
    stop = set("怎么什么是哪里的了在和与及或为有也啊吗呢吧就是会要把让被什么意思")
    # 阳明确立的高频术语(独立于 7 概念)
    TERMS = {
        "独知", "慎独", "四句教", "无善无恶", "有善有恶", "知善知恶",
        "为善去恶", "格物", "致知", "诚意", "正心", "精金", "龙场",
        "九川", "德洪", "薛侃", "陆澄", "徐爱", "黄省曾",
        "立志", "省察", "克治", "克己", "收敛", "持志", "主一",
        "亲民", "新民", "明明德", "止至善", "良知", "良能",
        "戒惧", "博文约礼", "约礼", "尊德性", "道问学",
        "素位", "中孚", "主忠信", "不欺", "无欲",
    }
    # 先查 TERMS 里有哪个在问题中
    for term in sorted(TERMS, key=len, reverse=True):
        if term in q:
            return ("keyword", term)
    chars = [c for c in q if c not in stop and not re.match(r'[\s,.?!;:\'"\-()\[\]【】《》、。,?!;:]', c)]
    if chars:
        # 生成 2-4 字候选关键词
        candidates = set()
        for n in [2, 3, 4]:
            for i in range(len(chars) - n + 1):
                kw = "".join(chars[i:i+n])
                if kw not in CONCEPTS_SET and kw not in TERMS:
                    candidates.add(kw)
        if candidates:
            # 按召回率(在标表里出现次数)排序,选最优
            from search_concepts import load_all_lines
            records = load_all_lines()
            scored = []
            for kw in candidates:
                hits = sum(1 for r in records if kw in r["first"] or kw in r["concepts_str"])
                scored.append((hits, len(kw), kw))
            scored.sort(key=lambda x: (-x[0], -x[1]))
            best = scored[0][2] if scored and scored[0][0] > 0 else question
            return ("keyword", best)

    return ("keyword", q)


def rag_query(question: str, top_k: int = 5) -> tuple:
    """
    主入口:自然语言问题 → (results, mode, query, mode_label)
    """
    mode, query = parse_intent(question)
    results = []

    if mode == "entry":
        results = search_by_entry(query)
        mode_label = f"按条号 〔{query}〕"
    elif mode == "concept_earliest":
        results = search_by_concept(query)
        results.sort(key=lambda r: int(r["no"]))
        mode_label = f"按概念『{query}』按条号找最早"
    elif mode == "concept_pair":
        # 关系类:召回两概念共现的条
        from search_concepts import load_all_lines
        all_records = load_all_lines()
        # 第二个概念取主问题中除 query 外的另一个 hit_concepts
        other_concepts = [c for c in CONCEPTS if c in question and c != query]
        if other_concepts:
            other = other_concepts[0]
            results = [
                r for r in all_records
                if any(query in x for x in r["concepts_list"])
                and any(other in x for x in r["concepts_list"])
            ]
            # 补充:也召回只标第一个的(取最早 2 条做对比基线)
            single = [r for r in all_records if any(query in x for x in r["concepts_list"])][:2]
            results = single + [r for r in results if r not in single]
            mode_label = f"按概念『{query}』和『{other}』共现(补基线)"
        else:
            results = search_by_concept(query)
            mode_label = f"按概念『{query}』全召回"
    elif mode == "concept_all":
        results = search_by_concept(query)
        mode_label = f"按概念『{query}』全召回"
    else:  # keyword
        results = search_by_keyword(query)
        mode_label = f"关键词『{query}』"

    return results[:top_k], mode, query, mode_label


def format_structured(question: str, results: list, mode_label: str) -> str:
    """结构化召回输出(给主人看)"""
    out = []
    out.append(f"🔍 问题:{question}")
    out.append(f"📌 检索模式:{mode_label}")
    out.append(f"📚 命中:{len(results)} 条")
    out.append("")
    for i, r in enumerate(results, 1):
        out.append(f"  {i}. [{r['seg']}] 〔{r['no']}〕")
        out.append(f"     首句: {r['first'][:70]}")
        out.append(f"     概念标: {r['concepts_str']}")
        out.append("")
    return "\n".join(out)


def format_rag_prompt(question: str, results: list, mode_label: str) -> str:
    """RAG prompt 模板(给 LLM 用,主对话里我自己就是 LLM)"""
    if not results:
        return f"""# 传习录 7 概念标表 RAG 检索
## 问题
{question}
## 检索模式
{mode_label}
## 结果
未在 7 概念标表中找到相关内容。建议:
1. 改写问题,聚焦 7 概念(心即理/格物致知/省察克治/知行合一/致良知/万物一体/事上磨练)
2. 或用具体条号(1-342)精确定位
"""

    prompt = f"""# 传习录 7 概念标表 RAG 检索

## 主人问题
{question}

## 召回条目(共 {len(results)} 条,{mode_label})

"""
    for i, r in enumerate(results, 1):
        prompt += f"""### 召回 {i}: 〔{r['seg']}·{r['no']}〕
- 首句:{r['first']}
- 概念标:{r['concepts_str']}

"""

    prompt += """## 回答要求
- 严格基于召回条目,不引入外部信息
- 引用用 〔段名·条号〕 格式标注
- 回答简洁,移动场景下不长篇
- 如召回不足,明确告知并建议改写问题
"""
    return prompt


def main():
    if len(sys.argv) < 2:
        print("用法:python rag_query.py \"<自然语言问题>\" [top_k]")
        print()
        print("示例:")
        print("  python rag_query.py \"致良知怎么起源\"")
        print("  python rag_query.py \"心即理和致良知的区别\"")
        print("  python rag_query.py \"第 23 条讲什么\"")
        print("  python rag_query.py \"独知是什么意思\"")
        sys.exit(1)

    question = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    results, mode, query, mode_label = rag_query(question, top_k)

    print("=" * 60)
    print(format_structured(question, results, mode_label))
    print("=" * 60)
    print("RAG PROMPT 模板(可直接喂给 LLM):")
    print("=" * 60)
    print(format_rag_prompt(question, results, mode_label))


if __name__ == "__main__":
    main()
