#!/usr/bin/env python3
"""Step 14 — 第七步结论数据底稿（纯机械统计，不调用任何模型）。

从 measurements_clean.jsonl 计算 FINDINGS.md 所需的每一个数字与候选原帖：
  1) 全站总体 + 各类别 中位数/票数/样本（全部 eligible，与 stats.json 同口径）
  2) 焦点模型 Qwen3.8-27B / Qwen3.6-35B-A3B：各类别（单卡，与第三问页面同口径）
     + Mac / 单卡4090 / N卡 的逐条候选举例（带 hn_url）
  3) 后悔（first_person + sentiment=regret + keep）按机器类别/机器逐条
  4) 同一人同机器同模型 开关投机解码都报了速度的配对 + 倍率
  5) 反直觉发现的数据支撑（MoE 让 Mac 追平 N卡；投机有时更慢；Strix Halo 后悔集中；长上下文掉速）
产出 out/07_clean/step7_findings.json + step7_findings.txt。
用法: python3 -I scripts/14_step7_findings.py   （需在 07e/08 重跑之后）
"""
import json
import statistics
from collections import defaultdict, Counter
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


def brief(r):
    return {"record_id": r["record_id"], "by": r["by"], "machine": r.get("machine_canon"),
            "category": r.get("machine_category"), "model": r.get("model_canon"),
            "speed_value": r.get("speed_value"), "speed_raw": r.get("speed_raw"),
            "quant": r.get("quant_canon"), "engine": r.get("engine_canon"),
            "context": r.get("context_length"), "multi_card": bool(r.get("multi_card")),
            "speculative": bool(r.get("speculative")), "spec_method": r.get("spec_method"),
            "sentiment": r.get("sentiment"), "hn_url": r.get("hn_url"),
            "summary": r.get("summary_zh")}


def is4090single(r):
    return r.get("machine_canon") == "RTX 4090" and not r.get("multi_card")


def main():
    recs = load(C / "measurements_clean.jsonl")
    fp = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    sp = [r for r in fp if eligible(r)]
    out = {}

    # 1) 全站（全部 eligible，未拆多卡，与 stats.json 同）
    m, v, n = person_median(sp)
    out["site_overall"] = {"median": m, "votes": v, "n_speed": n, "n_fp_keep": len(fp)}
    out["site_by_cat"] = {}
    for cat in CATS:
        cs = [r for r in sp if r.get("machine_category") == cat]
        cm, cv, cn = person_median(cs)
        out["site_by_cat"][cat] = {"median": cm, "votes": cv, "n_speed": cn}

    # 2) 焦点模型（单卡口径，与第三问页面一致）+ 候选举例
    out["focus_models"] = {}
    for mo in FOCUS:
        mfp = [r for r in fp if r.get("model_canon") == mo]
        single = [r for r in mfp if not r.get("multi_card")]
        s_el = [r for r in single if eligible(r)]
        om, ov, on = person_median(s_el)
        block = {"overall_single": {"median": om, "votes": ov, "n_speed": on, "n_total": len(single)},
                 "by_cat": {}, "examples": {}}
        for cat in CATS:
            cs = [r for r in s_el if r.get("machine_category") == cat]
            cm, cv, cn = person_median(cs)
            block["by_cat"][cat] = {"median": cm, "votes": cv, "n_speed": cn}
        # 候选举例：Mac / 单卡4090 / N卡单卡，按速度排序全列（写结论时挑 2-3 条）
        for label, pred in [("Mac", lambda r: r.get("machine_category") == "Mac"),
                            ("RTX4090单卡", is4090single),
                            ("N卡单卡", lambda r: r.get("machine_category") == "N卡")]:
            rs = sorted([r for r in s_el if pred(r)], key=lambda r: r["speed_value"])
            block["examples"][label] = [brief(r) for r in rs]
        out["focus_models"][mo] = block

    # 3) 后悔按机器
    reg = [r for r in fp if r.get("sentiment") == "regret"]
    out["regret_total"] = len(reg)
    out["regret_by_cat"] = {}
    for cat in CATS + ["机器未指明"]:
        rs = [r for r in reg if (r.get("machine_category") or "机器未指明") == cat]
        if not rs:
            continue
        out["regret_by_cat"][cat] = {
            "count": len(rs),
            "machines": dict(Counter(r.get("machine_canon") or "未指明" for r in rs)),
            "records": [brief(r) for r in rs]}

    # 3b) 后悔按人（一人多条只算一人）：每类机器多少人报过亲测、其中多少人后悔、比例。
    #     分母=该类 fp+keep 实测的去重人数；分子=该类 fp+keep+regret 的去重人数。卡片仍全列。
    def n_people(rs):
        return len({r["by"] for r in rs})
    out["regret_person"] = {"by_cat": {}, "overall": {}, "strix_halo": {}}
    for cat in CATS + [None]:
        name = cat or "机器未指明"
        pm = [r for r in fp if (r.get("machine_category") or None) == cat]
        pr = [r for r in reg if (r.get("machine_category") or None) == cat]
        m, rr = n_people(pm), n_people(pr)
        out["regret_person"]["by_cat"][name] = {
            "people_measured": m, "people_regret": rr,
            "ratio": round(rr / m, 3) if m else None, "records_regret": len(pr)}
    out["regret_person"]["overall"] = {
        "people_measured": n_people(fp), "people_regret": n_people(reg),
        "ratio": round(n_people(reg) / n_people(fp), 3) if fp else None}
    sm = [r for r in fp if r.get("machine_canon") == "Strix Halo"]
    sr = [r for r in reg if r.get("machine_canon") == "Strix Halo"]
    out["regret_person"]["strix_halo"] = {
        "people_measured": n_people(sm), "people_regret": n_people(sr),
        "ratio": round(n_people(sr) / n_people(sm), 3) if sm else None}

    # 4) 投机解码开关配对（第九步收紧：同一人·同机器·同模型·同一条评论 里 ON 与 OFF 都有单流生成 tok/s）
    # 第八步补漏：剔除口径混用的配对（per-slot 速度 vs 整套服务总吞吐），见 decided/step8_spec_decisions.json
    spec_dec = json.loads((C / "decided" / "step8_spec_decisions.json").read_text())
    excl = {(e["by"], e["machine"], e["model"]): e for e in spec_dec.get("exclude_pairs", [])}
    # 第九步：补抽同评论里作者自带、当初未抽成记录的 OFF 速度（仅供配对，不进速度统计）
    supp_dec = json.loads((C / "decided" / "step9_spec_off_supplement.json").read_text())
    g = defaultdict(list)
    for r in fp:
        if r.get("speed_value") is not None and r.get("speed_unit") == "tok/s":
            g[(r["by"], r.get("machine_canon"), r.get("model_canon"), str(r["comment_id"]))].append(r)
    n_supp = 0
    for s in supp_dec.get("off_supplement", []):
        by, cid = s["by"], str(s["comment_id"])
        targets = {(r.get("machine_canon"), r.get("model_canon")) for r in fp
                   if r["by"] == by and str(r["comment_id"]) == cid and r.get("speculative")
                   and r.get("speed_kind") in ("generation", "unspecified")}
        for (mach, mo) in targets:
            grp = g[(by, mach, mo, cid)]
            has_real_off = any((not r.get("speculative")) and r.get("speed_kind") in ("generation", "unspecified")
                               and r.get("speed_stat") == "include" and not r.get("_off_supplement") for r in grp)
            if has_real_off:
                continue
            grp.append({"speed_value": s["off_value"], "speed_unit": "tok/s", "speculative": False,
                        "speed_kind": s.get("speed_kind", "generation"), "speed_stat": "include",
                        "hn_url": f"https://news.ycombinator.com/item?id={cid}", "_off_supplement": True})
            n_supp += 1
    pairs = []
    excluded = []
    for (by, mach, mo, cid), rs in g.items():
        on = [r for r in rs if r.get("speculative") and r.get("speed_kind") in ("generation", "unspecified")]
        off = [r for r in rs if not r.get("speculative")
               and r.get("speed_kind") in ("generation", "unspecified") and r.get("speed_stat") == "include"]
        if not (on and off):
            continue
        if (by, mach, mo) in excl:
            e = excl[(by, mach, mo)]
            excluded.append({"by": by, "machine": mach, "model": mo, "reason": e["reason"],
                             "on_speeds": sorted(r["speed_value"] for r in on),
                             "off_speeds": sorted(r["speed_value"] for r in off)})
            continue
        onv = sorted(r["speed_value"] for r in on)
        offv = sorted(r["speed_value"] for r in off)
        on_med = statistics.median(onv)
        off_med = statistics.median(offv)
        ratio = round(on_med / off_med, 2) if off_med else None
        pairs.append({"by": by, "machine": mach, "model": mo, "comment_id": cid,
                      "on_speeds": onv, "off_speeds": offv,
                      "on_median": on_med, "off_median": off_med, "ratio_on_over_off": ratio,
                      "methods": sorted({r.get("spec_method") or "未注明" for r in on}),
                      "on_links": [r.get("hn_url") for r in on],
                      "off_links": [r.get("hn_url") for r in off],
                      "off_supplemented": any(r.get("_off_supplement") for r in off)})
    pairs.sort(key=lambda p: (p["ratio_on_over_off"] is None, -(p["ratio_on_over_off"] or 0)))
    out["spec_pairs"] = pairs
    out["spec_excluded"] = excluded
    out["spec_off_supplemented"] = n_supp
    out["spec_pair_count"] = len(pairs)
    faster = [p for p in pairs if p["ratio_on_over_off"] and p["ratio_on_over_off"] > 1]
    slower = [p for p in pairs if p["ratio_on_over_off"] and p["ratio_on_over_off"] < 1]
    out["spec_faster_count"] = len(faster)
    out["spec_slower_count"] = len(slower)
    # 4b) 按投机方法聚合倍率（写结论用，避免「MTP 通常 1.5–2× / DFlash 3–5×」这类与配对不符的概括）
    bym = defaultdict(list)
    for p in pairs:
        bym["/".join(p["methods"])].append(p["ratio_on_over_off"])
    out["spec_by_method"] = {}
    for mname, rs in sorted(bym.items()):
        fa = [x for x in rs if x and x > 1]
        sl = [x for x in rs if x and x < 1]
        allv = [x for x in rs if x]
        out["spec_by_method"][mname] = {
            "count": len(rs), "faster": len(fa), "slower": len(sl),
            "ratios": sorted(rs),
            "all_median": round(statistics.median(allv), 2) if allv else None,
            "faster_median": round(statistics.median(fa), 2) if fa else None,
            "faster_range": [min(fa), max(fa)] if fa else None,
            "slower_range": [min(sl), max(sl)] if sl else None}

    # 5) 反直觉数据支撑
    ci = {}
    # 5a) MoE vs dense：Mac/N卡 中位比
    for mo in FOCUS:
        b = out["focus_models"][mo]["by_cat"]
        mac, nk = b["Mac"]["median"], b["N卡"]["median"]
        ci.setdefault("mac_over_nvidia_ratio", {})[mo] = {
            "mac_median": mac, "nvidia_median": nk,
            "ratio": round(mac / nk, 2) if (mac and nk) else None,
            "mac_votes": b["Mac"]["votes"], "nvidia_votes": b["N卡"]["votes"]}
    # 5b) Strix Halo 后悔占比
    strix = [r for r in reg if r.get("machine_canon") == "Strix Halo"]
    ci["strix_halo_regret"] = {"count": len(strix), "of_total": len(reg),
                               "share": round(len(strix) / len(reg), 2) if reg else None}
    # 5c) 投机更慢的配对（已在 spec_pairs，这里列摘要）
    ci["spec_slower_examples"] = [{"by": p["by"], "machine": p["machine"], "model": p["model"],
                                   "on": p["on_speeds"], "off": p["off_speeds"], "ratio": p["ratio_on_over_off"]}
                                  for p in slower]
    out["counter_intuitive"] = ci

    (C / "step7_findings.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    # 可读 txt
    L = []
    L.append("=== 第七步结论数据底稿（中位数 tok/s | 票数 | 样本）===")
    so = out["site_overall"]
    L.append(f"全站总体: {so['median']} (票{so['votes']}, 样本{so['n_speed']}, 亲测去重{so['n_fp_keep']})")
    L.append("## 全站各类别（全部 eligible）")
    for cat in CATS:
        b = out["site_by_cat"][cat]
        L.append(f"  {cat:8} 中位={b['median']} 票={b['votes']} 样本={b['n_speed']}")
    for mo in FOCUS:
        b = out["focus_models"][mo]
        o = b["overall_single"]
        L.append(f"\n## 焦点模型 {mo}（单卡口径）总体 {o['median']} (票{o['votes']}, 样本{o['n_speed']}, 总{o['n_total']})")
        for cat in CATS:
            c = b["by_cat"][cat]
            L.append(f"  {cat:8} 中位={c['median']} 票={c['votes']} 样本={c['n_speed']}")
        for label, exs in b["examples"].items():
            L.append(f"  [{label} 候选 {len(exs)} 条]")
            for e in exs:
                L.append(f"    {e['speed_value']} t/s | {e['machine']} | {e['quant']} | {e['engine']} | ctx={e['context']} | {e['by']} | {e['hn_url']}")
    L.append(f"\n## 后悔按机器（共 {out['regret_total']}）")
    for cat, b in out["regret_by_cat"].items():
        L.append(f"  [{cat}] {b['count']} 条  机器={b['machines']}")
    L.append(f"\n## 投机解码开关配对（{out['spec_pair_count']} 组；更快 {out['spec_faster_count']}，更慢 {out['spec_slower_count']}）")
    for p in pairs:
        L.append(f"  {p['by']} | {p['machine']} | {p['model']} | ON={p['on_speeds']} {p['methods']} OFF={p['off_speeds']} | 倍率={p['ratio_on_over_off']}")
    L.append("\n## 反直觉数据")
    L.append(f"  Mac/N卡 中位比: {json.dumps(ci['mac_over_nvidia_ratio'], ensure_ascii=False)}")
    L.append(f"  Strix Halo 后悔: {ci['strix_halo_regret']}")
    txt = "\n".join(L) + "\n"
    (C / "step7_findings.txt").write_text(txt)
    print(txt)
    print(f"-> {C / 'step7_findings.json'} , {C / 'step7_findings.txt'}")


if __name__ == "__main__":
    main()
