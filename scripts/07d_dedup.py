#!/usr/bin/env python3
"""Step 07d — 同作者重复报告去重分析（纯机械，不调用任何模型，不删记录）。

规则（用户）：同一个人重复报的同一组数只算一次；统计只用亲测(first_person=true)。
按 (by, machine, model, 速度签名) 分组亲测记录，>1 的组视为重复候选；
速度签名：有具体 speed_value 用 (value, unit)；区间/上下界(speed_value=null)用 speed_raw 里
的实际数字元组+unit，避免把不同区间误并成同一组；无速度数字的记录各自独立、不去重。
每组保留 time 最早的一条为 keep，其余标 duplicate（dup_of=keep record_id）。
只打标，不删记录；统计在去重后的亲测集上做。附各条 quant/context/concurrency/comment 供用户核对。
machine/model 用原文（保守，跨写法变体可能漏并）；具体值相同但 quant/context 不同的组仍列候选交用户核对。
输出 out/07_clean/dedup_groups.json + dedup.txt + dedup_mark.json（record_id→状态）。
用法: python3 -I scripts/07d_dedup.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "06_merge" / "measurements.jsonl"
DST = ROOT / "out" / "07_clean"


def speed_sig(r):
    """速度签名：具体值用值；区间用原文数字元组；无数字则唯一（不去重）。"""
    sv = r.get("speed_value")
    su = r.get("speed_unit")
    if sv is not None:
        return ("v", sv, su)
    raw = r.get("speed_raw") or ""
    nums = tuple(re.findall(r"\d+(?:\.\d+)?", raw))
    if not nums:
        return ("none", r["record_id"])
    return ("raw", nums, su)


def main():
    recs = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    fp = [r for r in recs if r["first_person"] is True]
    groups = defaultdict(list)
    for r in fp:
        key = (r["by"], r.get("machine"), r.get("model"), speed_sig(r))
        groups[key].append(r)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    mark = {}
    out_groups = []
    for key, rs in sorted(dup_groups.items(), key=lambda kv: -len(kv[1])):
        rs_sorted = sorted(rs, key=lambda r: str(r.get("time")))
        keep = rs_sorted[0]
        mark[keep["record_id"]] = {"status": "keep", "dup_of": None}
        members = []
        for r in rs_sorted:
            if r["record_id"] != keep["record_id"]:
                mark[r["record_id"]] = {"status": "duplicate", "dup_of": keep["record_id"]}
            members.append({
                "record_id": r["record_id"], "comment_id": r["comment_id"],
                "time": str(r.get("time")), "hn_url": r["hn_url"],
                "quant": r.get("quant"), "context_length": r.get("context_length"),
                "concurrency": r.get("concurrency"), "speed_raw": r.get("speed_raw"),
                "status": "keep" if r["record_id"] == keep["record_id"] else "duplicate",
            })
        by, ma, mo, sig = key
        out_groups.append({"by": by, "machine": ma, "model": mo,
                           "speed_value": keep.get("speed_value"), "speed_unit": keep.get("speed_unit"),
                           "speed_sig": list(sig) if isinstance(sig, tuple) else sig,
                           "keep": keep["record_id"], "members": members})
    # 非重复的亲测记录也标 keep（便于统计）
    for r in fp:
        mark.setdefault(r["record_id"], {"status": "keep", "dup_of": None})
    (DST / "dedup_groups.json").write_text(json.dumps(out_groups, ensure_ascii=False, indent=2) + "\n")
    (DST / "dedup_mark.json").write_text(json.dumps(mark, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 同作者重复报告候选（同 by+machine+model+速度签名；具体值用值，区间用原文数字；保留最早，其余计重复）",
             "# 仅打标不删；统计用去重后亲测集。请核对 quant/context 是否真为同一组数（不同区间已不再误并）。", ""]
    for g in out_groups:
        lines.append(f"## by={g['by']} | {g['machine']} | {g['model']} | "
                     f"{g['speed_value']} {g['speed_unit']} | keep={g['keep']}")
        for m in g["members"]:
            lines.append(f"   [{m['status']}] {m['record_id']} time={m['time']} "
                         f"quant={m['quant']} ctx={m['context_length']} conc={m['concurrency']} "
                         f"raw={m['speed_raw']!r}")
            lines.append(f"      {m['hn_url']}")
        lines.append("")
    (DST / "dedup.txt").write_text("\n".join(lines) + "\n")
    n_dup = sum(1 for v in mark.values() if v["status"] == "duplicate")
    print(f"first_person_records={len(fp)} dup_groups={len(out_groups)} "
          f"duplicate_records={n_dup} keep_records={len(fp) - n_dup}")
    print(f"-> {DST / 'dedup.txt'}")


if __name__ == "__main__":
    main()