#!/usr/bin/env python3
"""Step 04e — 一次性备齐整批的精读上下文（纯机械，不调用任何模型）。

读批次输入，沿每条评论的 parent 链走到根，自动从源分片补取所有缺失祖先
（合并进 extra_ancestors.parquet，源数据只读），输出单一精读文件：
  COMMENTS 段：本批每条评论 clean() 文本
  ANCESTORS 段：去重后的祖先（含 TITLE）clean() 文本，每个只印一次
  CHAINS 段：comment_id -> 祖先链
精读时只读这一个文件即可同时做抽取与父链补全判断，省去多次探针往返。
用法: python3 -I scripts/04e_context.py --batch batch_008
"""
import argparse
import html
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
import os
DATA = Path(os.environ.get("HACKERRIG_DATA", str(Path(__file__).resolve().parent.parent / "data" / "2026")))
OUT = ROOT / "out" / "04_extract"
COLS = ["id", "type", "by", "time", "title", "text", "parent"]
A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")
HEAD = re.compile(r"^----- \[\d+\] id=(\d+) .*?parent=(\d+) ", re.M)


def clean(t: str) -> str:
    t = html.unescape(t).replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    return TAG.sub("", t).strip()


def load_index():
    idx = {}
    for f in ["parents.parquet", "extra_ancestors.parquet"]:
        p = OUT / f
        if p.exists():
            for _, r in pd.read_parquet(p).iterrows():
                idx[int(r["id"])] = r
    tie = pd.read_parquet(ROOT / "out" / "03_tier" / "tiered.parquet")
    for _, r in tie.iterrows():
        idx.setdefault(int(r["id"]), r)
    return idx, tie


def fetch(ids):
    parts = []
    for f in sorted(DATA.glob("*.parquet")):
        df = pq.ParquetFile(f).read(columns=COLS).to_pandas()
        parts.append(df[df["id"].isin(ids)])
    p = pd.concat(parts, ignore_index=True).drop_duplicates("id")
    prev = OUT / "extra_ancestors.parquet"
    if prev.exists():
        p = pd.concat([pd.read_parquet(prev), p], ignore_index=True).drop_duplicates("id")
    p.to_parquet(prev, index=False)
    return len(ids - set(p["id"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    a = ap.parse_args()
    infile = OUT / "batches" / f"{a.batch}.txt"
    pairs = [(int(c), int(p)) for c, p in HEAD.findall(infile.read_text())]
    idx, tie = load_index()
    tie = tie.set_index("id")

    # 反复补取直到所有链可走到根（缺失祖先的父亲可能也缺）
    fetched_total = 0
    for _ in range(12):
        missing = set()
        for cid, parent in pairs:
            cur, hops = parent, 0
            while cur and cur != 0 and hops < 50:
                if cur not in idx:
                    missing.add(cur)
                    break
                cur = int(idx[cur]["parent"])
                hops += 1
        if not missing:
            break
        fetched_total += len(missing) - fetch(missing)
        idx, _ = load_index()

    chains, anc_ids = {}, set()
    for cid, parent in pairs:
        chain, cur, hops = [], parent, 0
        while cur and cur != 0 and hops < 50:
            chain.append(cur)
            anc_ids.add(cur)
            if cur not in idx:
                break
            cur = int(idx[cur]["parent"])
            hops += 1
        chains[cid] = chain

    lines = [f"########## COMMENTS ({a.batch}, {len(pairs)}) ##########"]
    for cid, parent in pairs:
        r = tie.loc[cid]
        lines.append(f"----- [{cid}] by={r['by']} parent={parent} -----")
        lines.append(clean(r["text"]) + "\n")
    lines.append(f"########## ANCESTORS (unique, {len(anc_ids)}) ##########")
    for aid in sorted(anc_ids):
        r = idx.get(aid)
        if r is None:
            lines.append(f"----- [{aid}] MISSING -----\n")
            continue
        kind = "story" if ("type" in r.index and r["type"] == 1) else "comment"
        title = r["title"] if "title" in r.index and pd.notna(r["title"]) else ""
        text = clean(r["text"]) if ("text" in r.index and pd.notna(r["text"])) else ""
        lines.append(f"----- [{aid}] {kind} by={r['by']} -----")
        lines.append((f"TITLE: {title}\n" if title else "") + text + "\n")
    lines.append("########## CHAINS ##########")
    for cid, _ in pairs:
        lines.append(f"{cid} -> " + " > ".join(str(x) for x in chains[cid]))

    out_file = OUT / f"reading_{a.batch}.txt"
    out_file.write_text("\n".join(lines))
    print(f"batch={a.batch} comments={len(pairs)} ancestors={len(anc_ids)} "
          f"fetched={fetched_total} -> {out_file}")


if __name__ == "__main__":
    main()