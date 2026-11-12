#!/usr/bin/env python3
"""Step 07b — params 归一映射（纯机械，不调用任何模型）。

params 多为 "27B"/"27b" 大小写变体：统一单位后缀大写、规范数字。
少数特殊值（无单位、区间、万亿写法）单独处理或标 uncertain。
输出 out/07_clean/mapping_params.json + uncertain_params.json。
用法: python3 -I scripts/07b_params_map.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "out" / "07_clean"
NUM_UNIT = re.compile(r"^(\d+(?:\.\d+)?)([bBmMtT])$")


def norm_num(s: str) -> str:
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def main():
    raws = []
    for line in (DST / "distinct_params.txt").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        raws.append(parts[2])
    mapping, uncertain = [], []
    for raw in raws:
        m = NUM_UNIT.match(raw)
        if m:
            canon = norm_num(m.group(1)) + m.group(2).upper()
            mapping.append({"raw": raw, "canonical": canon, "confidence": "high", "note": ""})
        elif raw == "2.8-trillion-parameter":
            mapping.append({"raw": raw, "canonical": "2.8T", "confidence": "high",
                            "note": "万亿参数写法归一为 2.8T"})
        elif raw == "8x7B":
            mapping.append({"raw": raw, "canonical": "8x7B", "confidence": "high", "note": "MoE 配置"})
        elif raw in ("70b-120b", "20-30B"):
            canon = {"70b-120b": "70B-120B", "20-30B": "20B-30B"}[raw]
            mapping.append({"raw": raw, "canonical": canon, "confidence": "high", "note": "参数量区间"})
        elif raw in ("26", "27"):
            e = {"raw": raw, "canonical": raw, "confidence": "uncertain",
                 "question": f"params='{raw}' 无单位后缀，疑似 {raw}B；是否补 B？不推断则保留原文。",
                 "options": [f"{raw}B", raw]}
            mapping.append({"raw": raw, "canonical": raw, "confidence": "uncertain",
                            "note": "无单位后缀，不推断"})
            uncertain.append(e)
        else:
            mapping.append({"raw": raw, "canonical": raw, "confidence": "unmapped", "note": "保留原文"})
    (DST / "mapping_params.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")
    (DST / "uncertain_params.json").write_text(json.dumps(uncertain, ensure_ascii=False, indent=2) + "\n")
    from collections import Counter
    cc = Counter(e["confidence"] for e in mapping)
    print(f"params distinct={len(raws)} entries={len(mapping)} "
          f"high={cc['high']} uncertain={cc['uncertain']} unmapped={cc['unmapped']} "
          f"canonical={len(set(e['canonical'] for e in mapping))}")


if __name__ == "__main__":
    main()