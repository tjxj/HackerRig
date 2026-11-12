#!/usr/bin/env python3
"""Step 08 — 生成静态查询站数据（纯机械，不调用任何模型）。

读 out/07_clean/measurements_clean.jsonl + stats.json，产出 web/data.js（内嵌 JSON，离线可用）。
保留卡片与统计所需字段；计算默认对比模型（亲测+去重后样本最多的模型）。
用法: python3 -I scripts/08_build_web.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "out" / "07_clean" / "measurements_clean.jsonl"
STATS = ROOT / "out" / "07_clean" / "stats.json"
WEB = ROOT / "web"

KEEP = ["record_id", "comment_id", "by", "time", "month", "hn_url",
        "machine", "machine_canon", "machine_category", "memory",
        "model", "model_canon", "params_canon", "quant_canon", "engine_canon",
        "context_length", "concurrency", "speed_raw", "speed_value", "speed_unit",
        "speed_kind", "speed_stat", "speed_stat_reason", "speed_converted",
        "speed_value_original", "speed_unit_original", "price", "first_person",
        "sentiment", "summary_zh", "evidence_en", "context_evidence_en",
        "dedup_status", "anomaly_flags",
        "speculative", "spec_method", "multi_card", "gpu_count", "diffusion",
        "stalled", "range_converted", "context_supplemented", "context_ancestor_id"]
CAT_ORDER = ["Mac", "N卡", "A卡", "统一内存主机", "纯CPU", "SBC", "其他"]


def main():
    recs = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    stats = json.loads(STATS.read_text())
    out = [{k: r.get(k) for k in KEEP} for r in recs]

    stat_recs = [r for r in recs if r["first_person"] is True and r["dedup_status"] == "keep"]
    model_counts = Counter(r["model_canon"] for r in stat_recs if r.get("model_canon"))
    default_model = model_counts.most_common(1)[0][0]
    regret_fp = sum(1 for r in recs if r["first_person"] is True and r.get("sentiment") == "regret")
    # 后悔按人：分母=亲测去重人数，分子=其中后悔的去重人数（一人多条只算一人）
    stat_people = len({r["by"] for r in stat_recs})
    regret_people = len({r["by"] for r in stat_recs if r.get("sentiment") == "regret"})

    meta = {
        "source": "Hugging Face open-index/hacker-news",
        "license": "ODC-By",
        "range": "2026-01 至 2026-08-22",
        "generated": "2026-11-12",
        "total_records": len(recs),
        "fp_records": sum(1 for r in recs if r["first_person"] is True),
        "stat_records": len(stat_recs),
        "speed_stat_records": stats["speed_stat_records"],
        "regret_fp_records": regret_fp,
        "stat_people": stat_people,
        "regret_people": regret_people,
        "distinct_machine": stats["distinct_canonical"]["machine"],
        "distinct_model": stats["distinct_canonical"]["model"],
        "category_order": CAT_ORDER,
        "category_records": stats["category_records"],
        "default_compare_model": default_model,
        "overall_median": stats["speed_median_overall_tok_s"],
        "basis": {
            "count": "记录计数与列表默认只取网友亲测（first_person）且去重后的实测，共 %d 条。重复报告仍列出并标注，但不重复计数。" % len(stat_recs),
            "median": "速度中位数只取单流生成速度（tok/s，generation/unspecified，speed_stat=include），共 %d 条进入速度统计；按「同一人在同一机器同一模型上只算一票（取本人中位数）」计算，样本少于 5 条不给中位数。区间速度（如 25–30 tok/s）取中点进统计，卡片仍显示原文；「超过 60」「最高 32」这类单边界不进。多卡/多机（如 2× RTX 3090、两台 DGX Spark）与单卡单机分开计，第三问单独成行。" % stats["speed_stat_records"],
            "exclude": "总吞吐/批量峰值/并发拿不准/不可信/增量/字符级，以及投机解码（MTP/DFlash/EAGLE/草稿模型等）开启时测得的速度、扩散文本模型、0.0 tok/s（跑不动）都只做卡片、不进普通中位数，卡片上注明原因。同一帖里关闭投机解码测得的照常进。ms/token 已换算为 tok/s，卡片保留原文。",
            "supplement": "卡片摘要若由父评论/故事标题补全机器或模型等信息，标「补自上文」并链到那条评论；摘要不出现评论 ID 或内部加工备注。",
            "disclaimer": "全部数据为 Hacker News 网友自述，非标准化基准测试，仅供参考。",
        },
    }
    WEB.mkdir(exist_ok=True)
    payload = {"meta": meta, "records": out}
    (WEB / "data.js").write_text(
        "window.HACKERRIG_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
    size = (WEB / "data.js").stat().st_size
    print(f"records={len(out)} stat={len(stat_recs)} speed={stats['speed_stat_records']} "
          f"regret_fp={regret_fp} default_compare_model={default_model!r}")
    print(f"model_counts_top5={model_counts.most_common(5)}")
    print(f"-> {WEB / 'data.js'} ({size} bytes)")


if __name__ == "__main__":
    main()
