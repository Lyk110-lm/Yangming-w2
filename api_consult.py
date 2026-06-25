#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阳明心学咨询 APP - API 服务 (W1 v0.4 加权召回)
=======================================
基于 query_index.py + oral_to_concept.json 包成 HTTP API。
- FastAPI + uvicorn(沙箱已有依赖)
- 端口:5001(避开 5000)
- 端点:/health /concepts /search /consult

W1 v0.4 升级:加权召回 + 多样性
- 概念权重:基于弹药库分布的逆频权重(心即理 214 条 → 0.30,知行合一 12 条 → 1.00)
- 多样性约束:前 5 条尽量覆盖不同概念,避免同概念扎堆
- 多召回 30 条 → 打分排序 → 截断 top_k
"""
import sys
import time
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

# 路径:用脚本所在目录(云电脑和 Railway 容器都通)
WORKDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKDIR))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from query_index import query, CONCEPTS  # noqa: E402

# 加载口语 → 概念映射(过滤 divider 分组键)
ORAL_MAP_PATH = WORKDIR / "oral_to_concept.json"
with open(ORAL_MAP_PATH, "r", encoding="utf-8") as f:
    _raw_map: Dict[str, Any] = json.load(f)
ORAL_MAP: Dict[str, List[str]] = {
    k: v for k, v in _raw_map.items() if isinstance(v, list)
}
# 按 key 长度降序 — 长词优先匹配(避免"我"吞掉"我执行难")
ORAL_KEYS_SORTED = sorted(ORAL_MAP.keys(), key=len, reverse=True)

app = FastAPI(
    title="阳明心学咨询 API",
    description="W1 v0.4 - 口语 → 概念 → 加权召回 → 弹药(770 词/7 概念)",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────── 数据模型 ────────────

class ConsultRequest(BaseModel):
    question: str
    top_k: int = 5


class ComposeRequest(BaseModel):
    question: str
    ammo: List[Dict[str, Any]] = None
    oral_concepts: List[str] = None


# ──────────── 口语 → 概念桥 ────────────

# 概念权重(基于弹药库实际分布的逆频权重)
# 数据:心即理 214 / 致良知 86 / 省察克治 84 / 事上磨练 36 / 格物致知 33 / 万物一体之仁 17 / 知行合一 12
# 逆频 = log(总标数 / 该概念数) 再归一到 [0, 1]
CONCEPT_WEIGHTS = {
    "心即理": 0.30,         # 214 条(超高频,降权)
    "致良知": 0.55,         # 86 条
    "省察克治": 0.55,       # 84 条
    "事上磨练": 0.85,       # 36 条
    "格物致知": 0.85,       # 33 条
    "万物一体之仁": 0.95,   # 17 条
    "知行合一": 1.00,       # 12 条(稀有权,升权)
}


def oral_to_concepts(question: str) -> List[str]:
    """扫用户问题中的口语词,返回对应弹药库概念(去重保序)
    长词优先匹配,避免短词吞掉长词命中
    """
    hits = []
    seen = set()
    for k in ORAL_KEYS_SORTED:  # 已在模块级排序过(长→短)
        if k in question:
            for c in ORAL_MAP[k]:
                if c not in seen:
                    seen.add(c)
                    hits.append(c)
    return hits


def rerank(
    results: List[Dict[str, Any]],
    question: str,
    top_k: int = 5,
    concept_hint: List[str] = None,
) -> List[Dict[str, Any]]:
    """MMR 加权召回 + 多样性强制
    算法:Maximal Marginal Relevance
    公式:score_mmr = λ × 相关度 - (1-λ) × 与已选的最大概念重叠
    - 相关度 = 概念权重 × (1 + 概念命中奖励)
    - λ = 0.6(相关度 60%,多样性 40%)
    - 概念重叠 = 该条覆盖的概念 ∩ 已选弹药的概念 / 该条概念数
    目标:top_k=5 至少覆盖 4 个不同概念
    """
    if not results:
        return results
    concept_hint = concept_hint or []
    concept_hint_set = set(concept_hint)

    # 1) 给每条打分(相关度)
    for r in results:
        concepts_str = r.get("concepts_str", "") + r.get("concepts_csv", "")
        # 1.1 命中概念数
        hit_count = sum(1 for c in concept_hint_set if c in concepts_str)
        all_concepts_in_row = [c for c in CONCEPT_WEIGHTS if c in concepts_str]
        if all_concepts_in_row:
            hit_rate = hit_count / len(all_concepts_in_row)
        else:
            hit_rate = 0.5
        # 1.2 概念权重
        concept_max_w = max(
            (w for c, w in CONCEPT_WEIGHTS.items() if c in concepts_str),
            default=0.5,
        )
        # 1.3 综合相关度
        r["_score"] = round(concept_max_w * (1 + hit_rate), 4)
        r["_concept_w"] = round(concept_max_w, 3)
        r["_hit_rate"] = round(hit_rate, 3)
        r["_concepts_in_row"] = set(c for c in CONCEPT_WEIGHTS if c in concepts_str)

    # 2) MMR 选 top_k
    LAMBDA = 0.6
    selected = []
    remaining = list(results)
    while len(selected) < top_k and remaining:
        if not selected:
            # 第一个按相关度选
            best = max(remaining, key=lambda x: x["_score"])
        else:
            # 后续:惩罚与已选概念重叠
            selected_concepts = set()
            for s in selected:
                selected_concepts |= s.get("_concepts_in_row", set())

            def mmr_score(r):
                relevance = r["_score"]
                r_concepts = r.get("_concepts_in_row", set())
                if r_concepts:
                    overlap = len(r_concepts & selected_concepts) / len(r_concepts)
                else:
                    overlap = 0
                return LAMBDA * relevance - (1 - LAMBDA) * overlap * 2

            best = max(remaining, key=mmr_score)
        selected.append(best)
        remaining.remove(best)

    return selected


def consult_search(question: str, top_k: int = 5) -> Dict[str, Any]:
    """W1 核心:口语 → 概念 → 多召回 30 → 加权排序 → top_k"""
    t0 = time.time()
    oral_concepts = oral_to_concepts(question)

    all_results = []
    seen_keys = set()

    # 1) 口语映射命中的概念 — 每概念多召回 15 条
    for c in oral_concepts[:3]:
        results, _, _, label = query(c, top_k=15)
        for r in results:
            key = (r["seg"], r["no"])
            if key not in seen_keys:
                seen_keys.add(key)
                r["_from_concept"] = c
                all_results.append(r)

    # 2) 兜底:原 query 多召回
    if not all_results:
        results, _, _, label = query(question, top_k=20)
        for r in results:
            r["_from_concept"] = None
        all_results = results

    # 3) 加权重排
    all_results = rerank(all_results, question, top_k=top_k, concept_hint=oral_concepts)
    dt = (time.time() - t0) * 1000

    return {
        "oral_concepts": oral_concepts,
        "ammo": all_results,
        "ammo_count": len(all_results),
        "elapsed_ms": round(dt, 1),
    }


# ──────────── 端点 ────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.4.0",
        "concepts_count": len(CONCEPTS),
        "oral_map_count": len(ORAL_MAP),
        "ammo_db": str(WORKDIR / "entries.db"),
        "timestamp": time.time(),
    }


@app.get("/concepts")
def concepts():
    return {
        "concepts": CONCEPTS,
        "count": len(CONCEPTS),
        "oral_map_keys": list(ORAL_MAP.keys()),
        "oral_map_count": len(ORAL_MAP),
    }


@app.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=200),
    top_k: int = Query(5, ge=1, le=20),
):
    """纯检索(不打口语桥)"""
    t0 = time.time()
    results, mode, query_data, label = query(q, top_k=top_k)
    dt = (time.time() - t0) * 1000
    return {
        "question": q,
        "mode": mode,
        "label": label,
        "query": query_data,
        "elapsed_ms": round(dt, 1),
        "count": len(results),
        "results": results,
    }


@app.post("/consult")
def consult(req: ConsultRequest):
    """W1 阶段:口语 → 弹药(W2 加 LLM)"""
    res = consult_search(req.question, top_k=req.top_k)
    return {
        "question": req.question,
        **res,
        "next_step": "W1 只到弹药;W2 加 LLM,前端拿 ammo 后调 Coze Bot API 触发老李生成 3 段答案",
        "w1_stub_answer": {
            "root": "(W1 占位 - W2 由老李 LLM 生成 1 句共情病根)",
            "quotes": [
                (r["seg"] + "·" + r["no"], r["first"][:60])
                for r in res["ammo"][:3]
            ],
            "action": "(W1 占位 - W2 由老李 LLM 生成今晚 1 招 5 分钟落地动作)",
        },
    }


# ──────────── W3.5 修哥味 3 段生成器 ────────────
def compose_three_segments(question: str, ammo: List[Dict[str, Any]], oral_concepts: List[str]) -> Dict[str, str]:
    """规则引擎 + 弹药嵌入 + 修哥味硬规则
    不依赖外部 LLM,在 W1 API 内自动生成
    返回:病根(1 句共情) + 阳明说(取弹药原文 + 红色高亮) + 落地招(今晚 1 招 5 分钟)
    """
    if not ammo:
        return {
            "root": "这事先放下,今晚先睡一觉,明天再说。",
            "yangming_quote": "心体上不可添一物,圣人亦如此。——《传习录》",
            "action": "今晚 22:30 关手机,试试看。"
        }

    # ── 1) 病根:反差金句 + 共情 ──
    # 修哥味硬规则:反差 + 短句 + 第二人称
    pain = question[:8] if len(question) > 8 else question
    root_templates = {
        "default": f'这事表面是"做不到",根子是你心里有个 <span class="red-highlight">知而不行</span> 的结。阳明说:<span class="red-highlight">未有知而不行者,知而不行,只是未知</span>。',
    }
    # 概念驱动
    if "致良知" in oral_concepts:
        root_templates["zhiliangzhi"] = f'这事你不缺判断,缺的是<span class="red-highlight">敢按心里那点光走一步</span>。阳明说:良知人人具足,不须外面添一分。'
    if "心即理" in oral_concepts:
        root_templates["xinjiili"] = f'你翻来覆去想的那事,<span class="red-highlight">答案就在你心里</span>。阳明说:心即理,无心外之物。'
    if "省察克治" in oral_concepts:
        root_templates["shengcha"] = f'这事表面卡着,实际是<span class="red-highlight">你心里有几个旧念头在打转</span>。阳明说:省察克治,时时去人欲存天理。'
    if "事上磨练" in oral_concepts:
        root_templates["shishang"] = f'这事不是想通的,<span class="red-highlight">是干通的</span>。阳明说:事上磨练,事即道,道即事。'
    if "格物致知" in oral_concepts:
        root_templates["gewu"] = f'这事不用再想了,<span class="red-highlight">去做才知道</span>。阳明说:格物是止至善之功,意之所在便是物。'
    if "万物一体之仁" in oral_concepts:
        root_templates["wanwu"] = f'这事不只是你一个人的事,<span class="red-highlight">对方心里也在打鼓</span>。阳明说:大人者,以天地万物为一体者也。'
    if "知行合一" in oral_concepts:
        root_templates["zhixing"] = f'这事不是"懂了不会",是你<span class="red-highlight">没真懂</span>。阳明说:知是行之始,行是知之成。'

    # 选最匹配的模板(按关键词优先)
    best_root = root_templates["default"]
    for c in oral_concepts:
        key_map = {
            "致良知": "zhiliangzhi", "心即理": "xinjiili", "省察克治": "shengcha",
            "事上磨练": "shishang", "格物致知": "gewu", "万物一体之仁": "wanwu",
            "知行合一": "zhixing"
        }
        k = key_map.get(c)
        if k and k in root_templates:
            best_root = root_templates[k]
            break

    # ── 2) 阳明说:取弹药原文 + 红色高亮 ──
    best = ammo[0]
    # 取弹药第一段,做关键词高亮
    raw_text = best["first"].split("\n")[0][:120]  # 截取首句
    # 红色高亮 7 个概念词
    for c in CONCEPT_WEIGHTS:
        if c in raw_text:
            raw_text = raw_text.replace(c, f'<span class="red-highlight">{c}</span>')
    # 二次高亮:经典金句前缀
    golden_prefixes = ["知是行之始", "未有知而不行者", "心即理", "致良知", "省察克治", "事上磨练", "格物", "良知", "天理", "心外无物"]
    for k in golden_prefixes:
        if k in raw_text and f'<span class="red-highlight">{k}' not in raw_text:
            raw_text = raw_text.replace(k, f'<span class="red-highlight">{k}</span>')
    yangming_quote = f'{raw_text}<br><span class="text-xs text-gray-500">——《传习录》{best["seg"]}·{best["no"]}</span>'

    # ── 3) 落地招:基于概念给 5 分钟动作 ──
    action_templates = {
        "执行/自律": "今晚就 1 件 — 把手机扔客厅,桌面清空,开 25 分钟闹钟。动起来 5 分钟,大脑就懒得停了。",
        "情绪/心理": "拿张纸写下让你内耗的事,逐条问自己:\"这事 3 天后还重要吗?\" 大部分答案都是不。",
        "亲密关系": "今晚对方说啥,你只回一句:\"你刚才说的,我听到了。\" 情绪先接住,道理后面再说。",
        "育儿/亲子": "今晚别问学习,问孩子今天最开心的事。关系顺了,学习才有地儿放。",
        "财务/钱": "今晚 1 件事:打开手机银行,算下你这个月到底花了多少。看见数字,焦虑就停一半。",
        "职场/工作": "今晚把那件最不想干的事切成 3 段,先干第 1 段 5 分钟。心里那个\"等会再说\"会立刻被打破。",
        "身体/健康": "今晚 22:30 上床,关手机。睡不着也行,躺着也管用。身体先松,心才松。",
        "懒/摆烂": "今晚就动 5 分钟 — 倒杯水、走 200 步、把桌上东西归位。摆烂的反面不是勤奋,是动 1 下。",
        "原生家庭": "今晚别再翻旧账。给爸妈/兄弟姐妹发一句\"我今天想起你\"。关系不靠翻旧账修,靠新动作。",
        "死亡/重病/养老": "今晚打个电话,跟那个你想说但没说的亲人说一句\"我在\"。说完就放下。",
        "失败/挫折/被否": "今晚把这次失败写下来,只写 3 行:发生了什么/你学到了什么/下一步是什么。写完关灯。",
        "学习/考试": "今晚把书打开,只看 1 页。看到第 1 段就在心里讲给自己听。讲得出来,才算懂。",
        "现实压力/房子": "今晚关掉房价/工资信息推送。3 天不看,世界没变,你心里先松了。",
        "精神/信仰/命运": "今晚 22:00 关灯,躺着想 1 件你真心想做的事。想到 5 分钟就停。答案会自己冒出来。",
        "人生意义/我是谁": "今晚 1 件事:跟一个人说一句真话。啥都行。意义不是想的,是说出来的。",
        "社交/职场人际": "今晚给那个你想说但没说的人发句\"最近咋样\"。关系不靠维护,靠主动。",
        "情绪高敏/委屈": "今晚把那件让你委屈的事写下来,只写给\"你\"。写完撕掉。给情绪出口,不给人。",
        "比较/攀比/朋友圈": "今晚关朋友圈 3 天。比较停了,焦虑跟着停。",
        "年龄/退休": "今晚数下你手里会做的事。3 件就够 — 你不是老了,你是筛过。",
        "思维模式/自我": "今晚问自己:\"我是不是把简单的事想复杂了?\" 大部分时候,答案是:是。",
        "default": "今晚 1 件 — 把那件最纠结的事写下来,逐条问:\"3 天后还重要吗?\" 选 1 件做,别想整套。"
    }
    # 按口语桥所属场景映射
    q_low = question
    scene = "default"
    scene_keys = [
        ("执行", "执行/自律"), ("拖延", "执行/自律"),
        ("内耗", "情绪/心理"), ("焦虑", "情绪/心理"), ("抑郁", "情绪/心理"), ("控制不住", "情绪/心理"),
        ("对象", "亲密关系"), ("老公", "亲密关系"), ("婆", "亲密关系"), ("分手", "亲密关系"),
        ("孩子", "育儿/亲子"), ("厌学", "育儿/亲子"),
        ("钱", "财务/钱"), ("工资", "财务/钱"),
        ("辞职", "职场/工作"), ("被裁", "职场/工作"), ("工作", "职场/工作"), ("加班", "职场/工作"),
        ("失眠", "身体/健康"), ("身体", "身体/健康"), ("生病", "身体/健康"),
        ("摆烂", "懒/摆烂"), ("懒", "懒/摆烂"),
        ("父亲", "原生家庭"), ("母亲", "原生家庭"), ("父母", "原生家庭"),
        ("去世", "死亡/重病/养老"), ("死", "死亡/重病/养老"), ("病", "死亡/重病/养老"),
        ("失败", "失败/挫折/被否"), ("废了", "失败/挫折/被否"),
        ("学习", "学习/考试"), ("考", "学习/考试"),
        ("房子", "现实压力/房子"), ("房贷", "现实压力/房子"),
        ("信仰", "精神/信仰/命运"), ("命运", "精神/信仰/命运"),
        ("意义", "人生意义/我是谁"), ("活", "人生意义/我是谁"),
        ("社交", "社交/职场人际"), ("人际", "社交/职场人际"),
        ("委屈", "情绪高敏/委屈"),
        ("比较", "比较/攀比/朋友圈"), ("攀比", "比较/攀比/朋友圈"),
        ("35", "年龄/退休"), ("年龄", "年龄/退休"), ("老", "年龄/退休"),
        ("思维", "思维模式/自我"), ("认知", "思维模式/自我"),
    ]
    for kw, sc in scene_keys:
        if kw in q_low:
            scene = sc
            break
    action = action_templates.get(scene, action_templates["default"])

    return {
        "root": best_root,
        "yangming_quote": yangming_quote,
        "action": action,
        "scene": scene,
    }


@app.post("/compose")
def compose(req: ComposeRequest):
    """W3.5:基于问题 + 召回弹药 + 概念,生成修哥味 3 段
    输入:{question, ammo?, oral_concepts?}
    输出:{root, yangming_quote, action, scene}
    """
    # 如果前端不传 ammo,自动走 consult_search 召回
    ammo = req.ammo
    concepts = req.oral_concepts
    if not ammo or not concepts:
        res = consult_search(req.question, top_k=5)
        ammo = res["ammo"]
        concepts = res["oral_concepts"]

    seg = compose_three_segments(req.question, ammo, concepts)
    return {
        "question": req.question,
        "oral_concepts": concepts,
        "ammo_count": len(ammo),
        **seg,
    }


# ──────────── 启动 ────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    print(f"""
┌────────────────────────────────────────────┐
│  阳明心学咨询 API 服务 (W1 v0.4)           │
│  端口:{args.port}                            │
│  文档:http://{args.host}:{args.port}/docs       │
│  数据:SQLite 索引库(342 条/7 概念)          │
│  口语桥:ORAL_MAP({len(ORAL_MAP)} 个口语词)         │
│  加权重排:逆频权重 + 多样性约束               │
│  端点:/health /concepts /search /consult    │
└────────────────────────────────────────────┘
""")
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
