#!/usr/bin/env python3
"""Step 21 — 第九步改前改后对比（纯机械，不调用任何模型）。

对比 before_step9 快照与当前：
  1) 速度统计：总记录/亲测去重/进速度统计条数、全站中位+票数、各类别中位+票数
  2) 焦点模型（Qwen3.8-27B / Qwen3.6-35B-A3B）各类别中位+票数（单卡口径）
  3) 投机配对：组数/快慢、按方法中位（全部配对）
  4) 逐条列出被改标退出速度统计的记录
产出 out/07_clean/step9_compare.json + step9_compare.txt。
用法: python3 -I scripts/21_step9_compare.py   （需在 20/07e/08/14 重跑之后）
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "out" / "07_clean"
CATS = ["Mac", "N卡", "A卡", "统一内存主机", "纯CPU", "SBC", "其他"]
FOCUS = ["Qwen3.8-27B", "Qwen3.6-35B-A3B"]
DEFAULT_COMPARE = "Qwen3.6-27B"  # 网站第三问默认对比模型


def load(p):
    return json.loads(Path(p).read_text())


def single_card_by_cat(path, model):
    recs = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    el = [r for r in recs if r.get("first_person") and r.get("dedup_status") == "keep"
          and r.get("speed_stat") == "include" and r.get("speed_value") is not None
          and r.get("speed_unit") == "tok/s" and r.get("speed_kind") in ("generation", "unspecified")
          and not r.get("speculative") and not r.get("diffusion") and not r.get("stalled")
          and not r.get("multi_card") and r.get("model_canon") == model]
    g = defaultdict(list)
    for r in el:
        g[(r["by"], r.get("machine_canon"), r.get("machine_category"))].append(r["speed_value"])
    cv = defaultdict(list)
    ns = defaultdict(int)
    for (by, mach, cat), vs in g.items():
        cv[cat].append(statistics.median(vs))
        ns[cat] += len(vs)
    return {cat: {"median": round(statistics.median(cv[cat]), 2), "votes": len(cv[cat]), "n_speed": ns[cat]}
            for cat in cv}


def main():
    sb = load(C / "stats_before_step9.json")
    sa = load(C / "stats.json")
    fb = load(C / "step7_findings_before_step9.json")
    fa = load(C / "step7_findings.json")
    out = {}

    out["speed_records"] = {"before": sb["speed_stat_records"], "after": sa["speed_stat_records"]}
    out["overall"] = {"before": [sb["speed_median_overall_tok_s"], sb["speed_median_overall_votes"]],
                      "after": [sa["speed_median_overall_tok_s"], sa["speed_median_overall_votes"]]}
    out["by_cat"] = {}
    for cat in CATS:
        b = sb["speed_median_by_category"].get(cat, {})
        a = sa["speed_median_by_category"].get(cat, {})
        out["by_cat"][cat] = {"before": [b.get("median_tok_s"), b.get("votes")],
                              "after": [a.get("median_tok_s"), a.get("votes")]}
    out["focus_models"] = {}
    for mo in FOCUS:
        b = fb["focus_models"][mo]["by_cat"]
        a = fa["focus_models"][mo]["by_cat"]
        out["focus_models"][mo] = {}
        for cat in CATS:
            bb = b.get(cat, {})
            aa = a.get(cat, {})
            out["focus_models"][mo][cat] = {
                "before": [bb.get("median"), bb.get("votes"), bb.get("n_speed")],
                "after": [aa.get("median"), aa.get("votes"), aa.get("n_speed")]}
    # 网站第三问默认对比模型（单卡口径，直接从 clean 复算）
    db = single_card_by_cat(C / "measurements_clean_before_step9.jsonl", DEFAULT_COMPARE)
    da = single_card_by_cat(C / "measurements_clean.jsonl", DEFAULT_COMPARE)
    out["default_compare_model"] = {"model": DEFAULT_COMPARE, "by_cat": {}}
    for cat in CATS:
        bb = db.get(cat, {})
        aa = da.get(cat, {})
        out["default_compare_model"]["by_cat"][cat] = {
            "before": [bb.get("median"), bb.get("votes"), bb.get("n_speed")],
            "after": [aa.get("median"), aa.get("votes"), aa.get("n_speed")]}
    out["spec"] = {"before": {"pairs": fb["spec_pair_count"], "faster": fb["spec_faster_count"],
                              "slower": fb["spec_slower_count"]},
                   "after": {"pairs": fa["spec_pair_count"], "faster": fa["spec_faster_count"],
                             "slower": fa["spec_slower_count"]}}
    out["spec_by_method"] = {}
    for m, v in fa["spec_by_method"].items():
        bv = fb["spec_by_method"].get(m, {})
        out["spec_by_method"][m] = {"before_n": bv.get("count"), "after_n": v["count"],
                                    "before_all_median": bv.get("all_median"), "after_all_median": v["all_median"]}

    # 逐条改标记录
    dec = load(C / "decided" / "step9_spec_relabel.json")
    rb = {json.loads(l)["record_id"]: json.loads(l)
          for l in (C / "measurements_clean_before_step9.jsonl").read_text().splitlines() if l.strip()}
    out["relabeled"] = []
    for d in dec["relabel"]:
        r = rb[d["record_id"]]
        out["relabeled"].append({"record_id": d["record_id"], "by": d["by"],
                                 "machine": r.get("machine_canon"), "model": r.get("model_canon"),
                                 "speed_value": d["speed_value"], "spec_method": d["spec_method"],
                                 "before_stat": r.get("speed_stat"), "after_stat": "exclude"})

    (C / "step9_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")

    L = []
    L.append("=== 第九步改前改后对比 ===")
    L.append(f"进速度统计条数: {out['speed_records']['before']} -> {out['speed_records']['after']}")
    L.append(f"全站中位(tok/s)/票数: {out['overall']['before']} -> {out['overall']['after']}")
    L.append("\n-- 各类别 中位/票数 --")
    for cat in CATS:
        v = out["by_cat"][cat]
        flag = "" if v["before"] == v["after"] else "  <== 变化"
        L.append(f"  {cat}: {v['before']} -> {v['after']}{flag}")
    L.append("\n-- 焦点模型 各类别 [中位,票数,样本n_speed]（单卡）--")
    for mo in FOCUS:
        L.append(f"  [{mo}]")
        for cat in CATS:
            v = out["focus_models"][mo][cat]
            if v["before"] == [None, None, None] and v["after"] == [None, None, None]:
                continue
            flag = "" if v["before"] == v["after"] else "  <== 变化"
            L.append(f"    {cat}: {v['before']} -> {v['after']}{flag}")
    L.append(f"\n-- 网站默认对比模型 {DEFAULT_COMPARE} 各类别 [中位,票数,样本]（单卡）--")
    for cat in CATS:
        v = out["default_compare_model"]["by_cat"][cat]
        if v["before"] == [None, None, None] and v["after"] == [None, None, None]:
            continue
        flag = "" if v["before"] == v["after"] else "  <== 变化"
        L.append(f"    {cat}: {v['before']} -> {v['after']}{flag}")
    L.append(f"\n-- 投机配对 -- {out['spec']['before']} -> {out['spec']['after']}")
    for m, v in out["spec_by_method"].items():
        L.append(f"  {m}: n {v['before_n']}->{v['after_n']}  全部中位 {v['before_all_median']}->{v['after_all_median']}")
    L.append("\n-- 改标退出速度统计的记录 --")
    for r in out["relabeled"]:
        L.append(f"  {r['record_id']} {r['by']} | {r['machine']} | {r['model']} | {r['speed_value']} tok/s | {r['before_stat']}->{r['after_stat']} ({r['spec_method']})")
    txt = "\n".join(L) + "\n"
    (C / "step9_compare.txt").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
