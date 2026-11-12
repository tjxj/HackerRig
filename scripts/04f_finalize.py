#!/usr/bin/env python3
"""Step 04f — 波次收尾（纯机械，不调用任何模型）。

支持一次收尾一个波次的多个批次（子代理并行产出后集中合并）：
1. 幂等合并各批隔离文件 batch_NNN.excluded.jsonl / batch_NNN.fills.json 进共享状态，
   并把各批加入 context_fills.json["batches"]（必须在任何全量审计前全部并入，
   否则未合并批次的 needs_context=true 会让全量审计误判）。
2. 04d 合并父链补全（一次，处理 batches 列表里全部批次）
3. 引号修复：把各批 evidence_en / context_evidence_en 各段与原文对齐，
   仅修正弯/直引号码位差异（’↔'、“”↔"），不改任何词。
4. 05_audit 全量审计（一次）
5. violations=0 才把各批写入 progress.json（done 追加、next 前进）
用法: python3 -I scripts/04f_finalize.py --batch batch_009 batch_010 ... --next batch_014
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
    """返回与原文精确对齐的段；仅修引号码位，词不动。修不了则原样返回交审计判。"""
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
    ap.add_argument("--batch", nargs="+", required=True, help="本波次批次列表")
    ap.add_argument("--next", required=True)
    a = ap.parse_args()
    batches = a.batch

    # 0. 合并各批隔离输出（幂等）。子代理并行时只写本批隔离文件；
    #    这里在波次之间集中并入共享状态，避免竞争。全部批次先并入再审计。
    gex = OUT / "excluded.jsonl"
    have = {json.loads(l)["comment_id"] for l in gex.read_text().splitlines() if l.strip()}
    cf = json.loads((OUT / "context_fills.json").read_text())
    have_f = {x["record_id"] for x in cf["fills"]}
    have_u = {x["record_id"] for x in cf["unfilled"]}
    tot_ex = tot_f = tot_u = 0
    for name in batches:
        pb_ex = OUT / f"{name}.excluded.jsonl"
        if pb_ex.exists():
            with open(gex, "a") as f:
                for l in pb_ex.read_text().splitlines():
                    if not l.strip():
                        continue
                    e = json.loads(l)
                    if e["comment_id"] not in have:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                        have.add(e["comment_id"])
                        tot_ex += 1
        pb_fills = OUT / f"{name}.fills.json"
        if pb_fills.exists():
            pf = json.loads(pb_fills.read_text())
            for x in pf.get("fills", []):
                if x["record_id"] not in have_f:
                    cf["fills"].append(x)
                    have_f.add(x["record_id"])
                    tot_f += 1
            for x in pf.get("unfilled", []):
                if x["record_id"] not in have_u:
                    cf["unfilled"].append(x)
                    have_u.add(x["record_id"])
                    tot_u += 1
        if name not in cf["batches"]:
            cf["batches"].append(name)
    (OUT / "context_fills.json").write_text(json.dumps(cf, ensure_ascii=False, indent=2) + "\n")
    print(f"[merge] excluded_added={tot_ex} fills_added={tot_f} unfilled_added={tot_u} "
          f"batches={len(cf['batches'])}")

    # 1. 04d（一次，处理 batches 列表全部批次）
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "04d_apply_context.py")],
                       capture_output=True, text=True)
    print("[04d]", r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
        sys.exit(1)

    # 2. 引号修复（本波各批）
    tie = pd.read_parquet(ROOT / "out" / "03_tier" / "tiered.parquet").set_index("id")
    ancestors = {}
    for f in ["parents.parquet", "extra_ancestors.parquet"]:
        for _, row in pd.read_parquet(OUT / f).iterrows():
            i = int(row["id"])
            title = row["title"] if "title" in row.index and pd.notna(row["title"]) else ""
            text = row["text"] if pd.notna(row["text"]) else ""
            ancestors[i] = norm((f"TITLE: {title}\n" if title else "") + clean(text))
    for iid, row in tie.iterrows():
        i = int(iid)
        if i not in ancestors:
            ancestors[i] = norm(clean(row["text"]))

    # 修复所有批次（不只本波）：后续波次 04e 可能把早先批次的祖先重新取进
    # extra_ancestors（带弯引号/title），改变其展示文本，使早先批次已对齐的证据漂移。
    # 每波对全部批次重对齐引号码位（幂等、只动引号），防止跨波漂移。
    n_fix = 0
    all_batches = sorted(bf.stem for bf in OUT.glob("batch_*.json")
                         if re.fullmatch(r"batch_\d+", bf.stem))
    for name in all_batches:
        bf = OUT / f"{name}.json"
        recs = json.loads(bf.read_text())
        for rec in recs:
            ctext = norm(clean(tie.loc[rec["comment_id"]]["text"]))
            ev = rec["evidence_en"]
            if isinstance(ev, str):  # 旧格式（batch_001–003）单段长字符串：整段修复，保持字符串
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

    # 3. 全量审计（一次）
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "05_audit.py")],
                       capture_output=True, text=True)
    print("[05_audit]\n" + r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr)
        sys.exit(1)

    # 4. progress
    pf = OUT / "progress.json"
    prog = json.loads(pf.read_text())
    for name in batches:
        if name not in prog["done"]:
            prog["done"].append(name)
    prog["next"] = a.next
    pf.write_text(json.dumps(prog, ensure_ascii=False, indent=2) + "\n")
    print(f"[progress] done={len(prog['done'])} next={a.next}")


if __name__ == "__main__":
    main()