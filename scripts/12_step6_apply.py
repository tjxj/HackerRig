#!/usr/bin/env python3
"""Step 12 — 落地第六步口径裁定（纯机械合并，不调用任何模型）。

合并：
  机械：区间取中点进统计（仅亲测+keep+generation/unspecified，单边界不进）；扩散模型/0.0/批量峰值排除。
  子代理阅读裁定：decided/speculative_decisions.json、multicard_decisions.json、summary_clean.json。
产出：
  out/07_clean/fields_step6.json   （record_id → 字段补丁，供 07e 覆盖应用）
  更新 mapping_model.json（摘要↔标准名矛盾修正，含 jaimeyap DS4→DeepSeek-V4-Flash），原文件备份。
用法: python3 -I scripts/12_step6_apply.py   （需三个子代理产出就绪）
"""
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "out" / "07_clean"
DEC = CLEAN / "decided"
MERGE = ROOT / "out" / "06_merge"
# 从原始摘要的加工备注里回收「明确写出」的祖先评论 ID（父链故事/根评论/父故事…后紧跟 8 位 ID）。
ANCESTOR = re.compile(r"(?:父链故事|父链|根评论|父故事|父评论|故事标题|祖先)\D{0,6}(\d{8})")


def load(p):
    return json.loads(Path(p).read_text())


def main():
    scope = load(CLEAN / "step6_scope.json")
    recs = {r["record_id"]: r for r in (json.loads(l) for l in (CLEAN / "measurements_clean.jsonl").read_text().splitlines() if l.strip())}
    # 原始摘要（06_merge，从未清洗）用于回收祖先 ID；从头重跑时此处即原文，稳定可复现。
    raw_summ = {}
    if (MERGE / "measurements.jsonl").exists():
        for l in (MERGE / "measurements.jsonl").read_text().splitlines():
            if l.strip():
                rr = json.loads(l)
                raw_summ[rr["record_id"]] = rr.get("summary_zh") or ""

    # 子代理产出 + 覆盖校验
    spec = load(DEC / "speculative_decisions.json")
    multi = load(DEC / "multicard_decisions.json")
    summ = load(DEC / "summary_clean.json")
    spec_ids = {x["record_id"] for x in scope["speculative"]}
    multi_ids = {x["record_id"] for x in scope["multi"]}
    if {x["record_id"] for x in spec} != spec_ids:
        raise SystemExit(f"speculative 覆盖不符 missing={spec_ids - {x['record_id'] for x in spec}}")
    if {x["record_id"] for x in multi} != multi_ids:
        raise SystemExit(f"multi 覆盖不符 missing={multi_ids - {x['record_id'] for x in multi}}")
    note_ids = {x["record_id"] for x in scope["notes"]}
    summ_ids = {x["record_id"] for x in summ}
    if not note_ids <= summ_ids:
        raise SystemExit(f"summary 未覆盖全部 notes missing={note_ids - summ_ids}")

    fields = {}

    def patch(rid):
        return fields.setdefault(rid, {})

    # 1) 区间取中点（亲测+keep）
    n_range = 0
    for x in scope["ranges"]:
        if x["fp"] and x["dedup"] == "keep":
            p = patch(x["record_id"])
            p.update(speed_stat="include", speed_value=x["mid"], speed_unit="tok/s",
                     speed_converted=True, range_converted=True,
                     speed_stat_reason=f"区间「{x['speed_raw']}」取中点 {x['mid']} tok/s 进统计（卡片显示原文）")
            n_range += 1

    # 2) 扩散模型排除
    for x in scope["diffusion"]:
        p = patch(x["record_id"])
        p.update(diffusion=True, speed_stat="exclude",
                 speed_stat_reason="扩散文本模型，tok/s 与自回归不可比，不进中位数（卡片标「扩散模型」）")

    # 3) 0.0 跑不动排除
    for x in scope["zero"]:
        p = patch(x["record_id"])
        p.update(stalled=True, speed_stat="exclude",
                 speed_stat_reason="0.0 tok/s 视为跑不动，不进中位数（卡片标「跑不动」）")

    # 4) 投机解码（子代理）：ON 排除并标记；OFF 仅标记不改动既有口径
    n_spec_on = 0
    for s in spec:
        p = patch(s["record_id"])
        p["speculative"] = bool(s["speculative"])
        p["spec_method"] = s.get("spec_method")
        if s["speculative"]:
            p.update(speed_stat="exclude",
                     speed_stat_reason=f"投机解码（{s.get('spec_method') or '未注明'}）开启测得，不进普通中位数")
            n_spec_on += 1

    # 5) 多卡多机（子代理）：machine_canon 改为含卡数标签 + 标记
    n_multi = 0
    labels = Counter()
    for m in multi:
        if m["multi"]:
            p = patch(m["record_id"])
            p.update(multi_card=True, gpu_count=m.get("gpu_count"), machine_canon=m["machine_label"])
            labels[m["machine_label"]] += 1
            n_multi += 1

    # 6) 批量/峰值硬修正（回原文确认）
    patch("49336793#2").update(speed_stat="exclude",
                             speed_stat_reason="672 为批量峰值（原文单流 82 tps），不进单流中位数")
    patch("49101615#1").update(speed_stat="exclude",
                             speed_stat_reason="880 tok/s 为批量任务总吞吐，不进单流中位数")

    # 7) 摘要清洗 + 补自上文 + 标准名矛盾修正（子代理）
    #    矛盾修正一律落到「该记录」的 canon（每条都有自身摘要/证据支撑）；
    #    仅当该 raw 值全站只此一条时，才同步改全局映射，避免误伤共用 raw 的其它记录。
    model_map = load(CLEAN / "mapping_model.json")
    midx = {e["raw"]: e for e in model_map}
    machine_map = load(CLEAN / "mapping_machine.json")
    machidx = {e["raw"]: e for e in machine_map}
    raw_model_n = Counter(r.get("model") for r in recs.values())
    raw_machine_n = Counter(r.get("machine") for r in recs.values())
    n_clean = n_mismatch = n_ancestor = 0
    mismatches = []
    ancestor_recovered = []
    model_map_changed = machine_map_changed = False
    for s in summ:
        p = patch(s["record_id"])
        if s.get("summary_clean"):
            p["summary_zh"] = s["summary_clean"]
            n_clean += 1
        if "context_supplemented" in s:
            p["context_supplemented"] = bool(s["context_supplemented"])
        # 补自上文徽章须链到「那条评论」：缺祖先 ID 时，从原始摘要明确写出的备注回收（不推断）。
        if p.get("context_supplemented") and not recs[s["record_id"]].get("context_ancestor_id"):
            am = ANCESTOR.search(raw_summ.get(s["record_id"], ""))
            if am:
                p["context_ancestor_id"] = int(am.group(1))
                n_ancestor += 1
                ancestor_recovered.append((s["record_id"], int(am.group(1))))
        mm = s.get("mismatch")
        if mm:
            n_mismatch += 1
            mismatches.append((s["record_id"], mm))
            base = recs[s["record_id"]]
            if mm["field"] == "model_canon":
                p["model_canon"] = mm["proposed"]
                raw = base.get("model")
                if raw in midx and raw_model_n[raw] == 1:
                    midx[raw]["canonical"] = mm["proposed"]
                    midx[raw]["note"] = "第六步摘要↔标准名核对修正"
                    model_map_changed = True
            elif mm["field"] == "machine_canon":
                p["machine_canon"] = mm["proposed"]
                raw = base.get("machine")
                if raw in machidx and raw_machine_n[raw] == 1:
                    machidx[raw]["canonical"] = mm["proposed"]
                    machidx[raw]["note"] = "第六步摘要↔标准名核对修正"
                    machine_map_changed = True

    # 备份（保留首次 before 快照）+ 仅在确有全局改动时写映射
    if model_map_changed:
        bk = CLEAN / "mapping_model_before_step6.json"
        if not bk.exists():
            shutil.copy2(CLEAN / "mapping_model.json", bk)
        (CLEAN / "mapping_model.json").write_text(json.dumps(model_map, ensure_ascii=False, indent=2) + "\n")
    if machine_map_changed:
        bk = CLEAN / "mapping_machine_before_step6.json"
        if not bk.exists():
            shutil.copy2(CLEAN / "mapping_machine.json", bk)
        (CLEAN / "mapping_machine.json").write_text(json.dumps(machine_map, ensure_ascii=False, indent=2) + "\n")

    (CLEAN / "fields_step6.json").write_text(json.dumps(fields, ensure_ascii=False, indent=1) + "\n")

    print("=== 第六步口径合并 ===")
    print(f"  区间取中点进统计(亲测+keep): {n_range}")
    print(f"  扩散模型排除: {len(scope['diffusion'])}  0.0跑不动排除: {len(scope['zero'])}")
    print(f"  投机解码候选 {len(spec)}，其中 ON 排除 {n_spec_on}，OFF/误报 {len(spec)-n_spec_on}")
    print(f"  多卡多机标记: {n_multi}，distinct 标签 {len(labels)}")
    print(f"  批量/峰值硬修正: 2 (49336793#2, 49101615#1)")
    print(f"  摘要清洗: {n_clean}  标准名矛盾修正: {n_mismatch}  祖先ID回收: {n_ancestor}")
    for rid, aid in ancestor_recovered:
        print(f"    祖先ID回收 {rid} -> {aid}")
    for rid, mm in mismatches:
        print(f"    {rid}: {mm['field']} {mm['current']} -> {mm['proposed']}")
    print(f"  fields_step6 补丁记录数: {len(fields)}")
    print(f"  多卡标签样例: {labels.most_common(10)}")
    print(f"-> {CLEAN / 'fields_step6.json'} ; mapping_model.json 已更新")


if __name__ == "__main__":
    main()
