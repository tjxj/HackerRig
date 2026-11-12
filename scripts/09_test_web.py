#!/usr/bin/env python3
"""Step 09 — 用真实浏览器（Playwright chromium）在 file:// 下实测网站（第六步增强）。

验证：渲染无错、三问视图、后悔页、网址同步 file:// 还原、移动端无横向溢出（含机器视图）、
离线、中位数引擎与 Python 复算一致（含投机/扩散/跑不动排除、多卡单列）、样本<5 不给中位数、
搜索框真键盘逐字输入保焦点、第三问计数=总数且加得拢、口径锚点不重置视图、切视图清参数、
新徽章（扩散/跑不动/投机/多卡/补自上文）、摘要无加工备注、页面无内部 tier。
用法: python3 -I scripts/09_test_web.py
"""
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SHOT = ROOT / "out" / "09_web_test"
SHOT.mkdir(parents=True, exist_ok=True)
INDEX = (WEB / "index.html").as_uri()
REGRET = (WEB / "regret.html").as_uri()

fails = []
passes = []


def check(name, cond, detail=""):
    (passes if cond else fails).append(name)
    print(("  PASS " if cond else "  FAIL ") + name + (("  | " + detail) if detail else ""))


def load_data():
    raw = (WEB / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))


def eligible(r):
    return (r["first_person"] is True and r["dedup_status"] == "keep" and r["speed_stat"] == "include"
            and r.get("speed_value") is not None and r.get("speed_unit") == "tok/s"
            and r.get("speed_kind") in ("generation", "unspecified")
            and not r.get("speculative") and not r.get("diffusion") and not r.get("stalled"))


def person_stats(recs):
    el = [r for r in recs if eligible(r)]
    g = defaultdict(list)
    for r in el:
        g[(r["by"], r.get("machine_canon") or "", r.get("model_canon") or "")].append(r["speed_value"])
    votes = [statistics.median(v) for v in g.values()]
    med = round(statistics.median(votes), 2) if len(el) >= 5 else None
    return len(el), len(votes), med


def first_with(recs, **flags):
    for r in recs:
        if all(r.get(k) == v for k, v in flags.items()) and r.get("model_canon"):
            return r
    return None


def goto_model_of(page, r):
    page.goto(INDEX)
    page.wait_for_selector(".compare-grid")
    page.click(".tab[data-view='model']")
    page.wait_for_selector("select[data-k='model']")
    page.select_option("select[data-k='model']", r["model_canon"])
    page.wait_for_selector("#cards .card")


def has_badge(page, rid, cls):
    return page.evaluate(
        "(function(){var c=document.getElementById('r-" + rid + "');return c?!!c.querySelector('.badge." + cls + "'):false;})()")


def main():
    data = load_data()
    meta, recs = data["meta"], data["records"]
    stat = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    default_model = meta["default_compare_model"]
    dm_all = [r for r in stat if r.get("model_canon") == default_model]
    dm_single = [r for r in dm_all if not r.get("multi_card")]
    exp_n, exp_votes, exp_med = person_stats(dm_single)
    print(f"复算默认模型 {default_model}（单卡）: n={exp_n} votes={exp_votes} median={exp_med}；全部={len(dm_all)}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errors = []
        http_reqs = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: http_reqs.append(r.url) if r.url.startswith(("http://", "https://")) else None)

        # ===== [1] 首页 / 默认对比 =====
        print("\n[1] 首页加载 / 默认对比视图")
        page.goto(INDEX)
        page.wait_for_selector(".compare-grid")
        check("无 JS 错误", not errors, "; ".join(errors[:3]))
        check("离线：无 http(s) 请求", not http_reqs, str(http_reqs[:3]))
        kpis = page.eval_on_selector_all(".kpi .n", "els=>els.map(e=>e.textContent)")
        check("KPI 已填充", kpis and kpis[0] == str(meta["stat_records"]), str(kpis))
        check("默认对比模型=样本最多", page.eval_on_selector("select[data-k='model']", "e=>e.value") == default_model)
        note = page.eval_on_selector(".cmp-note", "e=>e.textContent")
        m = re.search(r"单卡总体中位数 ([\d.]+) tok/s（(\d+) 票）", note)
        got_med = float(m.group(1)) if m else None
        got_votes = int(m.group(2)) if m else None
        check("对比单卡总体中位数与Python一致", got_med == exp_med and got_votes == exp_votes,
              f"browser={got_med}/{got_votes} python={exp_med}/{exp_votes}")
        font = page.eval_on_selector("body", "e=>getComputedStyle(e).fontFamily")
        check("字体优先思源宋体", "Source Han Serif" in font, font)
        check("字体不含苹方PingFang", "PingFang" not in font)

        # ===== [1b] 第三问计数=总数，加得拢 =====
        print("\n[1b] 第三问计数口径（总数，非速度子集）")
        tbl_counts = page.eval_on_selector_all("table.tbl tbody tr td[data-label='实测数']",
                                               "els=>els.map(e=>parseInt(e.textContent,10))")
        total_m = re.search(r"合计 (\d+) 条", note)
        total = int(total_m.group(1)) if total_m else None
        uncat = len([r for r in dm_single if not r.get("machine_category")])
        check("对比表实测数合计+未分类=总条数", total is not None and sum(tbl_counts) + uncat == total,
              f"表合计={sum(tbl_counts)} 未分类={uncat} 总={total}")
        # 逐类别核对：实测数=该类别单卡总条数（非 eligible）
        cat_ok = True
        for cat in meta["category_order"]:
            exp_total = len([r for r in dm_single if r.get("machine_category") == cat])
            if exp_total == 0:
                continue
            row = page.evaluate(
                "(function(){var trs=[...document.querySelectorAll('table.tbl tbody tr')];"
                "for(var t of trs){var b=t.querySelector('.cat');if(b&&b.textContent===" + json.dumps(cat) + ")"
                "return parseInt(t.querySelector('td[data-label=\"实测数\"]').textContent,10);}return null;})()")
            if row != exp_total:
                cat_ok = False
        check("各类别实测数=单卡总条数", cat_ok)
        # 态度与计数同口径：每行 满+褒+后 <= 实测数
        sent_ok = page.evaluate(
            "(function(){var trs=[...document.querySelectorAll('table.tbl tbody tr')];"
            "return trs.every(function(t){var n=parseInt(t.querySelector('td[data-label=\"实测数\"]').textContent,10);"
            "var s=t.querySelector('td[data-label=\"态度\"]').textContent.split('/').map(x=>parseInt(x.trim(),10));"
            "return (s[0]+s[1]+s[2])<=n;});})()")
        check("态度计数不超过实测数（同口径）", bool(sent_ok))

        # ===== [2] Q1 机器视图 =====
        print("\n[2] Q1 机器→能跑什么")
        page.click(".tab[data-view='machine']")
        page.wait_for_selector(".picker")
        check("机器选择器渲染", page.eval_on_selector_all(".pick", "e=>e.length") >= 10)
        page.select_option("select[data-k='machine']", "RTX 3090")
        page.wait_for_selector("#cards .card")
        check("选机器后出卡片", page.eval_on_selector_all("#cards .card", "e=>e.length") > 0)
        url_q1 = page.url
        check("Q1 网址含 machine", "machine=RTX+3090" in url_q1 or "machine=RTX%203090" in url_q1, url_q1)
        hn = page.eval_on_selector_all("#cards .card a", "els=>els.map(e=>e.href)")
        check("卡片有HN原帖链接", any("news.ycombinator.com" in h for h in hn))

        # ===== [2b] 搜索框真键盘逐字输入（保焦点）=====
        print("\n[2b] 搜索框真键盘逐字输入")
        page.click("#cards input[data-k='q']")
        page.keyboard.type("mlx", delay=70)
        page.wait_for_timeout(260)
        val = page.eval_on_selector("#cards input[data-k='q']", "e=>e.value")
        focused = page.evaluate("document.activeElement?document.activeElement.getAttribute('data-k'):null")
        check("逐字输入后值完整=mlx", val == "mlx", val)
        check("逐字输入后焦点仍在搜索框", focused == "q", str(focused))
        page.keyboard.type(" frame", delay=70)
        page.wait_for_timeout(260)
        val2 = page.eval_on_selector("#cards input[data-k='q']", "e=>e.value")
        focused2 = page.evaluate("document.activeElement?document.activeElement.getAttribute('data-k'):null")
        check("继续输入值完整=mlx frame", val2 == "mlx frame", val2)
        check("继续输入焦点仍保持", focused2 == "q", str(focused2))
        # 搜索结果与 Python 一致
        q = "mlx frame"
        exp_cards = len([r for r in stat if r.get("machine_canon") == "RTX 3090"
                         and q in " ".join([r.get("summary_zh") or "", r.get("machine_canon") or "", r.get("machine") or "",
                                            r.get("model_canon") or "", r.get("model") or "", r.get("by") or "",
                                            " ".join(r.get("evidence_en") or [])]).lower()])
        got_cards = page.eval_on_selector_all("#cards .card", "e=>e.length")
        check("搜索过滤卡片数与Python一致", got_cards == exp_cards, f"browser={got_cards} python={exp_cards}")
        page.fill("#cards input[data-k='q']", "")
        page.wait_for_timeout(200)

        # ===== [3] file:// 网址还原 Q1 =====
        print("\n[3] file:// 网址还原 — Q1")
        page2 = ctx.new_page()
        page2.goto(url_q1)
        page2.wait_for_selector("#cards .card")
        check("还原后仍在机器视图", page2.eval_on_selector(".tab.active", "e=>e.getAttribute('data-view')") == "machine")
        check("还原后机器=RTX 3090", page2.eval_on_selector("select[data-k='machine']", "e=>e.value") == "RTX 3090")
        check("还原后卡片数一致",
              page.eval_on_selector_all("#cards .card", "e=>e.length") == page2.eval_on_selector_all("#cards .card", "e=>e.length"))
        page2.close()

        # ===== [4] 切视图清参数 + 口径锚点不重置 =====
        print("\n[4] 切视图清参数 / 口径锚点不重置视图")
        page.click(".tab[data-view='compare']")
        page.wait_for_selector(".compare-grid")
        check("切到对比视图清掉 machine 参数", "machine=" not in page.url, page.url)
        page.click(".tab[data-view='machine']")
        page.select_option("select[data-k='machine']", "RTX 3090")
        page.wait_for_selector("#cards .card")
        page.click(".nav-links a[href='#basis']")
        check("点口径说明不重置视图", page.eval_on_selector(".tab.active", "e=>e.getAttribute('data-view')") == "machine")
        check("点口径说明仍保留机器", page.eval_on_selector("select[data-k='machine']", "e=>e.value") == "RTX 3090")
        # 平滑滚动是异步的，页面很高时等它停稳（而非固定时长）
        try:
            page.wait_for_function("()=>{var e=document.getElementById('basis');if(!e)return false;var t=e.getBoundingClientRect().top;return t>=50&&t<=95;}", timeout=4000)
        except Exception:
            pass
        btop = page.eval_on_selector("#basis", "e=>e.getBoundingClientRect().top")
        check("口径锚点落在导航正下方附近", 50 <= btop <= 95, f"basis_top={btop}")

        # ===== [5] Q2 + 跨视图导航 =====
        print("\n[5] Q2 模型→要什么机器")
        page.goto(INDEX)
        page.wait_for_selector(".compare-grid")
        page.click(".tab[data-view='model']")
        page.wait_for_selector("select[data-k='model']")
        page.select_option("select[data-k='model']", "Qwen3.6-35B-A3B")
        page.wait_for_selector("table.tbl")
        first_machine = page.eval_on_selector("table.tbl tbody tr", "e=>e.getAttribute('data-machine')")
        page.click("table.tbl tbody tr")
        page.wait_for_selector(".tab.active[data-view='machine']")
        check("点机器行跨导航到Q1", page.eval_on_selector(".tab.active", "e=>e.getAttribute('data-view')") == "machine")
        check("跨导航带上机器", page.eval_on_selector("select[data-k='machine']", "e=>e.value") == first_machine)

        # ===== [6] 筛选同步 + file:// 还原 =====
        print("\n[6] 筛选同步 + file:// 还原 — Q2 带筛选")
        page.goto(INDEX)
        page.wait_for_selector(".compare-grid")
        page.click(".tab[data-view='model']")
        page.select_option("select[data-k='model']", "Qwen3.6-27B")
        page.wait_for_selector("#cards")
        page.select_option("#cards select[data-k='cat']", "Mac")
        page.fill("#cards input[data-k='q']", "mlx")
        page.select_option("#cards select[data-k='sort']", "speed_asc")
        page.wait_for_timeout(220)
        url_f = page.url
        check("筛选写入网址", all(k in url_f for k in ["cat=Mac", "q=mlx", "sort=speed_asc"]), url_f)
        page3 = ctx.new_page()
        page3.goto(url_f)
        page3.wait_for_selector("#cards")
        check("还原类别=Mac", page3.eval_on_selector("#cards select[data-k='cat']", "e=>e.value") == "Mac")
        check("还原搜索=mlx", page3.eval_on_selector("#cards input[data-k='q']", "e=>e.value") == "mlx")
        check("还原排序=speed_asc", page3.eval_on_selector("#cards select[data-k='sort']", "e=>e.value") == "speed_asc")
        check("还原后筛选卡片数一致",
              page.eval_on_selector_all("#cards .card", "e=>e.length") == page3.eval_on_selector_all("#cards .card", "e=>e.length"))
        page3.close()

        # ===== [7] 新徽章 =====
        print("\n[7] 新徽章（扩散/跑不动/投机/多卡/补自上文）")
        for flag, cls, label in [("diffusion", "diffusion", "扩散模型"), ("stalled", "stalled", "跑不动"),
                                 ("speculative", "spec", "投机解码"), ("multi_card", "multi", "多卡/多机"),
                                 ("context_supplemented", "supplement", "补自上文")]:
            r = first_with(stat, **{flag: True})
            if r is None:
                check(f"存在{label}样本", False, "数据中无此标记")
                continue
            goto_model_of(page, r)
            check(f"卡片渲染{label}徽章 ({r['record_id']})", has_badge(page, r["record_id"], cls))
        # 多卡/多机 在第三问单独成行
        mo = next((r["model_canon"] for r in stat if r.get("multi_card") and r.get("model_canon")), None)
        if mo:
            page.goto(INDEX)
            page.wait_for_selector(".compare-grid")
            page.select_option("select[data-k='model']", mo)
            page.wait_for_selector(".compare-grid")
            has_multi_row = page.evaluate("[...document.querySelectorAll('.cmp-row .cat')].some(e=>e.textContent==='多卡/多机')")
            check("第三问多卡/多机单独成行", bool(has_multi_row), mo)
        # 摘要无加工备注/评论ID；页面无内部 tier
        bad_sum = [r["record_id"] for r in recs if r.get("summary_zh")
                   and re.search(r"(根评论|父链|故事标题|评论\s*\d{5,}|#\d{5,}|由.{0,12}补充|补充自|来自父)", r["summary_zh"])]
        check("摘要无加工备注/评论ID", not bad_sum, str(bad_sum[:6]))
        check("data.js 不含内部 tier 字段", all("tier" not in r for r in recs))
        foot_txt = page.eval_on_selector_all(".card-foot", "els=>els.map(e=>e.textContent).join(' ')")
        check("卡片页脚无 S1/S2 标签", not re.search(r"\bS[12]\b", foot_txt))

        # ===== [8] 后悔页 =====
        print("\n[8] 后悔页")
        page.goto(REGRET)
        page.wait_for_selector(".regret-group")
        cards = page.eval_on_selector_all(".regret-group .card", "e=>e.length")
        check("后悔卡片数=meta", cards == meta["regret_fp_records"], f"cards={cards} meta={meta['regret_fp_records']}")
        # 小结按人算：每类 实测人数/后悔人数/比例，合计按人去重（一人多条只算一人）
        fp = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
        reg = [r for r in fp if r.get("sentiment") == "regret"]

        def ppl(rs, cat):
            return len({r["by"] for r in rs if (r.get("machine_category") or None) == cat})
        exp = {c: (ppl(fp, c), ppl(reg, c)) for c in meta["category_order"]}
        exp["机器未指明"] = (ppl(fp, None), ppl(reg, None))
        exp_total = (len({r["by"] for r in fp}), len({r["by"] for r in reg}))
        dom_rows = page.eval_on_selector_all(
            "#regret-summary table.tbl tbody tr",
            "els=>els.map(e=>Array.from(e.querySelectorAll('td')).map(td=>td.innerText.trim()))")
        parsed, total_row = {}, None
        for row in dom_rows:
            m = int(re.search(r"\d+", row[1]).group())
            rr = int(re.search(r"\d+", row[2]).group())
            pct = float(re.search(r"[\d.]+", row[3]).group())
            if "合计" in row[0]:
                total_row = (m, rr, pct)
            else:
                parsed[row[0]] = (m, rr, pct)
        ok_cat = all(parsed.get(c, (None, None))[:2] == exp[c] for c in exp if exp[c][0] > 0)
        check("后悔小结按人算·各类实测/后悔人数对得上", ok_cat,
              f"dom={ {k: v[:2] for k, v in parsed.items()} } exp={exp}")
        check("后悔小结合计按人去重=meta", bool(total_row) and total_row[0] == exp_total[0] == meta["stat_people"]
              and total_row[1] == exp_total[1] == meta["regret_people"],
              f"total={total_row} exp={exp_total}")
        ok_pct = all(abs(v[2] - round(v[1] / v[0] * 100, 1)) < 0.05 for v in parsed.values() if v[0])
        check("后悔比例=后悔人数/实测人数", ok_pct)
        check("后悔小结含机器未指明", "机器未指明" in parsed)
        check("后悔小结注明卡片仍全列", "全列" in page.eval_on_selector("#regret-summary", "e=>e.innerText"))
        check("后悔页无JS错误", not errors, "; ".join(errors[:3]))
        # 后悔页搜索真键盘
        page.click("input[data-k='q']")
        page.keyboard.type("mac", delay=70)
        page.wait_for_timeout(260)
        check("后悔页搜索保焦点", page.evaluate("document.activeElement?document.activeElement.getAttribute('data-k'):null") == "q")
        check("后悔页搜索值完整", page.eval_on_selector("input[data-k='q']", "e=>e.value") == "mac")
        page.fill("input[data-k='q']", "")
        page.wait_for_timeout(180)
        page.select_option("select[data-k='cat']", "统一内存主机")
        page.wait_for_timeout(150)
        url_r = page.url
        page4 = ctx.new_page()
        page4.goto(url_r)
        page4.wait_for_selector(".regret-group")
        check("后悔页类别还原", page4.eval_on_selector("select[data-k='cat']", "e=>e.value") == "统一内存主机")
        page4.close()

        # ===== [9] 移动端无横向溢出（含机器视图）=====
        print("\n[9] 移动端 390x844 无横向溢出")
        mctx = browser.new_context(viewport={"width": 390, "height": 844})
        mob = mctx.new_page()
        mob.goto(INDEX)
        mob.wait_for_selector(".compare-grid")
        iw = mob.evaluate("window.innerWidth")
        check("移动端首页无横向溢出", mob.evaluate("document.documentElement.scrollWidth") <= iw + 1)
        mob.click(".tab[data-view='machine']")
        mob.wait_for_selector(".picker")
        mob.select_option("select[data-k='machine']", "RTX 3090")
        mob.wait_for_selector("#cards .card")
        ow_m = mob.evaluate("document.documentElement.scrollWidth")
        check("移动端机器视图无横向溢出", ow_m <= iw + 1, f"scrollWidth={ow_m} innerWidth={iw}")
        mob.click(".tab[data-view='model']")
        mob.wait_for_selector("table.tbl")
        check("移动端表格视图无横向溢出", mob.evaluate("document.documentElement.scrollWidth") <= iw + 1)
        check("移动端表格转卡片(thead隐藏)", mob.eval_on_selector("table.tbl thead", "e=>getComputedStyle(e).display") == "none")
        mob.goto(REGRET)
        mob.wait_for_selector(".regret-group")
        check("移动端后悔页无横向溢出", mob.evaluate("document.documentElement.scrollWidth") <= iw + 1)
        # 触控目标 >=44px（导航/按钮/选择器/HN链接）
        small = mob.evaluate(
            "(function(){var sels=['.nav-links a','.tab','.btn','.field select','.field input','.card-foot a','.pick'];"
            "var bad=[];sels.forEach(function(s){document.querySelectorAll(s).forEach(function(e){"
            "var r=e.getBoundingClientRect();if(r.height>0&&r.height<43.5)bad.push(s+':'+Math.round(r.height));});});return bad;})()")
        check("移动端主要触控目标≥44px", not small, str(small[:8]))
        mob.screenshot(path=str(SHOT / "mobile.png"), full_page=True)
        mob.close()
        mctx.close()

        # ===== 桌面截图留底 =====
        page.goto(INDEX)
        page.wait_for_selector(".compare-grid")
        page.screenshot(path=str(SHOT / "desktop.png"), full_page=True)
        check("无累积JS错误(全程)", not errors, "; ".join(errors[:5]))
        browser.close()

    print(f"\n==== 结果：{len(passes)} 通过 / {len(fails)} 失败 ====")
    if fails:
        print("失败项：" + "；".join(fails))
        sys.exit(1)
    print("全部通过。截图：out/09_web_test/desktop.png , mobile.png")


if __name__ == "__main__":
    main()
