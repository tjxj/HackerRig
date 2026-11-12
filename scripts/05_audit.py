#!/usr/bin/env python3
"""Step 05 — 抽取结果审计（纯规则，不调用任何模型）。

模式:
- 默认: 审计 out/04_extract/batch_*.json（新旧格式兼容）
- --merged: 审计 out/06_merge/measurements.jsonl（合并后全量审计）

检查:
1. record_id 唯一、格式 comment_id#n（n 从 1 连续），comment_id 属于对应批次输入
2. 每段证据都是评论 clean() 文本（空白归一后）的连续子串；
   列表格式的证据额外要求每段 ≤2 句（启发式: [.!?]+空白+大写开头 断句）
3. 非空文本字段的字母数字 token 全部出现在证据段并集；
   evidence_source=parent 的记录允许 token 出现在 context_evidence_en 各段
4. speed_raw 是某一段证据的子串；speed_value 与 speed_raw 解析一致
   （区间/上下界 → null；k/K ×1000；逗号千分位；不做单位换算）
5. 枚举合法；evidence_source=parent 时 context 各段必须是对应祖先
   展示文本（TITLE 行 + clean(text)，空白归一）的子串，且祖先确在评论父链上
6. 漏斗对账：每批输入评论 = 抽取评论 ∪ 排除评论，不重不漏；排除原因合法
7. 元数据 by/month/hn_url/tier 存在才查（v2 批次省略，由 06_merge 补齐）
输出: out/05_audit/report.json + 终端摘要；有违规则退出码 1。
用法: python3 -I scripts/05_audit.py [--merged]
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "04_extract"
MERGED = ROOT / "out" / "06_merge"
REPORT = ROOT / "out" / "05_audit"

A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")
TEXT_FIELDS = ["machine", "memory", "model", "params", "quant", "engine",
               "context_length", "concurrency", "price"]
SPEED_UNITS = {"tok/s", "ms/token"}
SPEED_KINDS = {"generation", "prompt", "total", "unspecified"}
SENTIMENTS = {"satisfied", "regret", "mixed", "neutral", None}
EXCLUDE_REASONS = {"cloud", "hypothetical", "not_llm", "no_measurement",
                   "joke", "news_quote", "other"}
RANGE = re.compile(r"\d[\d.,]*\s*[kK]?\s*(?:[-–—]|to|or)\s*\d")
BOUND = re.compile(r"(over|ober|under|up to|at least|at most|at best|at worst|no more than|maximum|below|above|north of|south of|can[’']t break|cannot break|can[’']t exceed|cannot exceed|don[’']t break|don[’']t exceed|can[’']t push|cannot push|can[’']t seem to|cannot seem to|upwards of|upward of|in excess of|or less|or more|or below|or above|break\s*\d|(?:mid-high|mid-low|upper|lower|low|high|mid)\s*\d|capped at|<=|>=|<|>|\d\+)", re.I)
NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?|\.\d+)\s*([kK])?")
FRAC = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*(?:tokens?|tok|t/s|tps)")
BATCH_HEAD = re.compile(r"^----- \[\d+\] id=(\d+) ", re.M)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def clean(t: str) -> str:
    t = html.unescape(t).replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def toks(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def spans(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return v


def parse_speed(raw: str):
    if RANGE.search(raw) or BOUND.search(raw):
        return None
    fm = FRAC.search(raw)  # 分数速度 "1/2token per second" → 0.5（须紧邻 token 单位）
    if fm:
        den = float(fm.group(2))
        if den != 0:
            return float(fm.group(1)) / den
    m = NUM.search(raw)
    if not m:
        return "NO_NUM"
    s = m.group(1)
    # 欧式小数逗号 "44,7"→44.7（逗号后 1-2 位且无 3 位千分组）；否则千分位 "60,000"→60000
    if re.search(r",\d{1,2}$", s) and not re.search(r",\d{3}", s):
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    v = float(s)
    if m.group(2):
        v *= 1000
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", action="store_true")
    ap.add_argument("--batch", help="只审计单批（子代理预检，补全前；读 batch_NNN.excluded.jsonl）")
    a = ap.parse_args()
    prefill = bool(a.batch)

    tie = pd.read_parquet(ROOT / "out" / "03_tier" / "tiered.parquet")
    par = pd.read_parquet(OUT / "parents.parquet")
    ext = pd.read_parquet(OUT / "extra_ancestors.parquet")

    comments = {}   # id -> dict(text_norm, month, by)
    ancestors = {}  # id -> display text normalized
    parent_of = {}
    for _, r in tie.iterrows():
        comments[int(r["id"])] = {"text": norm(clean(r["text"])),
                                  "month": r["month"], "by": r["by"]}
        parent_of[int(r["id"])] = int(r["parent"])
    for df in (par, ext):
        for _, r in df.iterrows():
            i = int(r["id"])
            title = r["title"] if "title" in r.index and pd.notna(r["title"]) else ""
            text = r["text"] if pd.notna(r["text"]) else ""
            disp = (f"TITLE: {title}\n" if title else "") + clean(text)
            ancestors[i] = norm(disp)
            parent_of[i] = int(r["parent"])
    for _, r in tie.iterrows():  # tiered 评论也可能是祖先（如 47093980）
        i = int(r["id"])
        if i not in ancestors:
            ancestors[i] = norm(clean(r["text"]))

    violations = []

    def bad(rid, check, detail):
        violations.append({"record_id": rid, "check": check, "detail": detail})

    if a.merged:
        recs_all = [json.loads(l) for l in
                    (MERGED / "measurements.jsonl").read_text().splitlines() if l.strip()]
        batches = {}
        for r in recs_all:
            batches.setdefault(r["batch"], []).append(r)
        ex_path = MERGED / "excluded.jsonl"
    elif a.batch:
        batches = {a.batch: json.loads((OUT / f"{a.batch}.json").read_text())}
        pb_ex = OUT / f"{a.batch}.excluded.jsonl"
        ex_path = pb_ex if pb_ex.exists() else OUT / "excluded.jsonl"
    else:
        batches = {bf.stem: json.loads(bf.read_text())
                   for bf in sorted(OUT.glob("batch_*.json"))
                   if re.fullmatch(r"batch_\d+", bf.stem)}
        ex_path = OUT / "excluded.jsonl"
    excluded = [json.loads(l) for l in ex_path.read_text().splitlines() if l.strip()]
    ex_ids = [e["comment_id"] for e in excluded]
    if len(ex_ids) != len(set(ex_ids)):
        bad("-", "excluded_unique", "excluded.jsonl 有重复 comment_id")
    for e in excluded:
        if e["reason"] not in EXCLUDE_REASONS:
            bad(str(e["comment_id"]), "exclude_reason", e["reason"])

    all_rids = set()
    n_rec = n_parent = 0
    per_batch = []
    extracted_ids_all = set()
    for name, recs in sorted(batches.items()):
        infile = OUT / "batches" / f"{name}.txt"
        input_ids = [int(x) for x in BATCH_HEAD.findall(infile.read_text())]
        input_set = set(input_ids)
        if len(input_ids) != len(input_set):
            bad(name, "batch_input_unique", "批次输入有重复 id")
        by_comment = {}
        for r in recs:
            rid = r["record_id"]
            n_rec += 1
            if rid in all_rids:
                bad(rid, "record_id_unique", "record_id 重复")
            all_rids.add(rid)
            cid = r["comment_id"]
            by_comment.setdefault(cid, []).append(r)
            if cid not in input_set:
                bad(rid, "comment_in_batch", f"{cid} 不在 {name} 输入里")
                continue
            if cid not in comments:
                bad(rid, "comment_in_tiered", f"{cid} 不在 tiered")
                continue
            c = comments[cid]
            if "by" in r and r["by"] != c["by"]:
                bad(rid, "by_match", f"{r['by']} != {c['by']}")
            if "month" in r and r["month"] != c["month"]:
                bad(rid, "month_match", f"{r['month']} != {c['month']}")
            if "hn_url" in r and r["hn_url"] != f"https://news.ycombinator.com/item?id={cid}":
                bad(rid, "hn_url", r["hn_url"])
            if "tier" in r and r["tier"] not in {"S1", "S2"}:
                bad(rid, "tier_enum", str(r["tier"]))
            if r["first_person"] not in (True, False, "unclear"):
                bad(rid, "first_person_bool", str(r["first_person"]))
            if not prefill and r["needs_context"] is not False:
                bad(rid, "needs_context", "已处理批次必须为 false")
            ev_spans = spans(r["evidence_en"])
            list_fmt = isinstance(r["evidence_en"], list)
            cap = list_fmt or a.merged
            if not ev_spans:
                bad(rid, "evidence_missing", "evidence_en 为空")
            allowed = set()
            for i, sp in enumerate(ev_spans):
                spn = norm(sp)
                if spn not in c["text"]:
                    bad(rid, "evidence_substring", f"span[{i}] 不是评论原文连续子串")
                if cap and len(SENT.split(spn)) > 2:
                    bad(rid, "evidence_span_length", f"span[{i}] 超过两句")
                allowed |= toks(spn)
            ctx_spans = spans(r.get("context_evidence_en"))
            src = r["evidence_source"]
            if src not in {"comment", "parent"}:
                bad(rid, "evidence_source_enum", str(src))
            if src == "parent":
                n_parent += 1
                if not ctx_spans:
                    bad(rid, "context_evidence_missing", "parent 补全必须有 context_evidence_en")
                else:
                    aid = r.get("context_ancestor_id")
                    if aid is None or aid not in ancestors:
                        bad(rid, "context_ancestor_index", f"祖先 {aid} 不在索引")
                    else:
                        for i, sp in enumerate(ctx_spans):
                            spn = norm(sp)
                            if spn not in ancestors[aid]:
                                bad(rid, "context_evidence_substring",
                                    f"span[{i}] 不是祖先 {aid} 展示文本子串")
                            if cap and len(SENT.split(spn)) > 2:
                                bad(rid, "context_span_length", f"span[{i}] 超过两句")
                        cur, hops = parent_of.get(cid), 0
                        while cur is not None and cur != 0 and hops < 50:
                            if cur == aid:
                                break
                            cur = parent_of.get(cur)
                            hops += 1
                        else:
                            bad(rid, "context_chain", f"{aid} 不在 {cid} 的父链上")
                    allowed |= toks(" ".join(ctx_spans))
            else:
                if r.get("context_evidence_en") is not None:
                    bad(rid, "context_evidence_unexpected", "comment 来源不应有 context_evidence_en")
            for f in TEXT_FIELDS:
                v = r.get(f)
                if v is None:
                    continue
                if not isinstance(v, str):
                    bad(rid, f"field_type:{f}", str(type(v)))
                    continue
                missing = toks(v) - allowed
                if missing:
                    bad(rid, f"field_tokens:{f}", f"{v!r} 缺 token {sorted(missing)}")
            raw = r["speed_raw"]
            if not any(norm(raw) in norm(sp) for sp in ev_spans):
                bad(rid, "speed_raw_substring", f"{raw!r} 不在任何证据段")
            if r["speed_unit"] not in SPEED_UNITS:
                bad(rid, "speed_unit_enum", str(r["speed_unit"]))
            if r["speed_kind"] not in SPEED_KINDS:
                bad(rid, "speed_kind_enum", str(r["speed_kind"]))
            if r["sentiment"] not in SENTIMENTS:
                bad(rid, "sentiment_enum", str(r["sentiment"]))
            parsed = parse_speed(raw)
            sv = r["speed_value"]
            if parsed == "NO_NUM":
                bad(rid, "speed_parse", f"{raw!r} 解析不出数字")
            elif parsed is None:
                if sv is not None:
                    bad(rid, "speed_value_range", f"{raw!r} 为区间/上下界，speed_value 应为 null，实为 {sv}")
            else:
                if sv is None or abs(parsed - sv) > 1e-6:
                    bad(rid, "speed_value_parse", f"{raw!r} 解析为 {parsed}，实为 {sv}")
        for cid, rs in by_comment.items():
            nums = sorted(int(r["record_id"].split("#")[1]) for r in rs)
            if nums != list(range(1, len(nums) + 1)):
                bad(f"{cid}", "record_numbering", f"编号不连续: {nums}")
            for r in rs:
                if r["record_id"] != f"{cid}#{r['record_id'].split('#')[1]}":
                    bad(r["record_id"], "record_id_format", "与 comment_id 不符")
        ex_here = {e["comment_id"] for e in excluded if e["comment_id"] in input_set}
        ext_here = set(by_comment)
        if ex_here & ext_here:
            bad(name, "funnel_overlap", f"既抽取又排除: {sorted(ex_here & ext_here)}")
        missing = input_set - ext_here - ex_here
        extra = (ext_here | ex_here) - input_set
        if missing:
            bad(name, "funnel_missing", f"未处理评论: {sorted(missing)}")
        if extra:
            bad(name, "funnel_extra", f"不属于本批: {sorted(extra)}")
        extracted_ids_all |= ext_here
        per_batch.append({"batch": name, "input": len(input_set),
                          "extracted_comments": len(ext_here),
                          "records": len(recs), "excluded": len(ex_here)})

    REPORT.mkdir(parents=True, exist_ok=True)
    report_file = REPORT / (f"report_{a.batch}.json" if a.batch else "report.json")
    mode = "merged" if a.merged else (f"batch:{a.batch}" if a.batch else "batches")
    report = {"mode": mode,
              "batches": per_batch,
              "totals": {"records": n_rec,
                         "extracted_comments": len(extracted_ids_all),
                         "excluded_comments": len(ex_ids),
                         "parent_filled_records": n_parent},
              "violations": violations}
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for b in per_batch:
        print(f"{b['batch']}: input={b['input']} extracted_comments={b['extracted_comments']} "
              f"records={b['records']} excluded={b['excluded']}")
    t = report["totals"]
    print(f"TOTAL: records={t['records']} extracted_comments={t['extracted_comments']} "
          f"excluded_comments={t['excluded_comments']} parent_filled_records={t['parent_filled_records']}")
    print(f"violations={len(violations)} -> {report_file}")
    for v in violations[:50]:
        print(f"  [{v['check']}] {v['record_id']}: {v['detail']}")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()