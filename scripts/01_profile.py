#!/usr/bin/env python3
"""Step 01 — 摸底：2026 HN parquet 分片的字段、条目类型、评论正文格式、原文抽样。

数据 schema 依据数据集自带 README.md（open-index/hacker-news）：
  type: 1=story 2=comment 3=poll 4=pollopt 5=job（int8 枚举）
  text: HN 原始 HTML；deleted/dead: 0/1；缺失值用空串/0/空列表表示，列均 not null。
只读数据，输出写到 HackerRig/out/01_profile/。
用法: python3 -I scripts/01_profile.py
"""
import json
import random
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import os
DATA = Path(os.environ.get("HACKERRIG_DATA", str(Path(__file__).resolve().parent.parent / "data" / "2026")))
OUT = Path(__file__).resolve().parent.parent / "out" / "01_profile"
SEED = 42
TYPE_NAMES = {1: "story", 2: "comment", 3: "poll", 4: "pollopt", 5: "job"}

HTML_TAG = re.compile(r"<[a-zA-Z][^>]*>")
HTML_ENT = re.compile(r"&#x27;|&quot;|&gt;|&lt;|&amp;|&#x2F;")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*.parquet"))
    assert files, f"no parquet under {DATA}"

    profile = {"files": [], "totals": {}}
    rng = random.Random(SEED)
    sample_lines = []
    schema_printed = False
    total_rows = 0
    type_totals = {}
    comment_total = 0
    comment_with_text = 0
    comment_deleted = 0
    comment_dead = 0

    for f in files:
        pf = pq.ParquetFile(f)
        if not schema_printed:
            print("=== Arrow schema (first file) ===")
            print(pf.schema_arrow)
            schema_printed = True
        df = pf.read().to_pandas()
        n = len(df)
        total_rows += n
        types = {TYPE_NAMES.get(int(k), f"unknown({k})"): int(v)
                 for k, v in df["type"].value_counts().sort_index().items()}
        for k, v in types.items():
            type_totals[k] = type_totals.get(k, 0) + v

        info = {
            "file": f.name,
            "rows": n,
            "types": types,
            "time_min": str(df["time"].min()),
            "time_max": str(df["time"].max()),
        }

        comments = df[df["type"] == 2]
        nc = len(comments)
        comment_total += nc
        ndel = int(comments["deleted"].sum())
        ndead = int(comments["dead"].sum())
        comment_deleted += ndel
        comment_dead += ndead
        txt = comments["text"]
        with_text = int(txt.str.len().gt(0).sum())
        comment_with_text += with_text
        lens = txt.str.len()
        info["comments"] = {
            "count": nc,
            "deleted": ndel,
            "dead": ndead,
            "with_text": with_text,
            "empty_text": nc - with_text,
            "len_p50": int(lens.quantile(0.5)),
            "len_p90": int(lens.quantile(0.9)),
            "len_p99": int(lens.quantile(0.99)),
            "len_max": int(lens.max()),
            "contains_html_tag": int(txt.str.contains(HTML_TAG, regex=True).sum()),
            "contains_html_entity": int(txt.str.contains(HTML_ENT, regex=True).sum()),
            "contains_p_tag": int(txt.str.contains("<p>", regex=False).sum()),
            "contains_a_tag": int(txt.str.contains("<a href", regex=False).sum()),
            "contains_code_tag": int(txt.str.contains("<code>", regex=False).sum()),
        }
        # 每月随机抽 1 条完整原文（固定种子，可复现）
        row = comments.iloc[rng.randrange(nc)]
        sample_lines.append(
            f"----- RANDOM SAMPLE {f.name} | id={row['id']} | by={row['by']} "
            f"| time={row['time']} | parent={row['parent']} | dead={row['dead']} -----\n"
            f"{row['text']}\n"
        )
        profile["files"].append(info)
        c = info["comments"]
        print(f"{f.name}: rows={n} types={types}")
        print(f"    time=[{info['time_min']} .. {info['time_max']}]")
        print(f"    comments={nc} deleted={ndel} dead={ndead} with_text={with_text} "
              f"len p50/p90/p99/max={c['len_p50']}/{c['len_p90']}/{c['len_p99']}/{c['len_max']}")
        print(f"    html: tag={c['contains_html_tag']} entity={c['contains_html_entity']} "
              f"<p>={c['contains_p_tag']} <a>={c['contains_a_tag']} <code>={c['contains_code_tag']}")

    profile["totals"] = {
        "rows": total_rows,
        "types": type_totals,
        "comments": comment_total,
        "comments_deleted": comment_deleted,
        "comments_dead": comment_dead,
        "comments_with_text": comment_with_text,
    }
    (OUT / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2))
    (OUT / "samples_raw.txt").write_text("\n".join(sample_lines))
    print("\n=== TOTALS ===")
    print(json.dumps(profile["totals"], ensure_ascii=False, indent=2))
    print(f"\nwrote {OUT/'profile.json'} and {OUT/'samples_raw.txt'}")


if __name__ == "__main__":
    main()