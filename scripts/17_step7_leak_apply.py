#!/usr/bin/env python3
"""Step 17 — 第七步口径补漏：把人工裁定落成 fields_step7.json（纯机械，不调用任何模型）。

读 out/07_clean/decided/step7_leak_decisions.json（逐条回原文精读后的裁定，含 evidence_quote），
生成 out/07_clean/fields_step7.json：record_id → 补丁字段。
  type=multi → multi_card=True / gpu_count / machine_canon（卡数写进标准名；卡数未指明 gpu_count=null 不推断）
  type=batch → speed_stat=exclude / speed_stat_reason（批量/并发吞吐非单流；含并发数 concurrency）
该补丁由 07e 在 fields_step6.json 之后叠加应用（step7 覆盖 step6），
专治第六步多卡范围只扫 machine 字段、批量并发被区间中点补丁覆盖等漏网。
校验：每条 record_id 必须存在于当前 measurements_clean.jsonl；打印 multi/batch 计数与卡数分布。
用法: python3 -I scripts/17_step7_leak_apply.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "out" / "07_clean"


def main():
    decisions = json.loads((C / "decided" / "step7_leak_decisions.json").read_text())
    recs = {json.loads(l)["record_id"]: json.loads(l)
            for l in (C / "measurements_clean.jsonl").read_text().splitlines() if l.strip()}

    patches = {}
    missing = []
    n_multi = n_batch = 0
    for d in decisions:
        rid = d["record_id"]
        if rid not in recs:
            missing.append(rid)
            continue
        if rid in patches:
            raise SystemExit(f"重复 record_id: {rid}")
        p = {}
        if d["type"] == "multi":
            p["multi_card"] = True
            p["gpu_count"] = d.get("gpu_count")  # 未指明 → None，不推断
            p["machine_canon"] = d["machine_canon"]
            n_multi += 1
        elif d["type"] == "batch":
            p["speed_stat"] = "exclude"
            p["speed_stat_reason"] = d["speed_stat_reason"]
            if "concurrency" in d:
                p["concurrency"] = d["concurrency"]
            n_batch += 1
        else:
            raise SystemExit(f"未知 type: {d['type']} ({rid})")
        patches[rid] = p

    if missing:
        raise SystemExit(f"以下 record_id 不存在于 measurements_clean.jsonl: {missing}")

    (C / "fields_step7.json").write_text(json.dumps(patches, ensure_ascii=False, indent=1) + "\n")

    gpu_dist = Counter(str(d.get("gpu_count")) for d in decisions if d["type"] == "multi")
    print("=== 第七步补漏裁定 → fields_step7.json ===")
    print(f"  裁定总数: {len(decisions)}  生成补丁: {len(patches)}")
    print(f"  多卡/多机补标 (multi_card=True): {n_multi}")
    print(f"  批量/并发排除 (speed_stat=exclude): {n_batch}")
    print(f"  多卡卡数分布 (gpu_count): {dict(gpu_dist)}")
    print(f"  缺失 record_id: {len(missing)}")
    print(f"-> {C / 'fields_step7.json'}")


if __name__ == "__main__":
    main()
