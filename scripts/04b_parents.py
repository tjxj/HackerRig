#!/usr/bin/env python3
"""Step 04b — 父评论上下文库（方案 a：缺 machine/model 时查父评论，单独标注证据）。

默认：预取 S1+S2 全部评论的父条目（可能是评论或 story），存 parents.parquet。
带 --ids 文件（JSON 数组）时：只输出这些 id 的可读上下文文件 context.txt。
父评论的数字绝不混入子评论记录；引用时 evidence_source=parent。
用法: python3 -I scripts/04b_parents.py [--ids needed.json --out context.txt]
"""
import argparse
import html
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
import os
DATA = Path(os.environ.get("HACKERRIG_DATA", str(Path(__file__).resolve().parent.parent / "data" / "2026")))
TIERED = ROOT / "out" / "03_tier" / "tiered.parquet"
OUT = ROOT / "out" / "04_extract"
COLS = ["id", "type", "by", "time", "title", "text", "parent"]

A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def clean(t: str) -> str:
    t = html.unescape(t).replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def fetch_all():
    h = pd.read_parquet(TIERED)
    want = set(h.loc[h["tier"].isin(["S1", "S2"]), "parent"].astype(int))
    want.discard(0)
    parts = []
    for f in sorted(DATA.glob("*.parquet")):
        df = pq.ParquetFile(f).read(columns=COLS).to_pandas()
        parts.append(df[df["id"].isin(want)])
    p = pd.concat(parts, ignore_index=True).drop_duplicates("id")
    p.to_parquet(OUT / "parents.parquet", index=False)
    missing = want - set(p["id"])
    print(f"wanted={len(want)} fetched={len(p)} missing={len(missing)}")
    if missing:
        print("missing ids (父条目不在2026分片内，可能更早):", sorted(missing)[:50])
    (OUT / "parents_missing.json").write_text(json.dumps(sorted(missing)))


def emit(ids_file: Path, out_file: Path):
    ids = set(json.loads(ids_file.read_text()))
    p = pd.read_parquet(OUT / "parents.parquet")
    p = p[p["id"].isin(ids)]
    lines = []
    for _, r in p.iterrows():
        kind = "story" if r["type"] == 1 else "comment"
        head = f"----- PARENT id={r['id']} | {kind} | by={r['by']} | time={r['time']} -----"
        body = (f"TITLE: {r['title']}\n" if r["title"] else "") + clean(r["text"])
        lines.append(head + "\n" + body + "\n")
    out_file.write_text("\n".join(lines))
    print(f"emitted {len(p)} parents -> {out_file}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    ap.add_argument("--out")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.ids:
        emit(Path(a.ids), Path(a.out) if a.out else OUT / "context.txt")
    else:
        fetch_all()