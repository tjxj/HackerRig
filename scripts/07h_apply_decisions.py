#!/usr/bin/env python3
"""Step 07h — 落地用户第三步裁定（纯机械，不调用任何模型）。

三部分：
 1) 映射：合并 decided/decided_<field>.json（子代理按已接受主题 produced）→ 更新 mapping_<field>.json；
    全局类别改名 APU→统一内存主机；GB10 整机(DGX Spark/Asus GX10)归统一内存主机；
    硬覆盖用户点名项（模型 M7/M9/M11、引擎 vllm-mlx、机器 39 Intel/T10）。原 uncertain 归档清空。
 2) 去重：按用户裁定，6 组算重复（跨评论重报+同句拆条），8 组拆开（同评论不同 ctx/quant）。
    写最终 dedup_mark.json + dedup_final.txt。
 3) 速度口径：card-only 排除、绝对值/极低纳入、ms/token 换算、并发逐条（concurrency_decisions.json）。
    写 speed_decisions.json（record_id→{speed_stat,reason,convert_to_tok_s?}）。
用法: python3 -I scripts/07h_apply_decisions.py
"""
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "out" / "07_clean"
DEC = DST / "decided"
FIELDS = ["machine", "model", "engine", "quant", "params"]
CATS = {"Mac", "N卡", "A卡", "统一内存主机", "纯CPU", "SBC", "其他"}

# 用户点名硬覆盖（最后应用，确保精确）：(field, raw) -> 更新字段
OVERRIDES = {
    ("model", "Qwen 3.6 MoE"): {"canonical": "Qwen3.6-MoE（尺寸未指明）", "note": "M7 用户裁定：不补全，尺寸未指明"},
    ("model", "qwen3.6 moe"): {"canonical": "Qwen3.6-MoE（尺寸未指明）", "note": "M7 用户裁定：不补全，尺寸未指明"},
    ("model", "Qwen 3 A3B instruct"): {"canonical": "Qwen3-A3B（尺寸未指明）", "note": "M7 用户裁定：不补全（可能 Next-80B-A3B），尺寸未指明"},
    ("model", "Qwen Coder 1.5B"): {"canonical": "Qwen-Coder-1.5B（版本未指明）", "note": "M7 用户裁定：不猜 Qwen2.5，版本未指明"},
    ("model", "Muse 30B"): {"canonical": "Muse-30B（变体未指明）", "note": "M7 用户裁定：不补 Glimmer，变体未指明"},
    ("model", "DeepSeek-V4-Flash-DSpark"): {"canonical": "DeepSeek-V4-Flash", "note": "M9 用户裁定：DSpark=DeepSeek 投机解码（同 MTP），并回基础名"},
    ("model", "laguna xs2.1"): {"canonical": "Laguna-XS-2.1", "note": "M11 用户裁定：照原文单列 XS 变体"},
    ("model", "Qwen3-Coder-Next 80B"): {"canonical": "Qwen3-Coder-Next", "note": "M7：Coder-Next 即 80B-A3B，并入既有标准名避免筛选器分裂"},
    ("engine", "vllm-mlx"): {"canonical": "vllm-mlx", "note": "用户裁定：基于 MLX 的独立项目，单列"},
    ("engine", "vLLM-MLX"): {"canonical": "vllm-mlx", "note": "用户裁定：基于 MLX 的独立项目，单列"},
    ("machine", "39 Intel AI PCs"): {"canonical": "Intel AI PC（型号未指明）", "category": "其他", "note": "用户裁定：39 台组网集群，归其他"},
    ("machine", "DGX Spark (Asus)"): {"canonical": "Asus GX10", "category": "统一内存主机", "note": "T10 用户裁定：Asus 整机→GX10，统一内存主机"},
    ("machine", "Nvidia GB10"): {"canonical": "DGX Spark", "category": "统一内存主机", "note": "T10 用户裁定：裸 GB10→DGX Spark，统一内存主机"},
}
GB10_CANON = {"DGX Spark", "Asus GX10"}

# 去重：算重复的 6 组（按 keep record_id）；其余组拆开
KEEP_DEDUP = {"47305022#1", "47844644#1", "46877279#1", "48089417#1", "47296667#4", "47281919#4"}

# 速度口径：只做卡片不进速度统计
CARD_ONLY = {
    "47107002#1": "PS2 3000tok/s 与硬件规格严重不符，不可信",
    "47865140#1": "M4 自相矛盾（称尚未测 27B）",
    "48181931#4": "M5 Max ~1200tok/s 未注 prompt/generation，疑 prefill",
    "48729454#1": "+15token/s 为 MTP 加速增量，非绝对速率",
    "48680043#1": "B200 研究基准，非个人日常实测",
    "49208675#1": "KV260 FPGA tinystories，token=字符非大模型",
    "49208675#2": "KV260 FPGA tinystories，token=字符非大模型",
    "48780871#5": "2x3090 并发32 总吞吐，只做卡片",
    "49216034#3": "2x RTX Pro 6000 约64路总吞吐，只做卡片",
}
ABS_INCLUDE = {
    "47394843#1": "2013 Mac Pro 15.6tok/s 绝对值，照常进",
    "49274153#3": "39 Intel AI PCs ~1tok/s 绝对值，照常进",
    "47845998#1": "单卡 Spark Bonsai 173.3tok/s 绝对值，照常进",
    "46947121#1": "5090 跑 0.6B 1008tok/s 绝对值，照常进",
}
MS_CONVERT = {"47358030#1": 66.0, "46627199#1": 5.8}  # record_id -> ms/token


def part1_mappings():
    print("=== Part 1: 映射合并 + 类别改名 + 硬覆盖 ===")
    DEC.mkdir(exist_ok=True)
    for f in FIELDS:
        mapping = json.loads((DST / f"mapping_{f}.json").read_text())
        idx = {e["raw"]: e for e in mapping}
        unc_raws = {e["raw"] for e in mapping if e["confidence"] == "uncertain"}
        dp = DEC / f"decided_{f}.json"
        if not dp.exists():
            raise SystemExit(f"MISSING {dp} — 子代理尚未产出")
        decided = json.loads(dp.read_text())
        draw = {e["raw"] for e in decided}
        if draw != unc_raws:
            raise SystemExit(f"{f}: decided 覆盖不符 missing={unc_raws - draw} extra={draw - unc_raws}")
        for e in decided:
            t = idx[e["raw"]]
            t["canonical"] = e["canonical"]
            t["confidence"] = "high"
            t["note"] = e.get("note", "")
            if f == "machine":
                t["category"] = e["category"]
        # 全局类别改名 + GB10 归类
        if f == "machine":
            for e in mapping:
                if e.get("category") == "APU":
                    e["category"] = "统一内存主机"
                if e["canonical"] in GB10_CANON:
                    e["category"] = "统一内存主机"
        # 硬覆盖
        for (ff, raw), upd in OVERRIDES.items():
            if ff == f and raw in idx:
                idx[raw].update(upd)
                idx[raw]["confidence"] = "high"
        # 校验
        if f == "machine":
            bad = [e["raw"] for e in mapping if e.get("category") not in CATS]
            if bad:
                raise SystemExit(f"machine 非法类别: {bad[:5]}")
            if any(e.get("category") == "APU" for e in mapping):
                raise SystemExit("machine 仍有 APU 残留")
        (DST / f"mapping_{f}.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
        # 归档原 uncertain，清空活动 uncertain
        up = DST / f"uncertain_{f}.json"
        if up.exists():
            shutil.copy2(up, DEC / f"archive_uncertain_{f}.json")
            up.write_text("[]\n")
        cc = Counter(e["confidence"] for e in mapping)
        canon = len(set(e["canonical"] for e in mapping))
        catline = ""
        if f == "machine":
            catline = " categories=" + str(dict(Counter(e["category"] for e in mapping).most_common()))
        print(f"  {f}: entries={len(mapping)} high={cc['high']} uncertain={cc['uncertain']} "
              f"unmapped={cc['unmapped']} canonical={canon}{catline}")


def part2_dedup():
    print("=== Part 2: 去重最终标记 ===")
    recs = [json.loads(l) for l in (ROOT / "out" / "06_merge" / "measurements.jsonl").read_text().splitlines() if l.strip()]
    fp = [r for r in recs if r["first_person"] is True]
    groups = json.loads((DST / "dedup_groups.json").read_text())
    mark = {r["record_id"]: {"status": "keep", "dup_of": None} for r in fp}
    kept_groups, split_groups = [], []
    for g in groups:
        if g["keep"] in KEEP_DEDUP:
            kept_groups.append(g)
            for m in g["members"]:
                if m["record_id"] != g["keep"]:
                    mark[m["record_id"]] = {"status": "duplicate", "dup_of": g["keep"]}
        else:
            split_groups.append(g)
    (DST / "dedup_mark.json").write_text(json.dumps(mark, ensure_ascii=False, indent=2) + "\n")
    n_dup = sum(1 for v in mark.values() if v["status"] == "duplicate")
    lines = ["# 去重最终裁定：6 组算重复（跨评论重报+同句拆条），8 组拆开（同评论不同 ctx/quant）", ""]
    lines.append("## 算重复（保留最早）")
    for g in kept_groups:
        lines.append(f"  by={g['by']} | {g['machine']} | {g['model']} | keep={g['keep']} | 重复{len(g['members'])-1}条")
    lines.append("")
    lines.append("## 拆开（不同测量，全保留）")
    for g in split_groups:
        lines.append(f"  by={g['by']} | {g['machine']} | {g['model']} | {len(g['members'])}条全保留")
    (DST / "dedup_final.txt").write_text("\n".join(lines) + "\n")
    print(f"  fp={len(fp)} 算重复组={len(kept_groups)} 拆卡组={len(split_groups)} "
          f"duplicate={n_dup} keep={len(fp)-n_dup}")


def part3_speed():
    print("=== Part 3: 速度统计口径 ===")
    recs = {r["record_id"]: r for r in
            (json.loads(l) for l in (ROOT / "out" / "06_merge" / "measurements.jsonl").read_text().splitlines() if l.strip())}
    anomalies = {a["record_id"]: a["flags"] for a in json.loads((DST / "anomalies.json").read_text())}
    sd = {}
    # 优先级（后覆盖前）：极低 → 并发逐条 → ms换算 → 用户点名绝对值纳入 → card-only排除
    # 极低 18 → 纳入
    for rid, fl in anomalies.items():
        if "E_极低" in fl:
            sd[rid] = {"speed_stat": "include", "reason": "极低速度为真实体验，纳入统计"}
    # 并发逐条
    cp = DEC / "concurrency_decisions.json"
    if not cp.exists():
        raise SystemExit(f"MISSING {cp} — 并发分类子代理尚未产出")
    conc = json.loads(cp.read_text())
    n_inc = n_exc = 0
    for c in conc:
        rid = c["record_id"]
        sd[rid] = {"speed_stat": c["speed_stat"], "reason": c.get("reason", "并发逐条裁定")}
        if c["speed_stat"] == "include":
            n_inc += 1
        else:
            n_exc += 1
    # ms/token 换算
    for rid, ms in MS_CONVERT.items():
        conv = round(1000.0 / ms, 2)
        fp = recs[rid]["first_person"] is True
        sd[rid] = {"speed_stat": "include" if fp else "exclude",
                   "reason": f"由 {ms} ms/token 换算为 {conv} tok/s（卡片显示原文）" + ("" if fp else "；非亲测不入统计"),
                   "convert_to_tok_s": conv, "orig_ms_per_token": ms}
    # 用户点名绝对值纳入（覆盖并发裁定）
    for rid, reason in ABS_INCLUDE.items():
        sd[rid] = {"speed_stat": "include", "reason": reason}
    # card-only 排除（最后应用，优先级最高）
    for rid, reason in CARD_ONLY.items():
        sd[rid] = {"speed_stat": "exclude", "reason": reason + "（只做卡片）"}
    (DST / "speed_decisions.json").write_text(json.dumps(sd, ensure_ascii=False, indent=2) + "\n")
    cc = Counter(v["speed_stat"] for v in sd.values())
    print(f"  speed_decisions={len(sd)} include={cc['include']} exclude={cc['exclude']} "
          f"(并发 include={n_inc} exclude={n_exc}; card_only={len(CARD_ONLY)}; ms换算={len(MS_CONVERT)})")


if __name__ == "__main__":
    part1_mappings()
    part2_dedup()
    part3_speed()
    print("DONE -> mapping_*.json / dedup_mark.json / speed_decisions.json")
