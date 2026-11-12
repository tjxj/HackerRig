#!/usr/bin/env python3
"""Step 06 — 合并批次抽取结果为最终数据集（纯机械，不调用任何模型）。

- 证据统一为短句列表：旧格式长字符串按句界拆分，每段 ≤2 句，
  每段仍是原文连续子串；speed_raw 保证落在单段内（必要时合并相邻段）
- 按 comment_id 从 tiered.parquet 补 month/by/time/hn_url/tier，附 batch 溯源
- 输出 out/06_merge/measurements.jsonl、measurements.parquet、excluded.jsonl（带元数据）
  parquet 中 first_person 统一为字符串 "true"/"false"/"unclear"（bool 与 str 不能混列）
用法: python3 -I scripts/06_merge.py
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "04_extract"
DST = ROOT / "out" / "06_merge"
BATCH_HEAD = re.compile(r"^----- \[\d+\] id=(\d+) ", re.M)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
FIELDS = ["record_id", "comment_id", "batch", "month", "by", "time", "hn_url", "tier",
          "machine", "memory", "model", "params", "quant", "engine",
          "context_length", "concurrency",
          "speed_raw", "speed_value", "speed_unit", "speed_kind", "price",
          "first_person", "sentiment", "needs_context", "evidence_source",
          "evidence_en", "context_evidence_en", "context_ancestor_id", "summary_zh"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def to_spans(s: str, raws: list) -> list:
    """把已验证的连续原文长段按句界拆成 ≤2 句的短段；保证每个 speed_raw 落在单段内。"""
    s = norm(s)
    parts = SENT.split(s)
    out = [" ".join(parts[i:i + 2]) for i in range(0, len(parts), 2)]
    for raw in raws:
        rn = norm(raw)
        if any(rn in sp for sp in out):
            continue
        start = s.find(rn)
        assert start >= 0, f"speed_raw 不在证据里: {raw!r}"
        end = start + len(rn)
        offs, pos = [], 0
        for sp in out:
            offs.append((pos, pos + len(sp)))
            pos += len(sp) + 1
        lo = next(i for i, (x, y) in enumerate(offs) if x <= start < y)
        hi = next(i for i, (x, y) in enumerate(offs) if x < end <= y)
        out[lo:hi + 1] = [" ".join(out[lo:hi + 1])]
    return out


def as_spans(v, raws):
    if v is None:
        return None
    if isinstance(v, str):
        return to_spans(v, raws)
    return [norm(s) for s in v]


def main():
    tie = pd.read_parquet(ROOT / "out" / "03_tier" / "tiered.parquet").set_index("id")
    cid2batch = {}
    for bf in sorted((OUT / "batches").glob("batch_*.txt")):
        for cid in BATCH_HEAD.findall(bf.read_text()):
            cid2batch[int(cid)] = bf.stem

    recs = []
    n_split = 0
    for bf in sorted(OUT.glob("batch_*.json")):
        if not re.fullmatch(r"batch_\d+", bf.stem):
            continue  # 排除 batch_NNN.fills.json（dict，不是批次记录列表）
        for r in json.loads(bf.read_text()):
            cid = r["comment_id"]
            t = tie.loc[cid]
            if isinstance(r["evidence_en"], str):
                n_split += 1
            m = {"record_id": r["record_id"], "comment_id": cid, "batch": bf.stem,
                 "month": t["month"], "by": t["by"], "time": str(t["time"]),
                 "hn_url": f"https://news.ycombinator.com/item?id={cid}", "tier": t["tier"]}
            for f in FIELDS[8:]:
                m[f] = r.get(f)
            m["evidence_en"] = as_spans(r["evidence_en"], [r["speed_raw"]])
            m["context_evidence_en"] = as_spans(r.get("context_evidence_en"), [])
            recs.append(m)

    DST.mkdir(parents=True, exist_ok=True)
    with (DST / "measurements.jsonl").open("w") as f:
        for m in recs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    df = pd.DataFrame(recs)[FIELDS]
    df["first_person"] = df["first_person"].map({True: "true", False: "false", "unclear": "unclear"})
    df.to_parquet(DST / "measurements.parquet", index=False)

    ex = [json.loads(l) for l in (OUT / "excluded.jsonl").read_text().splitlines() if l.strip()]
    for e in ex:
        t = tie.loc[e["comment_id"]]
        e.update({"batch": cid2batch[e["comment_id"]], "month": t["month"], "by": t["by"],
                  "hn_url": f"https://news.ycombinator.com/item?id={e['comment_id']}"})
    with (DST / "excluded.jsonl").open("w") as f:
        for e in ex:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    n_spans = sum(len(m["evidence_en"]) for m in recs)
    print(f"batches={len(set(m['batch'] for m in recs))} records={len(recs)} "
          f"comments={len(set(m['comment_id'] for m in recs))} excluded={len(ex)}")
    print(f"old_format_split={n_split} evidence_spans_total={n_spans}")
    print(f"-> {DST / 'measurements.jsonl'}")
    print(f"-> {DST / 'measurements.parquet'}")
    print(f"-> {DST / 'excluded.jsonl'}")


if __name__ == "__main__":
    main()