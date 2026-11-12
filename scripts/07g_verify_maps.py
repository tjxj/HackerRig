#!/usr/bin/env python3
"""Step 07g — 映射表覆盖审计（纯机械，不调用任何模型）。

对每个字段校验 mapping_<field>.json：
  - 条目数 == distinct_<field>.txt 的原始写法数；raw 集合完全一致；无重复 raw
  - confidence 计数、canonical 种数
  - machine：每条必须带合法 category（Mac/N卡/A卡/APU/纯CPU/SBC/其他）
  - uncertain_<field>.json（若存在）条目数与 raw 集合 == mapping 中 uncertain 子集
任何不符以非零退出并打印原因。全部通过打印汇总表。
用法: python3 -I scripts/07g_verify_maps.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "out" / "07_clean"
FIELDS = ["machine", "model", "engine", "quant", "params"]
CATS = {"Mac", "N卡", "A卡", "统一内存主机", "纯CPU", "SBC", "其他"}


def distinct_raws(field):
    raws = []
    for line in (DST / f"distinct_{field}.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        raws.append(line.split("\t")[2])
    return raws


def main():
    ok = True
    rows = []
    for f in FIELDS:
        mp = DST / f"mapping_{f}.json"
        if not mp.exists():
            print(f"FAIL {f}: mapping file missing")
            ok = False
            continue
        mapping = json.loads(mp.read_text())
        raws = distinct_raws(f)
        mraws = [e["raw"] for e in mapping]
        errs = []
        if len(mapping) != len(raws):
            errs.append(f"count {len(mapping)} != distinct {len(raws)}")
        if set(mraws) != set(raws):
            miss = set(raws) - set(mraws)
            extra = set(mraws) - set(raws)
            errs.append(f"raw set mismatch missing={len(miss)} extra={len(extra)}")
        dup = [r for r, c in Counter(mraws).items() if c > 1]
        if dup:
            errs.append(f"duplicate raw={len(dup)}")
        cc = Counter(e["confidence"] for e in mapping)
        canon = len(set(e["canonical"] for e in mapping))
        if f == "machine":
            badcat = [e["raw"] for e in mapping if e.get("category") not in CATS]
            if badcat:
                errs.append(f"invalid/missing category={len(badcat)} e.g. {badcat[:3]}")
        up = DST / f"uncertain_{f}.json"
        ucount = None
        if up.exists():
            unc = json.loads(up.read_text())
            ucount = len(unc)
            map_unc = {e["raw"] for e in mapping if e["confidence"] == "uncertain"}
            if {e["raw"] for e in unc} != map_unc:
                errs.append("uncertain file raw set != mapping uncertain subset")
            if len(unc) != cc["uncertain"]:
                errs.append(f"uncertain count {len(unc)} != mapping {cc['uncertain']}")
        if errs:
            ok = False
            print(f"FAIL {f}: " + "; ".join(errs))
        rows.append((f, len(raws), canon, cc["high"], cc["uncertain"], cc["unmapped"], ucount))
    print("\nfield      distinct  canonical  high  uncertain  unmapped  uncertain_file")
    for f, d, c, h, u, um, uc in rows:
        print(f"{f:<10} {d:>8} {c:>10} {h:>5} {u:>10} {um:>9} {str(uc):>15}")
    if not ok:
        sys.exit(1)
    print("\nALL MAPS VERIFIED: coverage exact, no dup, categories valid, uncertain files consistent.")


if __name__ == "__main__":
    main()
