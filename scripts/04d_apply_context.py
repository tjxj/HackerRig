#!/usr/bin/env python3
"""Step 04d — 把父条目上下文补全（context_fills.json）合并进批次抽取结果。

补全判断由人工精读做出、记录在 context_fills.json；本脚本只做机械合并，
不调用任何模型。幂等：重复运行结果不变。
- fills: 写入字段，evidence_source=parent，记录 context_ancestor_id/context_evidence_en
- unfilled: 父链查无此信息，字段保持 null，仅更新摘要说明
- 所列批次全部记录 needs_context=false；统一补 context_ancestor_id 字段（未补为 null）
用法: python3 -I scripts/04d_apply_context.py [--fills out/04_extract/context_fills.json]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "04_extract"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fills", default=str(OUT / "context_fills.json"))
    a = ap.parse_args()
    doc = json.loads(Path(a.fills).read_text())
    fills = {f["record_id"]: f for f in doc["fills"]}
    unfilled = {f["record_id"]: f for f in doc["unfilled"]}
    assert len(fills) == len(doc["fills"]), "duplicate record_id in fills"
    assert len(unfilled) == len(doc["unfilled"]), "duplicate record_id in unfilled"
    assert not (set(fills) & set(unfilled)), "record in both fills and unfilled"
    touched = set(fills) | set(unfilled)
    seen = set()
    n_rec = n_fill = n_unfill = 0
    for name in doc["batches"]:
        bf = OUT / f"{name}.json"
        recs = json.loads(bf.read_text())
        for r in recs:
            rid = r["record_id"]
            assert rid not in seen, f"duplicate record_id {rid}"
            seen.add(rid)
            n_rec += 1
            r.setdefault("context_ancestor_id", None)
            r["needs_context"] = False
            if rid in fills:
                f = fills[rid]
                r.update(f["set"])
                r["evidence_source"] = "parent"
                r["context_ancestor_id"] = f["context_ancestor_id"]
                r["context_evidence_en"] = f["context_evidence_en"]
                r["summary_zh"] = f["summary_zh"]
                n_fill += 1
            elif rid in unfilled:
                r["summary_zh"] = unfilled[rid]["summary_zh"]
                n_unfill += 1
        bf.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n")
    missing = touched - seen
    assert not missing, f"record_ids not found: {sorted(missing)}"
    print(f"batches={len(doc['batches'])} records={n_rec} filled={n_fill} unfilled={n_unfill}")


if __name__ == "__main__":
    main()
