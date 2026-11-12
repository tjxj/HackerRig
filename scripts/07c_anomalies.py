#!/usr/bin/env python3
"""Step 07c — 速度异常/增量/存疑候选清单（纯机械检测，不调用任何模型，不自动删）。

读 out/06_merge/measurements.jsonl，按以下旗标挑出候选，附原文证据，交用户定去留：
  A 存疑保留：summary_zh 含「存疑保留」
  B 增量/相对：summary_zh 含「增量/相对/speed-up」或 speed_raw 含 speed-up/faster（非绝对速率）
  C 单位异常：speed_unit == ms/token
  D 高速待核：speed_kind∈{generation,unspecified} 且 speed_value>=1000
  E 极低：speed_kind==generation 且 0<speed_value<1
  F 字符级/非典型：summary_zh 含「字符/char-level/FPGA/KV260/microgpt」
输出 out/07_clean/anomalies.json + anomalies.txt（含原文）；终端只打印计数与 record_id。
用法: python3 -I scripts/07c_anomalies.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "06_merge" / "measurements.jsonl"
DST = ROOT / "out" / "07_clean"


def flags(r):
    s = r.get("summary_zh") or ""
    raw = (r.get("speed_raw") or "").lower()
    sv = r.get("speed_value")
    kind = r.get("speed_kind")
    out = []
    if "存疑保留" in s:
        out.append("A_存疑保留")
    if any(k in s for k in ("增量", "相对")) or "speed-up" in raw or "speed up" in raw:
        out.append("B_增量相对")
    if r.get("speed_unit") == "ms/token":
        out.append("C_单位异常")
    if kind in ("generation", "unspecified") and sv is not None and sv >= 1000:
        out.append("D_高速待核")
    if kind == "generation" and sv is not None and 0 < sv < 1:
        out.append("E_极低")
    if any(k in s for k in ("字符", "char-level", "FPGA", "KV260", "microgpt")):
        out.append("F_字符级非典型")
    return out


def main():
    recs = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    DST.mkdir(parents=True, exist_ok=True)
    flagged = []
    for r in recs:
        fl = flags(r)
        if fl:
            flagged.append({
                "record_id": r["record_id"], "comment_id": r["comment_id"],
                "by": r["by"], "hn_url": r["hn_url"], "flags": fl,
                "machine": r.get("machine"), "model": r.get("model"),
                "speed_raw": r.get("speed_raw"), "speed_value": r.get("speed_value"),
                "speed_unit": r.get("speed_unit"), "speed_kind": r.get("speed_kind"),
                "first_person": r.get("first_person"), "sentiment": r.get("sentiment"),
                "summary_zh": r.get("summary_zh"), "evidence_en": r.get("evidence_en"),
            })
    (DST / "anomalies.json").write_text(json.dumps(flagged, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 速度异常/增量/存疑候选（附原文，用户定去留，未自动删）", ""]
    for f in flagged:
        lines.append(f"## {f['record_id']}  by={f['by']}  flags={','.join(f['flags'])}")
        lines.append(f"   {f['hn_url']}")
        lines.append(f"   machine={f['machine']} | model={f['model']} | "
                     f"speed_raw={f['speed_raw']!r} value={f['speed_value']} "
                     f"{f['speed_unit']}/{f['speed_kind']} | fp={f['first_person']}")
        lines.append(f"   summary: {f['summary_zh']}")
        ev = f["evidence_en"]
        ev = ev if isinstance(ev, list) else [ev]
        for sp in ev:
            lines.append(f"   原文: {sp}")
        lines.append("")
    (DST / "anomalies.txt").write_text("\n".join(lines) + "\n")
    cc = Counter(fl for f in flagged for fl in f["flags"])
    print(f"flagged_records={len(flagged)} (of {len(recs)})")
    for k, v in sorted(cc.items()):
        print(f"  {k}: {v}")
    print("record_ids:", ", ".join(f["record_id"] for f in flagged))
    print(f"-> {DST / 'anomalies.txt'}")


if __name__ == "__main__":
    main()