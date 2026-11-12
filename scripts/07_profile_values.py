#!/usr/bin/env python3
"""Step 07a — 清洗归一前的取值摸底（纯机械，不调用任何模型）。

读 out/06_merge/measurements.jsonl，统计 machine/model/engine/quant/params 的
不同取值（distinct）及其记录数、亲测(first_person=true)记录数，按频次排序落盘，
供设计映射表用。另统计作者重复报告候选（同 by + 同 machine/model/speed_value）。
输出 out/07_clean/distinct_<field>.txt + profile.json；终端打印摘要。
用法: python3 -I scripts/07_profile_values.py
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "06_merge" / "measurements.jsonl"
DST = ROOT / "out" / "07_clean"
FIELDS = ["machine", "model", "engine", "quant", "params"]


def main():
    recs = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    DST.mkdir(parents=True, exist_ok=True)
    fp = [r for r in recs if r["first_person"] is True]
    summary = {"records": len(recs), "first_person_true": len(fp),
               "distinct": {}, "first_person_distinct": {}}
    for f in FIELDS:
        c_all = Counter(r[f] for r in recs if r.get(f) is not None)
        c_fp = Counter(r[f] for r in fp if r.get(f) is not None)
        summary["distinct"][f] = len(c_all)
        summary["first_person_distinct"][f] = len(c_fp)
        lines = [f"# {f}: distinct={len(c_all)} (first_person distinct={len(c_fp)}) "
                 f"records_with_value={sum(c_all.values())}",
                 "# count_all\tcount_fp\tvalue"]
        for v, n in c_all.most_common():
            lines.append(f"{n}\t{c_fp.get(v, 0)}\t{v}")
        (DST / f"distinct_{f}.txt").write_text("\n".join(lines) + "\n")

    # 作者重复报告候选：同 by + 同 (machine, model, speed_value, speed_unit)
    groups = defaultdict(list)
    for r in fp:
        key = (r["by"], r.get("machine"), r.get("model"),
               r.get("speed_value"), r.get("speed_unit"))
        groups[key].append(r["record_id"])
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    dup_lines = ["# 同作者+同(machine,model,speed_value,speed_unit) 的重复候选（仅亲测）",
                 "# by\tmachine\tmodel\tspeed_value\tspeed_unit\trecord_ids"]
    for k, v in sorted(dups.items(), key=lambda kv: -len(kv[1])):
        by, ma, mo, sv, su = k
        dup_lines.append(f"{by}\t{ma}\t{mo}\t{sv}\t{su}\t{','.join(v)}")
    (DST / "dup_candidates.txt").write_text("\n".join(dup_lines) + "\n")
    summary["dup_candidate_groups"] = len(dups)
    summary["dup_candidate_records"] = sum(len(v) for v in dups.values())

    (DST / "profile.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"records={len(recs)} first_person_true={len(fp)}")
    for f in FIELDS:
        print(f"distinct_{f}={summary['distinct'][f]} (fp={summary['first_person_distinct'][f]})")
    print(f"dup_candidate_groups={summary['dup_candidate_groups']} "
          f"records={summary['dup_candidate_records']}")
    print(f"-> {DST}")


if __name__ == "__main__":
    main()