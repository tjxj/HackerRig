#!/usr/bin/env python3
"""Step 07f — 导出可审映射表 CSV（纯机械，不调用任何模型）。

把 mapping_<field>.json + distinct_<field>.txt 的频次合成用户可审的 CSV：
  raw, canonical, category, confidence, note, count_all, count_fp
另汇总所有字段的 uncertain 项到 uncertain_all.csv（含 question/options）。
输出 out/07_clean/tables/mapping_<field>.csv + uncertain_all.csv。
用法: python3 -I scripts/07f_export_tables.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "out" / "07_clean"
FIELDS = ["machine", "model", "engine", "quant", "params"]


def counts(field):
    c = {}
    p = DST / f"distinct_{field}.txt"
    if not p.exists():
        return c
    for line in p.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        a, b, v = line.split("\t")
        c[v] = (int(a), int(b))
    return c


def main():
    td = DST / "tables"
    td.mkdir(parents=True, exist_ok=True)
    uncertain_all = []
    for f in FIELDS:
        mp = DST / f"mapping_{f}.json"
        if not mp.exists():
            print(f"SKIP {f} (no mapping yet)")
            continue
        mapping = json.loads(mp.read_text())
        cnt = counts(f)
        with (td / f"mapping_{f}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["raw", "canonical", "category", "confidence", "note", "count_all", "count_fp"])
            for e in sorted(mapping, key=lambda e: -cnt.get(e["raw"], (0, 0))[0]):
                ca, cf = cnt.get(e["raw"], (0, 0))
                w.writerow([e["raw"], e["canonical"], e.get("category", ""),
                            e["confidence"], e.get("note", ""), ca, cf])
        up = DST / f"uncertain_{f}.json"
        if up.exists():
            for e in json.loads(up.read_text()):
                uncertain_all.append({"field": f, **e})
        print(f"{f}: rows={len(mapping)} -> tables/mapping_{f}.csv")
    with (td / "uncertain_all.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "raw", "canonical_proposed", "confidence", "question", "options"])
        for e in uncertain_all:
            w.writerow([e["field"], e["raw"], e.get("canonical", ""), e.get("confidence", ""),
                        e.get("question", ""), " | ".join(e.get("options", []))])
    print(f"uncertain_all: rows={len(uncertain_all)} -> tables/uncertain_all.csv")


if __name__ == "__main__":
    main()