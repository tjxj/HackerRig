#!/usr/bin/env python3
"""Step 03 — 精读前收窄：把 02 的命中按「实测可能性」分层（纯规则，不调模型）。

分层：
  S1: 有数字速度（N t/s、N tokens per second、N ms/token 等）且含 local 或 hw 信号
  S2: 有数字速度，但无 local/hw 信号（机器可能在上下文里，先抽查再定）
  A : 无数字速度，但第一人称经验标记 + llm + (local|hw)（定性亲测）
  J : 疑似招聘帖（jobpost_hint），不参与精读
  R : 其余，暂不精读
去重：正文完全相同的只保留一条（跨帖复制），计数报告。
输出：out/03_tier/{tiered.parquet, counts.json, samples_S1/S2/A.txt}
用法: python3 -I scripts/03_tier.py
"""
import html
import json
import random
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / "out" / "02_coarse" / "hits.parquet"
OUT = ROOT / "out" / "03_tier"
SEED = 42

# 数字速度：数值+单位 或 单位:数值；含 ms/token（记录时保留原单位，不换算）
NUM_SPEED = [
    ("n_tps", r"\d+(?:\.\d+)?\s*(?:t/s|tok/s|tokens?\s*/\s*s(?:ec)?|tps)"),
    ("n_tok_per_s", r"\d+(?:\.\d+)?\s*tokens?\s+(?:per|a)\s+second"),
    ("n_tok_sec", r"\d+(?:\.\d+)?\s*tok\s*/\s*sec"),
    ("n_rev", r"(?:t/s|tok/s|tokens?\s*/\s*s)\s*[:=]\s*\d+(?:\.\d+)?"),
]
NUM_MS = [("n_ms_token", r"\d+(?:\.\d+)?\s*ms\s*(?:per|/)\s*token")]
FIRST_PERSON = [
    ("i_verb", r"\bi\s+(?:run|ran|'m running|am running|get|'m getting|am getting|was getting|got|'ve got|have got|can get|could get|'ve been running|have been running|'ve run|have run|tested|benchmarked|tried|'ve tried|have tried|'m using|am using|use|used|bought|built|set up|installed|downloaded|measured|'m seeing|am seeing|see|saw|noticed|push|pull|managed|'ve had|have had|picked up)\b"),
    ("i_have", r"\bi've\s+(?:run|tested|tried|been|got|had|used|benchmarked|built|set|installed|downloaded|measured|seen|noticed)\b"),
    ("i_can", r"\bi\s+(?:can|could)\s+(?:run|get|push|pull|fit)\b"),
    ("on_my", r"\bon my\b"),
    ("my_hw", r"\bmy\s+(?:box|rig|machine|setup|laptop|desktop|mac|macbook|gpu|gpus|server|hardware|pc|workstation|m[1-5]|rtx|3090|4090|5090|7900|5080|4080|3080|framework|strix|dgx|mac mini|mac studio)\b"),
    ("just_got", r"\bjust\s+(?:got|bought|built|picked up|received|installed)\b"),
    ("for_me", r"\bfor me\b"),
    ("in_my", r"\bin my (?:case|experience|setup|testing|tests)\b"),
]
SPEED_RE = re.compile("|".join(p for _, p in NUM_SPEED + NUM_MS), re.I)
FP_RE = re.compile("|".join(p for _, p in FIRST_PERSON), re.I)

A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def norm(t: str) -> str:
    return html.unescape(t).replace("<p>", "\n")


def clean(t: str) -> str:
    t = norm(t)
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(IN)
    n_in = len(h)
    txt = h["text"].map(norm)
    h["speed_hits"] = [SPEED_RE.findall(t) for t in txt]
    h["n_speed"] = h["speed_hits"].str.len()
    h["has_num_speed"] = h["n_speed"] > 0
    h["fp_hits"] = [FP_RE.findall(t) for t in txt]
    h["first_person"] = h["fp_hits"].str.len() > 0
    h["text_norm"] = txt

    # 完全重复正文去重（保留最早一条）
    h = h.sort_values(["time", "id"])
    dup_mask = h["text"].duplicated(keep="first")
    n_dup = int(dup_mask.sum())
    h["is_dup"] = dup_mask

    live = ~h["is_dup"] & ~h["jobpost_hint"]
    has_lh = h["f_local"] | h["f_hw"]
    h["tier"] = "R"
    h.loc[live & h["has_num_speed"] & has_lh, "tier"] = "S1"
    h.loc[live & h["has_num_speed"] & ~has_lh, "tier"] = "S2"
    h.loc[live & ~h["has_num_speed"] & h["first_person"] & has_lh, "tier"] = "A"
    h.loc[h["jobpost_hint"] & ~h["is_dup"], "tier"] = "J"
    h.loc[h["is_dup"], "tier"] = "DUP"

    counts = {"input_hits": n_in, "exact_text_duplicates": n_dup,
              "jobpost_hint": int((h["jobpost_hint"] & ~h["is_dup"]).sum()),
              "tiers": h["tier"].value_counts().to_dict()}
    stats = {}
    for t in ("S1", "S2", "A"):
        g = h[h["tier"] == t]
        lens = g["text"].str.len()
        stats[t] = {
            "n": len(g),
            "len_mean": int(lens.mean()) if len(g) else 0,
            "len_p50": int(lens.median()) if len(g) else 0,
            "len_p90": int(lens.quantile(0.9)) if len(g) else 0,
            "multi_speed_comments": int((g["n_speed"] >= 2).sum()),
            "with_first_person": int(g["first_person"].sum()),
        }
    counts["tier_stats"] = stats
    (OUT / "counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2))
    h.drop(columns=["speed_hits", "fp_hits"]).to_parquet(OUT / "tiered.parquet", index=False)

    rng = random.Random(SEED)
    for t, k in (("S1", 15), ("S2", 10), ("A", 15)):
        g = h[h["tier"] == t]
        idx = sorted(rng.sample(range(len(g)), min(k, len(g))))
        lines = []
        for _, r in g.iloc[idx].iterrows():
            lines.append(
                f"----- id={r['id']} | {r['month']} | by={r['by']} | tier={t} "
                f"| speed_matches={r['n_speed']} | fp={r['first_person']} -----\n"
                + clean(r["text"]) + "\n")
        (OUT / f"samples_{t}.txt").write_text("\n".join(lines))

    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(f"wrote tiered.parquet({len(h)}) counts.json samples -> {OUT}")


if __name__ == "__main__":
    main()