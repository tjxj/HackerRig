#!/usr/bin/env python3
"""Step 11 — 第六步改口径前的范围扫描（只读，不改数据）。

快照当前 stats/top20 为 *_before_step6；扫描 measurements_clean.jsonl + 06_merge 原始证据，
列出：区间速度、单边界、投机解码、多卡多机、扩散模型、0.0、摘要加工备注、jaimeyap DS4、
GreenGames 帖。写 out/07_clean/step6_scope.json 供后续脚本/子代理使用。
用法: python3 -I scripts/11_step6_scope.py
"""
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "out" / "07_clean"
MERGE = ROOT / "out" / "06_merge"

RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–~～到至]\s*(\d+(?:\.\d+)?)")
BOUND = re.compile(r"(超过|大于|≥|>=|最高|up to|over|above|at least|小于|低于|under|below|peak|峰值|>|<)", re.I)
SPEC = re.compile(r"(MTP|DFlash|DSpark|EAGLE|draft|speculative|投机|草稿|Medusa|ngram|n-gram|lookahead|spec[\s-]?dec)", re.I)
MULTI = re.compile(r"(2\s*[×xX]\s*|two\s|dual|双|两台|2x|2\s*GPUs?|2\s*cards?|[2-9]\s*×|×\s*[2-9]|multi[\s-]?gpu|SLI|nvlink|2\s+x\s|[2-9]\s*x\s)", re.I)
NOTE = re.compile(r"(根评论|父链|故事标题|由.{0,12}补充|评论\s*\d{5,}|comment\s*\d{5,}|#\d{5,}|补充自|来自父|祖先|父评论)")


def main():
    # 快照 before
    for f in ["stats.json", "top20.txt"]:
        if (CLEAN / f).exists():
            shutil.copy2(CLEAN / f, CLEAN / (f.replace(".", "_before_step6.")))
    recs = [json.loads(l) for l in (CLEAN / "measurements_clean.jsonl").read_text().splitlines() if l.strip()]
    raw = {r["record_id"]: r for r in (json.loads(l) for l in (MERGE / "measurements.jsonl").read_text().splitlines() if l.strip())}

    def ev_text(r):
        rr = raw.get(r["record_id"], r)
        return " ".join(rr.get("evidence_en") or []) + " " + (rr.get("summary_zh") or "") + " " + " ".join(rr.get("context_evidence_en") or [])

    scope = {"ranges": [], "bounds": [], "speculative": [], "multi": [], "diffusion": [],
             "zero": [], "notes": [], "jaimeyap": [], "greengames": [], "tier": dict(Counter(r.get("tier") for r in recs))}

    for r in recs:
        rid = r["record_id"]
        sr = r.get("speed_raw") or ""
        sv = r.get("speed_value")
        kind = r.get("speed_kind")
        txt = ev_text(r)
        # 区间：speed_value null + generation/unspecified + 有 N-N
        if sv is None and kind in ("generation", "unspecified") and RANGE.search(sr) and not BOUND.search(sr):
            m = RANGE.search(sr)
            scope["ranges"].append({"record_id": rid, "speed_raw": sr, "lo": float(m.group(1)), "hi": float(m.group(2)),
                                    "mid": round((float(m.group(1)) + float(m.group(2))) / 2, 2),
                                    "machine": r.get("machine_canon"), "model": r.get("model_canon"), "fp": r["first_person"], "dedup": r["dedup_status"]})
        if sv is None and BOUND.search(sr):
            scope["bounds"].append({"record_id": rid, "speed_raw": sr})
        if SPEC.search(txt):
            scope["speculative"].append({"record_id": rid, "by": r.get("by"), "machine": r.get("machine_canon"),
                                         "model": r.get("model_canon"), "speed_value": sv, "speed_raw": sr,
                                         "speed_stat": r.get("speed_stat"), "summary": r.get("summary_zh"),
                                         "evidence": raw.get(rid, {}).get("evidence_en"), "hn_url": r.get("hn_url")})
        mtext = (r.get("machine") or "") + " " + (r.get("machine_canon") or "")
        if MULTI.search(mtext):
            scope["multi"].append({"record_id": rid, "machine": r.get("machine"), "machine_canon": r.get("machine_canon"),
                                   "category": r.get("machine_category"), "model": r.get("model_canon"), "speed_value": sv})
        if "diffusion" in ((r.get("model_canon") or "") + (r.get("model") or "")).lower():
            scope["diffusion"].append({"record_id": rid, "model": r.get("model_canon"), "speed_value": sv, "speed_stat": r.get("speed_stat")})
        if sv == 0:
            scope["zero"].append({"record_id": rid, "machine": r.get("machine_canon"), "model": r.get("model_canon"), "speed_raw": sr})
        if NOTE.search(r.get("summary_zh") or ""):
            scope["notes"].append({"record_id": rid, "summary": r.get("summary_zh"),
                                   "context_ancestor_id": r.get("context_ancestor_id"), "has_ctx": bool(r.get("context_evidence_en"))})
        if (r.get("by") or "").lower() == "jaimeyap":
            scope["jaimeyap"].append({"record_id": rid, "model": r.get("model"), "model_canon": r.get("model_canon"),
                                      "summary": r.get("summary_zh"), "speed_value": sv})
        if (r.get("by") or "").lower() == "greengames":
            scope["greengames"].append({"record_id": rid, "model": r.get("model_canon"), "speed_value": sv,
                                        "speed_raw": sr, "speed_stat": r.get("speed_stat"), "summary": r.get("summary_zh"),
                                        "evidence": raw.get(rid, {}).get("evidence_en")})

    (CLEAN / "step6_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=1) + "\n")
    print("=== 第六步范围扫描 ===")
    for k in ["ranges", "bounds", "speculative", "multi", "diffusion", "zero", "notes", "jaimeyap", "greengames"]:
        print(f"  {k}: {len(scope[k])}")
    print("  tier:", scope["tier"])
    fp_ranges = [x for x in scope["ranges"] if x["fp"] and x["dedup"] == "keep"]
    print(f"  区间中 亲测+keep: {len(fp_ranges)}（这些取中点后会进统计）")
    print("\n  区间样例:", [(x['speed_raw'], x['mid']) for x in scope["ranges"][:8]])
    print("  多卡样例:", [(x['machine_canon'], x['machine']) for x in scope["multi"][:10]])
    print("  投机样例(by):", dict(Counter(x['by'] for x in scope['speculative']).most_common(10)))
    print("  jaimeyap:", scope["jaimeyap"])
    print("  GreenGames:", [(x['record_id'], x['speed_value'], x['speed_raw']) for x in scope["greengames"]])
    print(f"\n-> {CLEAN / 'step6_scope.json'} ; before 快照 stats_before_step6.json / top20_before_step6.txt")


if __name__ == "__main__":
    main()
