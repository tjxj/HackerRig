#!/usr/bin/env python3
"""Step 04c — 补取父级以上的祖先条目（源数据只读）。

04b 预取的 parents.parquet 只含 S1+S2 的直接父条目；当父条目本身没写
machine/model 需要沿 parent 链再往上追时，用本脚本从源分片补取。
输出: out/04_extract/extra_ancestors.parquet + 可读上下文（与 04b 同格式）。
用法: python3 -I scripts/04c_ancestors.py --ids ids.json [--out context_extra.txt]
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
OUT = ROOT / "out" / "04_extract"
COLS = ["id", "type", "by", "time", "title", "text", "parent"]

A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def clean(t: str) -> str:
    t = html.unescape(t).replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    ids = set(json.loads(Path(a.ids).read_text()))
    parts = []
    for f in sorted(DATA.glob("*.parquet")):
        df = pq.ParquetFile(f).read(columns=COLS).to_pandas()
        parts.append(df[df["id"].isin(ids)])
    p = pd.concat(parts, ignore_index=True).drop_duplicates("id")
    prev = OUT / "extra_ancestors.parquet"
    if prev.exists():
        p = pd.concat([pd.read_parquet(prev), p], ignore_index=True).drop_duplicates("id")
    p.to_parquet(prev, index=False)
    p = p[p["id"].isin(ids)]
    missing = ids - set(p["id"])
    lines = []
    for _, r in p.iterrows():
        kind = "story" if r["type"] == 1 else "comment"
        head = f"----- PARENT id={r['id']} | {kind} | by={r['by']} | time={r['time']} -----"
        body = (f"TITLE: {r['title']}\n" if r["title"] else "") + clean(r["text"])
        lines.append(head + "\n" + body + "\n")
    out_file = Path(a.out) if a.out else OUT / "context_extra.txt"
    out_file.write_text("\n".join(lines))
    print(f"wanted={len(ids)} fetched={len(p)} missing={len(missing)} -> {out_file}")
    if missing:
        print("missing:", sorted(missing))


if __name__ == "__main__":
    main()
