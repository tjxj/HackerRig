#!/usr/bin/env python3
"""Step 13 — 第六步改口径前后对比（纯机械，不调用任何模型）。

读 before 快照 measurements_clean_before_step6.jsonl 与 after measurements_clean.jsonl，
用与 07e 完全相同的「每人每机器每模型一票」中位数引擎，输出：
  1) 全站总体 + 各类别 中位数/票数 改前改后
  2) 第三问两个默认模型（Qwen3.6-27B / Qwen3.6-35B-A3B）各类别 中位数/票数/总条数/速度样本 改前改后
  3) after 的多卡/多机单列行
写 out/07_clean/step6_compare.json + step6_compare.txt。
用法: python3 -I scripts/13_step6_compare.py   （需在 07e/08 重跑之后）
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "out" / "07_clean"
CATS = ["Mac", "N卡", "A卡", "统一内存主机", "纯CPU", "SBC", "其他"]
MODELS = ["Qwen3.6-27B", "Qwen3.6-35B-A3B"]


def load(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def eligible(r):
    return (r["first_person"] is True and r["dedup_status"] == "keep"
            and r.get("speed_stat") == "include" and r.get("speed_value") is not None
            and r.get("speed_unit") == "tok/s" and r.get("speed_kind") in ("generation", "unspecified")
            and not r.get("speculative") and not r.get("diffusion") and not r.get("stalled"))


def person_median(recs):
    # 与网页 app.js personStats 同口径：样本（eligible 记录数）<5 不给中位数。
    g = defaultdict(list)
    for r in recs:
        g[(r["by"], r.get("machine_canon"), r.get("model_canon"))].append(r["speed_value"])
    votes = [statistics.median(v) for v in g.values()]
    med = round(statistics.median(votes), 2) if (votes and len(recs) >= 5) else None
    return med, len(votes)


def stat_block(recs):
    """给定记录全集，返回 总体 + 各类别（全部 eligible，不拆多卡）的中位数/票数/样本/总条数。"""
    fp = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    sp = [r for r in fp if eligible(r)]
    m, v = person_median(sp)
    out = {"overall": {"median": m, "votes": v, "n_speed": len(sp), "n_total": len(fp)}, "by_cat": {}}
    for cat in CATS:
        cs = [r for r in sp if r.get("machine_category") == cat]
        ct = [r for r in fp if r.get("machine_category") == cat]
        cm, cv = person_median(cs)
        out["by_cat"][cat] = {"median": cm, "votes": cv, "n_speed": len(cs), "n_total": len(ct)}
    return out


def model_block(recs, model, split_multi=False):
    fp = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"
          and r.get("model_canon") == model]
    sp = [r for r in fp if eligible(r)]
    if split_multi:
        single = [r for r in sp if not r.get("multi_card")]
        multi = [r for r in sp if r.get("multi_card")]
    else:
        single, multi = sp, []
    m, v = person_median(single)
    fp_single = [r for r in fp if not r.get("multi_card")]
    out = {"overall_single": {"median": m, "votes": v, "n_speed": len(single), "n_total": len(fp_single)},
           "by_cat": {}, "multi_row": None}
    for cat in CATS:
        cs = [r for r in single if r.get("machine_category") == cat]
        ct = [r for r in fp if r.get("machine_category") == cat and not r.get("multi_card")]
        cm, cv = person_median(cs)
        out["by_cat"][cat] = {"median": cm, "votes": cv, "n_speed": len(cs), "n_total": len(ct)}
    if split_multi:
        mm, mv = person_median(multi)
        out["multi_row"] = {"median": mm, "votes": mv, "n_speed": len(multi),
                            "n_total": sum(1 for r in fp if r.get("multi_card"))}
    return out


def fmt(x):
    return "—" if x is None else str(x)


def main():
    before = load(C / "measurements_clean_before_step6.jsonl")
    after = load(C / "measurements_clean.jsonl")
    rep = {"before": stat_block(before), "after": stat_block(after), "models": {}}
    for mo in MODELS:
        # before 快照没有 multi_card 标记 → split 后全部落入单卡，等于改前页面口径；
        # after 拆出单卡类别行 + 多卡单列行，与网页第三问完全一致。
        rep["models"][mo] = {
            "before": model_block(before, mo, split_multi=True),
            "after": model_block(after, mo, split_multi=True),
        }
    (C / "step6_compare.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n")

    L = []
    L.append("=== 第六步改口径前后对比（中位数 tok/s | 票数）===")
    L.append("口径变化：区间取中点进统计；投机解码ON/扩散/0.0跑不动/批量峰值排除；多卡多机单列；DS4→DeepSeek-V4-Flash。")
    L.append("")
    b, a = rep["before"]["overall"], rep["after"]["overall"]
    L.append(f"全站总体: 改前 {fmt(b['median'])} (票{b['votes']}, 速度样本{b['n_speed']})  →  改后 {fmt(a['median'])} (票{a['votes']}, 速度样本{a['n_speed']})")
    L.append("")
    L.append("## 各类别（全部 eligible，未拆多卡）")
    L.append(f"  {'类别':<8} {'改前中位':>8} {'改前票':>6}   {'改后中位':>8} {'改后票':>6}")
    for cat in CATS:
        bb, aa = rep["before"]["by_cat"][cat], rep["after"]["by_cat"][cat]
        L.append(f"  {cat:<8} {fmt(bb['median']):>8} {bb['votes']:>6}   {fmt(aa['median']):>8} {aa['votes']:>6}")
    L.append("")
    for mo in MODELS:
        mb = rep["models"][mo]["before"]
        ms = rep["models"][mo]["after"]
        L.append(f"## 第三问模型 {mo}（类别行=单卡口径，与页面一致；多卡/多机单列）")
        ob, oa = mb["overall_single"], ms["overall_single"]
        L.append(f"  单卡总体: 改前 {fmt(ob['median'])} (票{ob['votes']}, 总{ob['n_total']}条)  →  改后 {fmt(oa['median'])} (票{oa['votes']}, 单卡{oa['n_total']}条)")
        L.append(f"  {'类别':<8} {'改前中位':>8} {'前票':>5} {'前总':>5}   {'改后中位':>8} {'后票':>5} {'后总':>5}")
        for cat in CATS:
            x, y = mb["by_cat"][cat], ms["by_cat"][cat]
            L.append(f"  {cat:<8} {fmt(x['median']):>8} {x['votes']:>5} {x['n_total']:>5}   {fmt(y['median']):>8} {y['votes']:>5} {y['n_total']:>5}")
        mr = ms["multi_row"]
        L.append(f"  [改后·多卡/多机单列行] {fmt(mr['median'])} (票{mr['votes']}, 速度样本{mr['n_speed']}, 总{mr['n_total']}条)")
        L.append("")
    txt = "\n".join(L) + "\n"
    (C / "step6_compare.txt").write_text(txt)
    print(txt)
    print(f"-> {C / 'step6_compare.json'} , {C / 'step6_compare.txt'}")


if __name__ == "__main__":
    main()
