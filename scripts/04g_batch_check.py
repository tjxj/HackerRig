#!/usr/bin/env python3
"""Step 04g — 单批预检（子代理用，纯机械，不调用任何模型）。

子代理并行抽取时各自只写本批的隔离文件，不碰共享状态。本脚本：
1. 引号修复：把 batch_NNN.json 的 evidence_en / context_evidence_en 各段与原文对齐，
   仅修弯/直引号码位（’↔'、“”↔"），词不动（与 04f 同逻辑）。
2. 05_audit --batch batch_NNN：只审计本批（补全前 prefill 模式，
   漏斗读本批 batch_NNN.excluded.jsonl；needs_context=true 暂不判违规）。
不运行 04d、不改 excluded.jsonl/context_fills.json/progress.json、不写全局 report。
子代理反复改 JSON 重跑本脚本，直到 violations=0 再回报。
用法: python3 -I scripts/04g_batch_check.py --batch batch_009
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "04_extract"
A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")
QUOTE_MAP = {ord("’"): "'", ord("‘"): "'", ord("“"): '"', ord("”"): '"'}


def clean(t: str) -> str:
    t = html.unescape(t).replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def canon(s: str) -> str:
    return s.translate(QUOTE_MAP)


def repair_span(sp: str, source_norm: str):
    spn = norm(sp)
    if spn in source_norm:
        return spn, False
    csrc = canon(source_norm)
    i = csrc.find(canon(spn))
    if i >= 0:
        return source_norm[i:i + len(spn)], True
    return spn, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    a = ap.parse_args()

    tie = pd.read_parquet(ROOT / "out" / "03_tier" / "tiered.parquet").set_index("id")
    ancestors = {}
    for f in ["parents.parquet", "extra_ancestors.parquet"]:
        p = OUT / f
        if not p.exists():
            continue
        for _, row in pd.read_parquet(p).iterrows():
            i = int(row["id"])
            title = row["title"] if "title" in row.index and pd.notna(row["title"]) else ""
            text = row["text"] if pd.notna(row["text"]) else ""
            ancestors[i] = norm((f"TITLE: {title}\n" if title else "") + clean(text))
    for iid, row in tie.iterrows():
        i = int(iid)
        if i not in ancestors:
            ancestors[i] = norm(clean(row["text"]))

    bf = OUT / f"{a.batch}.json"
    recs = json.loads(bf.read_text())
    n_fix = 0
    for rec in recs:
        ctext = norm(clean(tie.loc[rec["comment_id"]]["text"]))
        ev = rec["evidence_en"]
        if isinstance(ev, str):  # 旧格式单段长字符串：整段修复，保持字符串（勿按字符迭代）
            fixed, changed = repair_span(ev, ctext)
            rec["evidence_en"] = fixed
            n_fix += changed
        else:
            new_ev = []
            for sp in ev:
                fixed, changed = repair_span(sp, ctext)
                new_ev.append(fixed)
                n_fix += changed
            rec["evidence_en"] = new_ev
        ce = rec.get("context_evidence_en")
        if ce:
            aid = rec.get("context_ancestor_id")
            asrc = ancestors.get(aid, "")
            if isinstance(ce, str):
                fixed, changed = repair_span(ce, asrc)
                rec["context_evidence_en"] = fixed
                n_fix += changed
            else:
                new_ctx = []
                for sp in ce:
                    fixed, changed = repair_span(sp, asrc)
                    new_ctx.append(fixed)
                    n_fix += changed
                rec["context_evidence_en"] = new_ctx
    bf.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n")
    print(f"[repair] quote_fixes={n_fix}")

    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "05_audit.py"),
                        "--batch", a.batch], capture_output=True, text=True)
    print("[05_audit --batch]\n" + r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()