#!/usr/bin/env python3
"""Step 04a — 生成精读批次文件（S1 在前、S2 在后，各按时间排序，每批 40 条）。

显示文本 = clean(原始HTML)：unescape 实体、<p>→换行、<a>→「文本 (url)」、去其余标签。
审计（05）用同一 clean 函数重算规范文本，证据引用必须是其子串（空白归一后）。
输出: out/04_extract/batches/batch_NNN.txt + batches_manifest.json
用法: python3 -I scripts/04a_batches.py
"""
import html
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / "out" / "03_tier" / "tiered.parquet"
OUT = ROOT / "out" / "04_extract" / "batches"
BATCH_SIZE = 40

A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def clean(t: str) -> str:
    t = html.unescape(t).replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    h = pd.read_parquet(IN)
    s1 = h[h["tier"] == "S1"].sort_values(["time", "id"])
    s2 = h[h["tier"] == "S2"].sort_values(["time", "id"])
    order = pd.concat([s1, s2], ignore_index=True)
    manifest = {"total": len(order), "batch_size": BATCH_SIZE, "batches": []}
    for bi in range((len(order) + BATCH_SIZE - 1) // BATCH_SIZE):
        chunk = order.iloc[bi * BATCH_SIZE:(bi + 1) * BATCH_SIZE]
        lines = [f"===== BATCH {bi+1:03d} | comments {bi*BATCH_SIZE+1}-{bi*BATCH_SIZE+len(chunk)} of {len(order)} =====\n"]
        ids = []
        for j, (_, r) in enumerate(chunk.iterrows(), start=bi * BATCH_SIZE + 1):
            ids.append(int(r["id"]))
            lines.append(
                f"----- [{j}] id={r['id']} | {r['month']} | by={r['by']} | time={r['time']} "
                f"| parent={r['parent']} | tier={r['tier']} -----\n"
                f"https://news.ycombinator.com/item?id={r['id']}\n"
                + clean(r["text"]) + "\n")
        name = f"batch_{bi+1:03d}.txt"
        (OUT / name).write_text("\n".join(lines))
        manifest["batches"].append({"file": name, "n": len(chunk), "ids": ids})
    (OUT / "batches_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"total={len(order)} (S1={len(s1)}, S2={len(s2)}) batches={len(manifest['batches'])} -> {OUT}")


if __name__ == "__main__":
    main()