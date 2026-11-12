#!/usr/bin/env python3
"""Step 16 — 第七步口径补漏：全量扫描多卡/批量漏标（只读，不改数据）。

第六步的多卡范围只扫了 machine/machine_canon 两个字段（脚本 11 第 60-61 行），
且 MULTI 正则漏掉「4 RTX Pro 6000」「(4) 3090s」「8xMI300X」「2 7900XT」等常见写法，
卡数只写在原文/摘要里的也没扫到。本脚本对全部记录的完整原文
（machine + machine_canon + evidence_en + summary_zh + context_evidence_en + speed_raw）
做更宽的多卡/批量扫描，列出尚未正确处理的候选，并从源 parquet 取回完整评论供精读。
  多卡候选 = 宽正则命中完整原文 且 当前 multi_card != True
  批量候选 = 批量/并发正则命中 或 concurrency>1，且 speed_stat=include 且 speed_value 非空
输出 out/16_leak/leak_candidates.json + reading_leak.txt（含完整原评论）。
用法: python3 -I scripts/16_step7_leak_scope.py
"""
import html
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
import os
DATA = Path(os.environ.get("HACKERRIG_DATA", str(ROOT / "data" / "2026")))
CLEAN = ROOT / "out" / "07_clean"
MERGE = ROOT / "out" / "06_merge"
OUT = ROOT / "out" / "16_leak"

# 宽多卡正则：覆盖 N×/Nx/N x、(N)、N+显卡名、two/three...of them、dual/双/N台/N卡、NVLink/SLI/并行
MULTI = re.compile(r"""(
    [2-9]\s*[×xX]\s*\w
  | \([2-9]\)\s*\w
  | \b[2-9]\s+(?:RTX|GTX|Radeon|RX\b|MI\d|Instinct|Tesla|A100|H100|V100|L40|3090|4090|5090|3060|7900|6000|R9700|7900XT|Pro\s*6000)
  | \b(?:two|three|four|five|six|seven|eight)\s+(?:of\s+(?:them|these|those|the)|GPUs?|cards?|RTX|GTX|Radeon|RX\b|3090|4090|3060|7900|6000|MI\d)
  | \b(?:dual|double|quad)\s+(?:RTX|GTX|Radeon|RX|3090|4090|3060|GPU|card|\d)
  | (?:双卡|双\s*GPU|两台|三台|四台|两卡|三卡|四卡|八卡|多卡|多\s*GPU|[二两三四五六八]\s*[卡张台路])
  | \b[2-9]\s*(?:GPUs?|cards?|卡|张卡|张|way|路|sockets?)\b
  | (?:multi[\s-]?gpu|SLI|nvlink|crossfire|tensor[\s-]?parallel|pipeline[\s-]?parallel)
  | \b(?:pair\s+of|both\s+cards|a\s+pair\s+of)\b
  | \b[2-9]\s*[×xX]\b
)""", re.I | re.X)

BATCH = re.compile(r"(batch|batched|batching|concurrent|concurrency|并发|累计|cumulative|"
                   r"aggregate|\bagg\b|total\s+throughput|throughput|per\s+slot|"
                   r"\d+\s+users?|\d+\s+requests?|parallel\s+\d|--parallel|峰值|peak|"
                   r"simultaneous|in\s+parallel)", re.I)

A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def clean(t):
    t = html.unescape(t or "").replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def conc_gt1(c):
    if c is None:
        return False
    s = str(c).strip().lower()
    if s in ("", "single request", "single", "1", "none", "null"):
        return False
    m = re.search(r"\d+", s)
    return bool(m) and int(m.group()) > 1


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    recs = [json.loads(l) for l in (CLEAN / "measurements_clean.jsonl").read_text().splitlines() if l.strip()]
    raw = {r["record_id"]: r for r in (json.loads(l) for l in (MERGE / "measurements.jsonl").read_text().splitlines() if l.strip())}

    def full_text(r):
        rr = raw.get(r["record_id"], r)
        return " ".join([
            r.get("machine") or "", r.get("machine_canon") or "",
            " ".join(rr.get("evidence_en") or []), rr.get("summary_zh") or "",
            " ".join(rr.get("context_evidence_en") or []), r.get("speed_raw") or "",
        ])

    multi_cand, batch_cand = [], []
    for r in recs:
        rid = r["record_id"]
        rr = raw.get(rid, r)
        txt = full_text(r)
        base = {"record_id": rid, "by": r.get("by"), "comment_id": r.get("comment_id"),
                "machine": r.get("machine"), "machine_canon": r.get("machine_canon"),
                "category": r.get("machine_category"), "model": r.get("model_canon"),
                "speed_value": r.get("speed_value"), "speed_raw": r.get("speed_raw"),
                "speed_kind": r.get("speed_kind"), "speed_stat": r.get("speed_stat"),
                "multi_card": r.get("multi_card"), "gpu_count": r.get("gpu_count"),
                "concurrency": r.get("concurrency"), "speculative": r.get("speculative"),
                "summary_zh": rr.get("summary_zh"), "evidence_en": rr.get("evidence_en"),
                "context_evidence_en": rr.get("context_evidence_en"), "hn_url": r.get("hn_url"),
                "fp": r.get("first_person"), "dedup": r.get("dedup_status")}
        mm = MULTI.search(txt)
        if mm and not r.get("multi_card"):
            base["match"] = mm.group(0).strip()
            multi_cand.append(base)
        bm = BATCH.search(txt)
        if (bm or conc_gt1(r.get("concurrency"))) and r.get("speed_stat") == "include" and r.get("speed_value") is not None:
            base["match"] = (bm.group(0).strip() if bm else f"concurrency={r.get('concurrency')}")
            batch_cand.append(base)

    # 取回完整原评论
    cids = {c["comment_id"] for c in multi_cand + batch_cand if c.get("comment_id")}
    full = {}
    if cids:
        parts = []
        for f in sorted(DATA.glob("*.parquet")):
            df = pq.ParquetFile(f).read(columns=["id", "by", "text", "parent"]).to_pandas()
            parts.append(df[df["id"].isin(cids)])
        if parts:
            df = pd.concat(parts, ignore_index=True).drop_duplicates("id")
            for _, row in df.iterrows():
                full[int(row["id"])] = clean(row["text"])
    for c in multi_cand + batch_cand:
        c["full_comment"] = full.get(c.get("comment_id"))

    (OUT / "leak_candidates.json").write_text(json.dumps(
        {"multi": multi_cand, "batch": batch_cand}, ensure_ascii=False, indent=1) + "\n")

    lines = [f"########## 多卡候选 ({len(multi_cand)}) ##########"]
    for c in multi_cand:
        lines.append(f"\n----- {c['record_id']} by={c['by']} match={c['match']!r} -----")
        lines.append(f"machine={c['machine']!r} canon={c['machine_canon']!r} cat={c['category']} model={c['model']} "
                     f"speed={c['speed_value']} {c['speed_kind']} stat={c['speed_stat']} fp={c['fp']} dedup={c['dedup']}")
        lines.append(f"summary: {c['summary_zh']}")
        lines.append(f"FULL COMMENT:\n{c['full_comment']}")
    lines.append(f"\n########## 批量候选 ({len(batch_cand)}) ##########")
    for c in batch_cand:
        lines.append(f"\n----- {c['record_id']} by={c['by']} match={c['match']!r} -----")
        lines.append(f"machine={c['machine']!r} canon={c['machine_canon']!r} model={c['model']} "
                     f"speed={c['speed_value']} raw={c['speed_raw']!r} kind={c['speed_kind']} conc={c['concurrency']} fp={c['fp']} dedup={c['dedup']}")
        lines.append(f"summary: {c['summary_zh']}")
        lines.append(f"FULL COMMENT:\n{c['full_comment']}")
    (OUT / "reading_leak.txt").write_text("\n".join(lines))

    print(f"=== 第七步补漏范围扫描（只读）===")
    print(f"  多卡候选（命中宽正则 且 当前非multi）: {len(multi_cand)}")
    print(f"  批量候选（命中批量/并发 且 include 有速度）: {len(batch_cand)}")
    print(f"  涉及不同评论: {len(cids)}")
    print(f"  多卡候选中 亲测+keep: {sum(1 for c in multi_cand if c['fp'] and c['dedup']=='keep')}")
    print(f"  批量候选中 亲测+keep: {sum(1 for c in batch_cand if c['fp'] and c['dedup']=='keep')}")
    print(f"\n  多卡候选 by 分布:")
    from collections import Counter
    for by, n in Counter(c['by'] for c in multi_cand).most_common():
        print(f"    {by}: {n}")
    print(f"\n-> {OUT / 'leak_candidates.json'} ; {OUT / 'reading_leak.txt'}")


if __name__ == "__main__":
    main()
