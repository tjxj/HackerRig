#!/usr/bin/env python3
"""Step 10 — 自验收审计（只找问题，不改任何 web/ 文件）。

产出：
  out/10_audit/desktop/*.png , mobile/*.png  （首页/三问结果/后悔页/筛选无结果，各两套）
  out/10_audit/evidence.json                （控制台错误、几何/对比度、对账、异常候选原文）
   stdout 摘要
用法: python3 -I scripts/10_audit_web.py
"""
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = ROOT / "out" / "10_audit"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "desktop").mkdir(exist_ok=True)
(OUT / "mobile").mkdir(exist_ok=True)
INDEX = (WEB / "index.html").as_uri()
REGRET = (WEB / "regret.html").as_uri()
random.seed(20261112)


def load_data():
    raw = (WEB / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))


def eligible(r):
    return (r["first_person"] is True and r["dedup_status"] == "keep" and r["speed_stat"] == "include"
            and r.get("speed_value") is not None and r.get("speed_unit") == "tok/s"
            and r.get("speed_kind") in ("generation", "unspecified"))


def person_stats(recs):
    el = [r for r in recs if eligible(r)]
    g = defaultdict(list)
    for r in el:
        g[(r["by"], r.get("machine_canon") or "", r.get("model_canon") or "")].append(r["speed_value"])
    votes = [statistics.median(v) for v in g.values()]
    return {"n": len(el), "votes": len(votes),
            "median": round(statistics.median(votes), 2) if len(el) >= 5 else None}


def lum(hexstr):
    h = hexstr.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast(fg, bg):
    l1, l2 = sorted([lum(fg), lum(bg)], reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 2)


def main():
    data = load_data()
    meta, recs = data["meta"], data["records"]
    stat = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    by_id = {r["record_id"]: r for r in recs}
    ev = {"console": [], "geometry": {}, "contrast": {}, "reconcile": {}, "anomalies": [], "interaction": {}}

    # 对比度（小字需>=4.5，大字>=3）
    pairs = {
        "muted_on_paper(小字)": ("#6f675a", "#f4efe6"),
        "muted_on_surface(小字)": ("#6f675a", "#faf7f1"),
        "inksoft_on_paper": ("#433e36", "#f4efe6"),
        "barval_paper_on_accent": ("#f4efe6", "#b5451b"),
        "accentink_on_surface": ("#8f3614", "#faf7f1"),
        "na_muted_on_surface": ("#6f675a", "#faf7f1"),
        "catborder_ink_on_paper": ("#1c1b1a", "#f4efe6"),
    }
    ev["contrast"] = {k: contrast(a, b) for k, (a, b) in pairs.items()}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        errors, failed = [], []

        def new_page(width, height):
            ctx = browser.new_context(viewport={"width": width, "height": height})
            pg = ctx.new_page()
            pg.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
            pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
            pg.on("requestfailed", lambda r: failed.append(f"{r.url} :: {r.failure}"))
            return ctx, pg

        def shot(pg, folder, name):
            pg.screenshot(path=str(OUT / folder / f"{name}.png"), full_page=True)

        def overflow(pg):
            return pg.evaluate("({sw:document.documentElement.scrollWidth, iw:window.innerWidth})")

        # ===== 桌面 1280 =====
        ctx, pg = new_page(1280, 900)
        pg.goto(INDEX); pg.wait_for_selector(".compare-grid")
        shot(pg, "desktop", "01_home_compare")
        ev["geometry"]["desktop_home_overflow"] = overflow(pg)
        # 锚点跳转是否落在导航下方
        pg.click("a[href='#basis']"); pg.wait_for_timeout(200)
        basis_top = pg.eval_on_selector("#basis", "e=>e.getBoundingClientRect().top")
        nav_h = pg.eval_on_selector(".nav", "e=>e.getBoundingClientRect().height")
        ev["geometry"]["anchor_basis_top_vs_nav"] = {"basis_top": round(basis_top, 1), "nav_h": round(nav_h, 1)}
        # 口径说明是否重置当前视图（先切到 Q1 选机器，再点口径说明）
        pg.click(".tab[data-view='machine']"); pg.wait_for_selector(".picker")
        pg.select_option("select[data-k='machine']", "RTX 3090"); pg.wait_for_selector("#cards .card")
        before_view = pg.eval_on_selector(".tab.active", "e=>e.getAttribute('data-view')")
        pg.click("a[href='#basis']"); pg.wait_for_timeout(200)
        after_view = pg.eval_on_selector(".tab.active", "e=>e.getAttribute('data-view')")
        ev["interaction"]["basis_link_resets_view"] = {"before": before_view, "after": after_view,
                                                       "url": pg.url}
        # Q1 结果
        pg.click(".tab[data-view='machine']"); pg.wait_for_selector(".picker")
        pg.select_option("select[data-k='machine']", "RTX 3090"); pg.wait_for_selector("#cards .card")
        shot(pg, "desktop", "02_q1_machine")
        # Q2 结果
        pg.click(".tab[data-view='model']"); pg.wait_for_selector("select[data-k='model']")
        pg.select_option("select[data-k='model']", "Qwen3.6-27B"); pg.wait_for_selector("#cards .card")
        shot(pg, "desktop", "03_q2_model")
        # 搜索逐字输入是否丢焦点
        pg.click("#cards input[data-k='q']")
        pg.eval_on_selector("#cards input[data-k='q']", "e=>e.focus()")
        pg.keyboard.type("mlx", delay=60)
        focus_lost = pg.evaluate("document.activeElement.getAttribute('data-k')")
        qval = pg.eval_on_selector("#cards input[data-k='q']", "e=>e.value")
        ev["interaction"]["search_typing"] = {"active_data_k_after_typing": focus_lost, "value": qval,
                                              "focus_kept": focus_lost == "q"}
        shot(pg, "desktop", "04_q2_search_mlx")
        # 筛选无结果
        pg.eval_on_selector("#cards input[data-k='q']", "e=>{e.value='zzz_no_match_zzz';e.dispatchEvent(new Event('input',{bubbles:true}));}")
        pg.wait_for_timeout(150)
        shot(pg, "desktop", "05_empty_filter")
        ev["geometry"]["desktop_empty_overflow"] = overflow(pg)
        empty_txt = pg.eval_on_selector("#cards", "e=>e.textContent")
        ev["interaction"]["empty_state_shown"] = "没有符合" in empty_txt
        # Q3 另一模型
        pg.click(".tab[data-view='compare']"); pg.wait_for_selector(".compare-grid")
        pg.select_option("select[data-k='model']", "Qwen3.6-35B-A3B"); pg.wait_for_selector(".compare-grid")
        shot(pg, "desktop", "06_q3_compare_moe")
        # 后悔页
        pg.goto(REGRET); pg.wait_for_selector(".regret-group")
        shot(pg, "desktop", "07_regret")
        ev["geometry"]["desktop_regret_overflow"] = overflow(pg)
        ctx.close()

        # ===== 移动 390 =====
        mctx, mob = new_page(390, 844)
        mob.goto(INDEX); mob.wait_for_selector(".compare-grid")
        shot(mob, "mobile", "01_home_compare")
        ev["geometry"]["mobile_home_overflow"] = overflow(mob)
        mob.click(".tab[data-view='machine']"); mob.wait_for_selector(".picker")
        mob.select_option("select[data-k='machine']", "RTX 3090"); mob.wait_for_selector("#cards .card")
        shot(mob, "mobile", "02_q1_machine")
        ev["geometry"]["mobile_q1_overflow"] = overflow(mob)
        mob.click(".tab[data-view='model']"); mob.wait_for_selector("select[data-k='model']")
        mob.select_option("select[data-k='model']", "Qwen3.6-27B"); mob.wait_for_selector("#cards .card")
        shot(mob, "mobile", "03_q2_model")
        ev["geometry"]["mobile_q2_overflow"] = overflow(mob)
        # 移动触控目标尺寸
        taps = mob.evaluate("""()=>{
          const els=[...document.querySelectorAll('.nav a, .tab, select, input, button, .card-foot a')];
          return els.map(e=>{const r=e.getBoundingClientRect();return {t:e.tagName+(e.getAttribute('data-k')||'')+(e.textContent||'').slice(0,8),h:Math.round(r.height),w:Math.round(r.width)};}).filter(x=>x.h>0&&x.h<40);
        }""")
        ev["geometry"]["mobile_small_tap_targets"] = taps[:25]
        mob.eval_on_selector("#cards input[data-k='q']", "e=>{e.value='zzz_no_match_zzz';e.dispatchEvent(new Event('input',{bubbles:true}));}")
        mob.wait_for_timeout(150)
        shot(mob, "mobile", "05_empty_filter")
        mob.click(".tab[data-view='compare']"); mob.wait_for_selector(".compare-grid")
        mob.select_option("select[data-k='model']", "Qwen3.6-35B-A3B"); mob.wait_for_selector(".compare-grid")
        shot(mob, "mobile", "06_q3_compare_moe")
        mob.goto(REGRET); mob.wait_for_selector(".regret-group")
        shot(mob, "mobile", "07_regret")
        ev["geometry"]["mobile_regret_overflow"] = overflow(mob)
        mctx.close()

        # ===== 对账：随机 20 张卡片 =====
        ctx, pg = new_page(1280, 900)
        sample = random.sample(stat, 20)
        routes = defaultdict(list)
        for r in sample:
            if r.get("model_canon"):
                routes[("model", r["model_canon"])].append(r)
            elif r.get("machine_canon"):
                routes[("machine", r["machine_canon"])].append(r)
            else:
                routes[("__none__", "")].append(r)
        card_check = []
        for (view, param), rs in routes.items():
            if view != "__none__":
                pg.goto(INDEX + "#view=" + view + "&" + view + "=" + quote(param, safe=""))
                pg.wait_for_selector("#cards")
            for r in rs:
                got = None if view == "__none__" else pg.evaluate(
                    """(rid)=>{const c=[...document.querySelectorAll('.card')].find(x=>x.id==='r-'+rid);if(!c)return null;
                      return {machine:c.querySelector('.card-machine').textContent,
                              model:c.querySelector('.card-model').textContent,
                              speed:c.querySelector('.card-speed').textContent};}""", r["record_id"])
                exp_machine = r.get("machine_canon") or r.get("machine") or "机器未指明"
                exp_model = r.get("model_canon") or r.get("model") or "模型未指明"
                ok = bool(got) and got["machine"] == exp_machine and got["model"] == exp_model
                speed_ok = True
                if got and r.get("speed_value") is not None:
                    num = re.search(r"[\d.]+", got["speed"])
                    speed_ok = bool(num) and abs(float(num.group()) - r["speed_value"]) < 0.011
                elif got and r.get("speed_value") is None:
                    speed_ok = (r.get("speed_raw") or "速度未注明") in got["speed"] or "速度未注明" in got["speed"]
                card_check.append({"id": r["record_id"], "route": view, "found": bool(got), "machine_ok": ok,
                                   "speed_ok": speed_ok, "got": got,
                                   "exp": {"machine": exp_machine, "model": exp_model,
                                           "speed_value": r.get("speed_value"), "speed_raw": r.get("speed_raw")}})
        ev["reconcile"]["cards_20"] = card_check

        # ===== 对账：3 组筛选（条数 + 中位数）=====
        groups = []
        # 组1: model 视图 Qwen3.6-27B + cat=Mac 的卡片条数
        pg.goto(INDEX + "#view=model&model=Qwen3.6-27B&cat=Mac"); pg.wait_for_selector("#cards")
        shown = pg.eval_on_selector_all("#cards .card", "e=>e.length")
        exp = len([r for r in stat if r.get("model_canon") == "Qwen3.6-27B" and r.get("machine_category") == "Mac"])
        groups.append({"name": "model=Qwen3.6-27B&cat=Mac 卡片数", "shown": shown, "expected": exp, "ok": shown == exp})
        # 组2: compare Qwen3.6-35B-A3B 各类别中位数与条数
        pg.goto(INDEX + "#view=compare&model=Qwen3.6-35B-A3B"); pg.wait_for_selector(".compare-grid")
        rows = pg.evaluate("""()=>[...document.querySelectorAll('.compare-grid .cmp-row:not(.head)')].map(r=>({
          cat:r.querySelector('.cat').textContent, stat:r.querySelector('.cmp-stat').textContent}))""")
        mo = [r for r in stat if r.get("model_canon") == "Qwen3.6-35B-A3B"]
        cmp_check = []
        for row in rows:
            sub = [r for r in mo if r.get("machine_category") == row["cat"]]
            ps = person_stats(sub)
            med_str = (str(ps["median"]) if ps["median"] is not None else "样本不足")
            ok = (str(len(sub)) + " 条") in row["stat"] and (med_str in row["stat"] or (ps["median"] is not None and re.search(r"[\d.]+", row["stat"]) and abs(float(re.search(r"[\d.]+", row["stat"]).group()) - ps["median"]) < 0.011))
            cmp_check.append({"cat": row["cat"], "shown_stat": row["stat"], "expected_n": len(sub),
                              "expected_median": ps["median"], "ok": ok})
        groups.append({"name": "compare Qwen3.6-35B-A3B 类别中位数/条数", "rows": cmp_check,
                       "ok": all(c["ok"] for c in cmp_check)})
        # 组3: machine 视图 Strix Halo 按模型表中位数
        pg.goto(INDEX + "#view=machine&machine=Strix+Halo"); pg.wait_for_selector("table.tbl")
        mrows = pg.evaluate("""()=>[...document.querySelectorAll('table.tbl tbody tr')].map(r=>({
          model:r.getAttribute('data-model'), cells:[...r.querySelectorAll('td')].map(td=>td.textContent)}))""")
        sh = [r for r in stat if r.get("machine_canon") == "Strix Halo"]
        bm = defaultdict(list)
        for r in sh:
            bm[r.get("model_canon") or "（模型未指明）"].append(r)
        mcheck = []
        for mr in mrows[:8]:
            sub = bm.get(mr["model"], [])
            ps = person_stats(sub)
            shown_med = mr["cells"][2]
            ok = (str(len(sub)) == mr["cells"][1]) and (("样本不足" in shown_med) if ps["median"] is None else (re.search(r"[\d.]+", shown_med) and abs(float(re.search(r"[\d.]+", shown_med).group()) - ps["median"]) < 0.011))
            mcheck.append({"model": mr["model"], "shown_n": mr["cells"][1], "shown_med": shown_med,
                           "expected_n": len(sub), "expected_median": ps["median"], "ok": ok})
        groups.append({"name": "machine=Strix Halo 按模型中位数/条数", "rows": mcheck, "ok": all(c["ok"] for c in mcheck)})
        ev["reconcile"]["filter_groups_3"] = groups
        ctx.close()
        browser.close()

    ev["console"] = {"errors_warnings": errors, "failed_requests": failed}

    # ===== 异常候选：最高速 / 极低 / 换算 / 排除仍显示，附原文 =====
    inc = [r for r in stat if eligible(r)]
    top = sorted(inc, key=lambda r: r["speed_value"], reverse=True)[:8]
    low = sorted(inc, key=lambda r: r["speed_value"])[:5]
    conv = [r for r in recs if r.get("speed_converted")][:4]
    cand = {r["record_id"]: r for r in top + low + conv}
    for r in cand.values():
        ev["anomalies"].append({
            "record_id": r["record_id"], "machine": r.get("machine_canon"), "cat": r.get("machine_category"),
            "model": r.get("model_canon"), "speed_value": r.get("speed_value"), "speed_raw": r.get("speed_raw"),
            "speed_kind": r.get("speed_kind"), "speed_stat": r.get("speed_stat"),
            "reason": r.get("speed_stat_reason"), "quant": r.get("quant_canon"), "params": r.get("params_canon"),
            "summary_zh": r.get("summary_zh"), "evidence_en": r.get("evidence_en"),
            "hn_url": r.get("hn_url"), "by": r.get("by")})

    (OUT / "evidence.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1) + "\n")

    # ===== stdout 摘要 =====
    print("=== 控制台 ===")
    print(" errors/warnings:", len(errors), errors[:6])
    print(" failed_requests:", len(failed), failed[:4])
    print("=== 对比度（小字阈值4.5）===")
    for k, v in ev["contrast"].items():
        print(f"  {k}: {v}" + ("  <-- 低于4.5" if v < 4.5 else ""))
    print("=== 几何/溢出 ===")
    for k, v in ev["geometry"].items():
        if k == "mobile_small_tap_targets":
            print(f"  移动小触控目标(<40px): {len(v)} 个，例: {v[:5]}")
        else:
            print(f"  {k}: {v}")
    print("=== 交互 ===")
    print(" ", ev["interaction"])
    print("=== 对账 20 卡片 ===")
    bad = [c for c in card_check if not (c["found"] and c["machine_ok"] and c["speed_ok"])]
    print(f"  核对 {len(card_check)} 张，不符 {len(bad)}")
    for c in bad[:8]:
        print("   ", c)
    print("=== 对账 3 组筛选 ===")
    for g in groups:
        print(f"  {g['name']}: ok={g['ok']}")
        if not g["ok"]:
            print("    ", json.dumps(g, ensure_ascii=False)[:600])
    print("=== 异常候选（详见 evidence.json）===")
    for a in ev["anomalies"][:10]:
        print(f"  {a['record_id']} {a['machine']}[{a['cat']}] {a['model']} = {a['speed_value']} tok/s ({a['speed_raw']}) stat={a['speed_stat']}")
    print(f"\n证据已写入 {OUT / 'evidence.json'}；截图 desktop/ mobile/ 各 7 张")


if __name__ == "__main__":
    main()
