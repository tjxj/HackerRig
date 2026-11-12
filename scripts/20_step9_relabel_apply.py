#!/usr/bin/env python3
"""Step 20 — 第九步投机口径补漏：把人工裁定落成 fields_step9.json（纯机械，不调用任何模型）。

读 out/07_clean/decided/step9_spec_relabel.json（逐条回原文精读后的裁定，含 evidence_quote），
生成 out/07_clean/fields_step9.json：record_id → 补丁字段。
  relabel → speculative=True / spec_method / speed_stat=exclude / speed_stat_reason
  （把开着 MTP 测的速度改标投机解码，退出普通速度中位数；用户拍板）
该补丁由 07e 在 fields_step7.json 之后叠加应用（step9 覆盖 step7/step6）。
校验：每条 record_id 必须存在于 measurements_clean.jsonl，且 by / speed_value 与裁定一致。
judged_keep（如 mirekrusin 90，原文未提 MTP，按规矩3不推断）只打印不改标。
用法: python3 -I scripts/20_step9_relabel_apply.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "out" / "07_clean"


def main():
    dec = json.loads((C / "decided" / "step9_spec_relabel.json").read_text())
    recs = {json.loads(l)["record_id"]: json.loads(l)
            for l in (C / "measurements_clean.jsonl").read_text().splitlines() if l.strip()}

    patches = {}
    missing, mismatch = [], []
    for d in dec.get("relabel", []):
        rid = d["record_id"]
        if rid not in recs:
            missing.append(rid)
            continue
        r = recs[rid]
        if r.get("by") != d["by"] or r.get("speed_value") != d["speed_value"]:
            mismatch.append((rid, r.get("by"), r.get("speed_value"), d["by"], d["speed_value"]))
            continue
        if rid in patches:
            raise SystemExit(f"重复 record_id: {rid}")
        m = d["spec_method"]
        patches[rid] = {
            "speculative": True,
            "spec_method": m,
            "speed_stat": "exclude",
            "speed_stat_reason": f"投机解码（{m}）开启测得，不进普通中位数",
        }

    if missing:
        raise SystemExit(f"以下 record_id 不存在于 measurements_clean.jsonl: {missing}")
    if mismatch:
        raise SystemExit(f"by/speed_value 与裁定不一致: {mismatch}")

    (C / "fields_step9.json").write_text(json.dumps(patches, ensure_ascii=False, indent=1) + "\n")

    print("=== 第九步投机补漏裁定 → fields_step9.json ===")
    print(f"  改标投机解码并退出速度统计 (relabel): {len(patches)}")
    for rid, p in patches.items():
        print(f"    {rid} -> {p['spec_method']} / {p['speed_stat']}")
    print(f"  回原文判断后保留非投机 (judged_keep): {len(dec.get('judged_keep', []))}")
    for d in dec.get("judged_keep", []):
        print(f"    {d['record_id']} ({d['by']}, {d['speed_value']}): {d['decision']}")
    print(f"  缺失 record_id: {len(missing)}  不一致: {len(mismatch)}")
    print(f"-> {C / 'fields_step9.json'}")


if __name__ == "__main__":
    main()
