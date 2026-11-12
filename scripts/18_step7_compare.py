#!/usr/bin/env python3
"""Step 18 — 第七步口径补漏 改前改后对比（纯机械，不调用任何模型）。

读 before 快照 measurements_clean_before_step7fix.jsonl 与 after measurements_clean.jsonl，
用与 07e/网页完全相同的「每人每机器每模型一票」中位数引擎，输出：
  1) 全站总体 + 各类别（全部 eligible，含多卡，与 stats.json/结论3 同口径）改前改后
  2) 焦点模型 Qwen3.8-27B / Qwen3.6-35B-A3B 各类别（单卡口径，与第三问页面/结论1·2 同）改前改后
     + 多卡/多机单列行 改前改后
  3) 本次 32 条补丁逐条 改前→改后（multi_card / gpu_count / speed_stat / 是否仍进单卡生成中位数）
写 out/07_clean/step7_compare.json + step7_compare.txt。
用法: python3 -I scripts/18_step7_compare.py   （需在 07e/08/14 重跑之后）
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "out" / "07_clean"
CATS = ["Mac", "N卡", "A卡", "统一内存主机", "纯CPU", "SBC", "其他"]
FOCUS = ["Qwen3.8-27B", "Qwen3.6-35B-A3B"]


def load(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def eligible(r):
    return (r["first_person"] is True and r["dedup_status"] == "keep"
            and r.get("speed_stat") == "include" and r.get("speed_value") is not None
            and r.get("speed_unit") == "tok/s" and r.get("speed_kind") in ("generation", "unspecified")
            and not r.get("speculative") and not r.get("diffusion") and not r.get("stalled"))


def person_median(recs):
    g = defaultdict(list)
    for r in recs:
        g[(r["by"], r.get("machine_canon"), r.get("model_canon"))].append(r["speed_value"])
    votes = [statistics.median(v) for v in g.values()]
    med = round(statistics.median(votes), 2) if (votes and len(recs) >= 5) else None
    return med, len(votes), len(recs)


def site_block(recs):
    fp = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    sp = [r for r in fp if eligible(r)]
    m, v, n = person_median(sp)
    out = {"overall": {"median": m, "votes": v, "n_speed": n}, "by_cat": {}}
    for cat in CATS:
        cm, cv, cn = person_median([r for r in sp if r.get("machine_category") == cat])
        out["by_cat"][cat] = {"median": cm, "votes": cv, "n_speed": cn}
    return out


def model_block(recs, model):
    fp = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"
          and r.get("model_canon") == model]
    sp = [r for r in fp if eligible(r)]
    single = [r for r in sp if not r.get("multi_card")]
    multi = [r for r in sp if r.get("multi_card")]
    om, ov, on = person_median(single)
    out = {"overall_single": {"median": om, "votes": ov, "n_speed": on,
                              "n_total": sum(1 for r in fp if not r.get("multi_card"))},
           "by_cat": {}, "multi_row": None}
    for cat in CATS:
        cm, cv, cn = person_median([r for r in single if r.get("machine_category") == cat])
        out["by_cat"][cat] = {"median": cm, "votes": cv, "n_speed": cn}
    mm, mv, mn = person_median(multi)
    out["multi_row"] = {"median": mm, "votes": mv, "n_speed": mn,
                        "n_total": sum(1 for r in fp if r.get("multi_card"))}
    return out


def fmt(x):
    return "—" if x is None else str(x)


def main():
    before = load(C / "measurements_clean_before_step7fix.jsonl")
    after = load(C / "measurements_clean.jsonl")
    bidx = {r["record_id"]: r for r in before}
    aidx = {r["record_id"]: r for r in after}
    patches = json.loads((C / "fields_step7.json").read_text())

    rep = {"site": {"before": site_block(before), "after": site_block(after)}, "models": {}}
    for mo in FOCUS:
        rep["models"][mo] = {"before": model_block(before, mo), "after": model_block(after, mo)}

    # 逐条补丁 改前→改后
    rows = []
    for rid, p in patches.items():
        b, a = bidx.get(rid, {}), aidx.get(rid, {})
        rows.append({
            "record_id": rid, "by": a.get("by"), "model": a.get("model_canon"),
            "category": a.get("machine_category"), "speed_value": a.get("speed_value"),
            "before_multi": bool(b.get("multi_card")), "after_multi": bool(a.get("multi_card")),
            "before_gpu": b.get("gpu_count"), "after_gpu": a.get("gpu_count"),
            "before_machine_canon": b.get("machine_canon"), "after_machine_canon": a.get("machine_canon"),
            "before_stat": b.get("speed_stat"), "after_stat": a.get("speed_stat"),
            "before_eligible": eligible(b) if b else None, "after_eligible": eligible(a) if a else None,
            "patch": p})
    rep["patched_records"] = rows
    (C / "step7_compare.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n")

    L = []
    L.append("=== 第七步口径补漏 改前改后对比（中位数 tok/s | 票数 | 速度样本）===")
    L.append("口径补漏：多卡/多机只写在原文/摘要的补标 multi_card 单列；批量/并发累计吞吐排除（含被区间中点误覆盖的）。")
    L.append("")
    b, a = rep["site"]["before"]["overall"], rep["site"]["after"]["overall"]
    L.append(f"全站总体: 改前 {fmt(b['median'])} (票{b['votes']}, 样本{b['n_speed']})  →  改后 {fmt(a['median'])} (票{a['votes']}, 样本{a['n_speed']})")
    L.append("")
    L.append("## 全站各类别（全部 eligible，含多卡，与结论3 同口径）")
    L.append(f"  {'类别':<8} {'改前中位':>8} {'前票':>5} {'前样':>5}   {'改后中位':>8} {'后票':>5} {'后样':>5}")
    for cat in CATS:
        x, y = rep["site"]["before"]["by_cat"][cat], rep["site"]["after"]["by_cat"][cat]
        L.append(f"  {cat:<8} {fmt(x['median']):>8} {x['votes']:>5} {x['n_speed']:>5}   {fmt(y['median']):>8} {y['votes']:>5} {y['n_speed']:>5}")
    L.append("")
    for mo in FOCUS:
        mb, ms = rep["models"][mo]["before"], rep["models"][mo]["after"]
        ob, oa = mb["overall_single"], ms["overall_single"]
        L.append(f"## 焦点模型 {mo}（类别行=单卡口径，与结论1·2/页面一致）")
        L.append(f"  单卡总体: 改前 {fmt(ob['median'])} (票{ob['votes']}, 样{ob['n_speed']}, 总{ob['n_total']})  →  改后 {fmt(oa['median'])} (票{oa['votes']}, 样{oa['n_speed']}, 总{oa['n_total']})")
        L.append(f"  {'类别':<8} {'改前中位':>8} {'前票':>5} {'前样':>5}   {'改后中位':>8} {'后票':>5} {'后样':>5}")
        for cat in CATS:
            x, y = mb["by_cat"][cat], ms["by_cat"][cat]
            L.append(f"  {cat:<8} {fmt(x['median']):>8} {x['votes']:>5} {x['n_speed']:>5}   {fmt(y['median']):>8} {y['votes']:>5} {y['n_speed']:>5}")
        xb, xa = mb["multi_row"], ms["multi_row"]
        L.append(f"  [多卡/多机单列行] 改前 {fmt(xb['median'])} (票{xb['votes']}, 样{xb['n_speed']}, 总{xb['n_total']})  →  改后 {fmt(xa['median'])} (票{xa['votes']}, 样{xa['n_speed']}, 总{xa['n_total']})")
        L.append("")
    L.append("## 本次 32 条补丁逐条（改前→改后）")
    L.append(f"  {'record_id':<14} {'by':<16} {'模型':<22} {'速度':>7}  multi前→后  卡数前→后  stat前→后  进单卡生成中位前→后")
    for r in rows:
        L.append(f"  {r['record_id']:<14} {str(r['by']):<16} {str(r['model']):<22} {fmt(r['speed_value']):>7}  "
                 f"{int(r['before_multi'])}→{int(r['after_multi'])}  {fmt(r['before_gpu'])}→{fmt(r['after_gpu'])}  "
                 f"{r['before_stat']}→{r['after_stat']}  {int(bool(r['before_eligible']))}→{int(bool(r['after_eligible']))}")
    txt = "\n".join(L) + "\n"
    (C / "step7_compare.txt").write_text(txt)
    print(txt)
    print(f"-> {C / 'step7_compare.json'} , {C / 'step7_compare.txt'}")


if __name__ == "__main__":
    main()
