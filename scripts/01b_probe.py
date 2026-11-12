#!/usr/bin/env python3
"""Step 01b — 校准探针：找几条真实的「本地跑大模型」评论原文，用于校准粗筛词表。

只读数据，输出写到 HackerRig/out/01_profile/probe_local_llm.txt。
用法: python3 -I scripts/01b_probe.py
"""
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import os
DATA = Path(os.environ.get("HACKERRIG_DATA", str(Path(__file__).resolve().parent.parent / "data" / "2026")))
OUT = Path(__file__).resolve().parent.parent / "out" / "01_profile"

TOPIC = re.compile(r"ollama|llama\.cpp|llamafile|lm[ -]?studio|vllm|gguf", re.I)
PERF = re.compile(r"t/s|tok/s|tokens? (per|a) second|vram|\bmac\b|\bgpu\b|3090|4090|5090|m[1-4] (max|ultra|pro)", re.I)

WANT = 8


def main():
    lines = []
    found = 0
    for f in sorted(DATA.glob("*.parquet")):
        df = pq.ParquetFile(f).read(columns=["id", "type", "by", "time", "text", "dead"]).to_pandas()
        c = df[df["type"] == 2]
        mask = c["text"].str.contains(TOPIC) & c["text"].str.contains(PERF)
        for _, row in c[mask].iterrows():
            lines.append(
                f"----- PROBE {f.name} | id={row['id']} | by={row['by']} | time={row['time']} -----\n"
                f"{row['text']}\n"
            )
            found += 1
            if found >= WANT:
                break
        if found >= WANT:
            break
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe_local_llm.txt").write_text("\n".join(lines))
    print(f"found {found} probe comments, wrote {OUT/'probe_local_llm.txt'}")


if __name__ == "__main__":
    main()