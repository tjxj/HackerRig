#!/usr/bin/env python3
"""Step 07e — 应用归一映射 + 速度口径 + 统计（纯机械，不调用任何模型）。

读 out/06_merge/measurements.jsonl 与 out/07_clean/mapping_<field>.json（已含用户裁定），
给每条记录加 <field>_canon、machine_category、各字段置信度、anomaly_flags、dedup_status、speed_stat。
ms/token 按 speed_decisions.json 换算成 tok/s（保留原值供卡片显示原文）。
统计口径：
  记录计数/类别/Top20 = 亲测(first_person=true) + 去重 keep 的全部卡片。
  速度中位数 = 上述子集中 speed_stat=include 且 tok/s 且 generation/unspecified，
             按「每人每机器每模型一票（取本人中位数）」再取中位数。
输出 out/07_clean/measurements_clean.jsonl + stats.json + top20.txt。
用法: python3 -I scripts/07e_apply_norm.py
"""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "06_merge" / "measurements.jsonl"
DST = ROOT / "out" / "07_clean"
FIELDS = ["machine", "model", "engine", "quant", "params"]


def load_map(field):
    p = DST / f"mapping_{field}.json"
    return {e["raw"]: e for e in json.loads(p.read_text())} if p.exists() else {}


def person_median(recs):
    """每人每机器每模型一票（本人中位数），再取这些票的中位数。"""
    groups = defaultdict(list)
    for r in recs:
        groups[(r["by"], r.get("machine_canon"), r.get("model_canon"))].append(r["speed_value"])
    votes = [statistics.median(v) for v in groups.values()]
    return (round(statistics.median(votes), 2) if votes else None), len(votes)


def main():
    recs = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    maps = {f: load_map(f) for f in FIELDS}
    anomalies = {a["record_id"]: a["flags"] for a in json.loads((DST / "anomalies.json").read_text())}
    mark = json.loads((DST / "dedup_mark.json").read_text())
    sd = json.loads((DST / "speed_decisions.json").read_text())

    n_uncertain_records = 0
    n_converted = 0
    for r in recs:
        used_uncertain = False
        for f in FIELDS:
            raw = r.get(f)
            if raw is None:
                r[f + "_canon"] = None
                r[f + "_conf"] = None
                continue
            e = maps[f].get(raw)
            if e is None:
                r[f + "_canon"] = raw
                r[f + "_conf"] = "unmapped"
            else:
                r[f + "_canon"] = e["canonical"]
                r[f + "_conf"] = e["confidence"]
                if e["confidence"] == "uncertain":
                    used_uncertain = True
        r["machine_category"] = (maps["machine"].get(r["machine"], {}) or {}).get("category") \
            if r.get("machine") is not None else None
        r["anomaly_flags"] = anomalies.get(r["record_id"], [])
        r["dedup_status"] = mark.get(r["record_id"], {}).get("status", "non_fp")
        # 速度口径 + ms/token 换算
        d = sd.get(r["record_id"], {})
        if "convert_to_tok_s" in d:
            r["speed_value_original"] = r.get("speed_value")
            r["speed_unit_original"] = r.get("speed_unit")
            r["speed_value"] = d["convert_to_tok_s"]
            r["speed_unit"] = "tok/s"
            r["speed_converted"] = True
            n_converted += 1
        default = "include" if r.get("speed_value") is not None else "no_speed"
        r["speed_stat"] = d.get("speed_stat", default)
        r["speed_stat_reason"] = d.get("reason", "")
        if used_uncertain:
            n_uncertain_records += 1

    # 第六步新字段默认值（所有记录都带，供前端徽章/口径使用）
    for r in recs:
        r.setdefault("speculative", False)
        r.setdefault("spec_method", None)
        r.setdefault("multi_card", False)
        r.setdefault("gpu_count", None)
        r.setdefault("diffusion", False)
        r.setdefault("stalled", False)
        r.setdefault("range_converted", False)
        r.setdefault("context_supplemented", False)
    # 第六步口径补丁（区间中点 / 扩散 / 0.0 / 投机ON / 多卡 / 批量峰值 / 摘要清洗 / 标准名修正）
    f6p = DST / "fields_step6.json"
    n_f6 = 0
    if f6p.exists():
        f6 = json.loads(f6p.read_text())
        for r in recs:
            p = f6.get(r["record_id"])
            if p:
                r.update(p)
                n_f6 += 1
    # 第七步口径补漏补丁（多卡/多机补标 + 批量/并发排除），在 step6 之后叠加，step7 覆盖 step6
    f7p = DST / "fields_step7.json"
    n_f7 = 0
    if f7p.exists():
        f7 = json.loads(f7p.read_text())
        for r in recs:
            p = f7.get(r["record_id"])
            if p:
                r.update(p)
                n_f7 += 1
    # 第九步投机口径补漏：把开着 MTP 测的速度改标投机解码并退出速度统计，在 step7 之后叠加
    f9p = DST / "fields_step9.json"
    n_f9 = 0
    if f9p.exists():
        f9 = json.loads(f9p.read_text())
        for r in recs:
            p = f9.get(r["record_id"])
            if p:
                r.update(p)
                n_f9 += 1

    (DST / "measurements_clean.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))

    # 记录计数口径：亲测 + 去重 keep
    stat_recs = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    # 速度口径：include + tok/s + generation/unspecified，且非投机ON/扩散/跑不动
    speed_recs = [r for r in stat_recs if r["speed_stat"] == "include"
                  and r.get("speed_value") is not None and r.get("speed_unit") == "tok/s"
                  and r.get("speed_kind") in ("generation", "unspecified")
                  and not r.get("speculative") and not r.get("diffusion") and not r.get("stalled")]
    overall_median, overall_votes = person_median(speed_recs)
    by_cat = {}
    for cat in sorted({r["machine_category"] for r in speed_recs if r.get("machine_category")}):
        m, v = person_median([r for r in speed_recs if r["machine_category"] == cat])
        by_cat[cat] = {"median_tok_s": m, "votes": v}

    stats = {"total_records": len(recs),
             "first_person_records": sum(1 for r in recs if r["first_person"] is True),
             "stat_records_fp_dedup": len(stat_recs),
             "speed_stat_records": len(speed_recs),
             "records_using_uncertain_mapping": n_uncertain_records,
             "ms_converted_records": n_converted,
             "speed_median_basis": "亲测+去重keep+speed_stat=include+tok/s+generation/unspecified，排除投机解码ON/扩散模型/跑不动(0.0)/批量峰值；区间取中点；每人每机器每模型一票(本人中位数)；多卡多机单列",
             "speed_median_overall_tok_s": overall_median,
             "speed_median_overall_votes": overall_votes,
             "speed_median_by_category": by_cat,
             "distinct_canonical": {}, "category_records": {}}
    for f in ["machine", "model", "engine", "quant"]:
        vals = [r[f + "_canon"] for r in stat_recs if r.get(f + "_canon") is not None]
        stats["distinct_canonical"][f] = len(set(vals))
    stats["category_records"] = dict(Counter(r["machine_category"] for r in stat_recs if r.get("machine_category")).most_common())
    stats["step6"] = {
        "fields_patched": n_f6,
        "range_converted": sum(1 for r in recs if r.get("range_converted")),
        "speculative_on": sum(1 for r in recs if r.get("speculative")),
        "diffusion": sum(1 for r in recs if r.get("diffusion")),
        "stalled": sum(1 for r in recs if r.get("stalled")),
        "multi_card": sum(1 for r in recs if r.get("multi_card")),
        "context_supplemented": sum(1 for r in recs if r.get("context_supplemented")),
    }
    stats["step7"] = {
        "fields_patched": n_f7,
        "multi_card_total": sum(1 for r in recs if r.get("multi_card")),
        "batch_excluded_by_step7": sum(1 for rid, p in (json.loads(f7p.read_text()) if f7p.exists() else {}).items()
                                       if p.get("speed_stat") == "exclude"),
    }
    stats["step9"] = {
        "fields_patched": n_f9,
        "spec_relabel_excluded": sum(1 for rid, p in (json.loads(f9p.read_text()) if f9p.exists() else {}).items()
                                     if p.get("speed_stat") == "exclude"),
    }

    def top(field, n=20):
        c = Counter(r[field + "_canon"] for r in stat_recs if r.get(field + "_canon") is not None)
        out = []
        for name, cnt in c.most_common(n):
            entry = {"name": name, "records": cnt}
            if field == "machine":
                cats = Counter(r["machine_category"] for r in stat_recs
                               if r.get("machine_canon") == name and r.get("machine_category"))
                entry["category"] = cats.most_common(1)[0][0] if cats else "其他"
            out.append(entry)
        return out

    stats["top20_machine"] = top("machine")
    stats["top20_model"] = top("model")
    (DST / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")

    lines = ["# 计数=亲测+去重keep全部卡片；速度中位数=include子集(每人每机器每模型一票)",
             f"stat_records={len(stat_recs)} speed_stat_records={len(speed_recs)} "
             f"overall_median={overall_median} tok/s (votes={overall_votes})", ""]
    lines.append("## 各类别速度中位数（tok/s | 票数）")
    for cat, d in by_cat.items():
        lines.append(f"  {cat:<8} {str(d['median_tok_s']):>8}  votes={d['votes']}")
    lines.append("")
    lines.append("## TOP 20 机器（标准名 | 类别 | 记录数）")
    for e in stats["top20_machine"]:
        lines.append(f"  {e['records']:>4}  {e['category']:<8} {e['name']}")
    lines.append("")
    lines.append("## TOP 20 模型（标准名 | 记录数）")
    for e in stats["top20_model"]:
        lines.append(f"  {e['records']:>4}  {e['name']}")
    (DST / "top20.txt").write_text("\n".join(lines) + "\n")

    print(f"total={len(recs)} stat_fp_dedup={len(stat_recs)} speed_stat={len(speed_recs)} "
          f"ms_converted={n_converted} overall_median={overall_median} votes={overall_votes}")
    for f in ["machine", "model", "engine", "quant"]:
        print(f"distinct_canonical_{f}={stats['distinct_canonical'][f]}")
    print("category_records=", stats["category_records"])
    print("speed_median_by_category=", by_cat)
    print("step6=", stats["step6"])
    print("step7=", stats["step7"])
    print("step9=", stats["step9"])
    print(f"-> {DST / 'stats.json'} , {DST / 'top20.txt'}")


if __name__ == "__main__":
    main()
