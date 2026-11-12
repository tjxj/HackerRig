#!/usr/bin/env python3
"""Step 02 — 粗筛：从 2026 年评论里宽口径捞出「本地跑大模型的硬件和速度」候选。

规则（宽口径，宁可多捞，下一步精读）：
  匹配前先做 html.unescape（HN 把 / 写成 &#x2F;、' 写成 &#x27; 等，
  不还原会漏掉 t/s、tok/s 这类含斜杠的词）；<p> 还原为换行。
  落盘 text 列仍是原始 HTML，不做任何改写。
  四类信号（大小写不敏感正则）：
    llm   — 模型家族/运行时/量化格式/模型尺寸/云模型名等
    local — local(ly)/self-host/on-device/my own hardware/at home 等
    hw    — Mac/M系芯片/GPU型号/VRAM/RAM/CPU/边缘设备等
    speed — tokens per second/t/s/throughput/latency/fast/slow/benchmark 等
  命中 = llm AND (local OR hw OR speed)
  差一点（near）= 未命中且满足其一：
    A: 只有 llm 信号（local/hw/speed 全无）
    B: 无 llm 信号，但 local/hw/speed 中至少两类
  跳过：空正文、正文恰为 [dead]/[flagged]/[deleted] 占位符（计数并报告）。
  dead=1 但正文仍在的评论保留（带 dead 标记，精读再定）。

输出（HackerRig/out/02_coarse/）：
  hits.parquet / near.parquet  — 全量候选与差一点池（含信号标志、命中词、原文）
  counts.json                  — 每月进出数量
  filter_spec.json             — 本次使用的全部正则（审计用）
  samples_hits.txt / samples_near.txt — 固定种子随机各 20 条（near: A/B 各 10）
用法: python3 -I scripts/02_coarse_filter.py
"""
import html
import json
import random
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import os
DATA = Path(os.environ.get("HACKERRIG_DATA", str(Path(__file__).resolve().parent.parent / "data" / "2026")))
OUT = Path(__file__).resolve().parent.parent / "out" / "02_coarse"
SEED = 42
PLACEHOLDERS = {"[dead]", "[flagged]", "[deleted]"}
COLS = ["id", "type", "by", "time", "text", "parent", "dead", "deleted"]
# 招聘帖提示（Who is hiring 等），只打标不排除，精读再用
JOBPOST = re.compile(
    r"^Location:|\b(?:full-time|part-time|contract)\b[^.]{0,80}\b(?:onsite|remote)\b"
    r"|\b(?:onsite|remote)\b[^.]{0,80}\b(?:full-time|part-time|contract)\b", re.I)

# ---------------------------------------------------------------- 词表
# 每项: (标签, 正则)。内部一律用非捕获组 (?:...)。
LLM = [
    ("llm", r"\bllms?\b"),
    ("language_model", r"\b(?:large |small )?language models?\b"),
    ("slm", r"\bslms?\b"),
    ("llama", r"\bllama"),
    ("qwen", r"\bqwen"),
    ("mistral", r"\bmistral"),
    ("mixtral", r"\bmixtral"),
    ("deepseek", r"\bdeepseek"),
    ("gemma", r"\bgemma"),
    ("phi", r"\bphi-?[0-9]"),
    ("gpt_oss", r"\bgpt[- ]?oss\b"),
    ("tinyllama", r"\btinyllama"),
    ("vicuna", r"\bvicuna"),
    ("wizardlm", r"\bwizardlm"),
    ("starcoder", r"\bstarcoder"),
    ("codegemma", r"\bcodegemma"),
    ("smollm", r"\bsmollm"),
    ("nemotron", r"\bnemotron"),
    ("granite", r"\bgranite"),
    ("exaone", r"\bexaone"),
    ("internlm", r"\binternlm"),
    ("minicpm", r"\bminicpm"),
    ("chatglm", r"\bchatglm"),
    ("glm", r"\bglm-?[0-9]"),
    ("baichuan", r"\bbaichuan"),
    ("hunyuan", r"\bhunyuan"),
    ("ernie", r"\bernie"),
    ("olmo", r"\bolmo"),
    ("openchat", r"\bopenchat"),
    ("stablelm", r"\bstablelm"),
    ("command_r", r"\bcommand-?r\b"),
    ("kimi", r"\bkimi[- ]?k?[0-9]"),
    ("grok", r"\bgrok[- ]?[0-9]"),
    ("falcon", r"\bfalcon[- ]?[0-9]"),
    ("yi", r"\byi[- ]?[0-9]"),
    ("solar", r"\bsolar[- ]?[0-9]"),
    ("dolphin", r"\bdolphin[- ]?[0-9]"),
    ("orca", r"\borca[- ]?[0-9]"),
    ("aya", r"\baya[- ]?[0-9]"),
    ("bloom", r"\bbloom[- ]?[0-9]"),
    ("hermes", r"\bhermes[- ]?[0-9]"),
    ("nous", r"\bnous[- ]"),
    ("claude", r"\bclaude"),
    ("chatgpt", r"(?<!utm_source=)\bchatgpt\b"),
    ("gpt_n", r"\bgpt-?[0-9o]"),
    ("gemini", r"\bgemini"),
    ("copilot", r"\bcopilot"),
    ("ollama", r"\bollama"),
    ("llama_cpp", r"\bllama[.-]?cpp"),
    ("llamafile", r"\bllamafile"),
    ("lm_studio", r"\blm[ -]?studio"),
    ("vllm", r"\bvllm"),
    ("sglang", r"\bsglang"),
    ("exllama", r"\bexllama"),
    ("kobold", r"\bkobold"),
    ("gpt4all", r"\bgpt4all"),
    ("localai", r"\blocal-?ai\b"),
    ("mlc", r"\bmlc\b"),
    ("mlx", r"\bmlx\b"),
    ("oobabooga", r"\boobabooga"),
    ("tg_webui", r"\btext-generation-(?:webui|inference)\b"),
    ("tabby", r"\btabby(?:api)?\b"),
    ("aphrodite", r"\baphrodite\b"),
    ("tgi", r"\btgi\b"),
    ("jan_ai", r"\bjan\.ai\b"),
    ("openwebui", r"\bopen-?webui\b"),
    ("anythingllm", r"\banythingllm"),
    ("gguf", r"\bgguf"),
    ("ggml", r"\bggml"),
    ("awq", r"\bawq\b"),
    ("gptq", r"\bgptq"),
    ("exl2", r"\bexl2\b"),
    ("quant_fmt", r"\bi?q[2-8]_[a-z0-9_]+"),
    ("bpw", r"\bbpw\b"),
    ("bit", r"\b\d(?:\.\d)?-?bit\b"),
    ("fp", r"\b(?:fp16|bf16|fp8|f16|f32|int8|int4)\b"),
    ("quantize", r"\bquantiz(?:ed|ation|e|ing)\b"),
    ("size_b", r"\b\d{1,4}(?:\.\d+)?b\b"),
    ("size_ab", r"\ba\d{1,3}b\b"),
    ("moe", r"\bmoe\b"),
    ("moe_full", r"\bmixture of experts\b"),
    ("ctx", r"\bctx[- ]size\b"),
    ("ctx_bare", r"\bctx\b"),
    ("context", r"\bcontext (?:size|window|length)\b"),
    ("context_nk", r"\b\d{1,3}k context\b"),
    ("kv_cache", r"\bkv[- ]?cache\b"),
    ("ngl", r"\bngl\b"),
    ("n_gpu_layers", r"\bn-gpu-layers\b"),
    ("flash_attn", r"\bflash[- ]?attn\b"),
    ("flash_attention", r"\bflash attention\b"),
    ("inference", r"\binference\b"),
    ("open_weights", r"\bopen[- ]?weights?\b"),
    ("finetune", r"\bfine[- ]?tun(?:e|ed|ing)\b"),
]
LOCAL = [
    ("local", r"\blocal(?:ly)?\b"),
    ("self_host", r"\bself[- ]?host(?:ed|ing)?\b"),
    ("on_prem", r"\bon[- ]?prem\b"),
    ("on_device", r"\bon[- ]device\b"),
    ("at_home", r"\bat home\b"),
    ("homelab", r"\bhome ?lab\b"),
    ("home_server", r"\bhome server\b"),
    ("my_machine", r"\bmy (?:own )?(?:machine|box|rig|server|desktop|laptop|hardware|setup|pc|mac|gpu|cpu)\b"),
    ("own_hw", r"\bown (?:hardware|machine|box|server|gpu|rig|silicon)\b"),
    ("offline", r"\boffline\b"),
    ("air_gapped", r"\bair[- ]?gapped\b"),
    ("no_cloud", r"\bwithout (?:using )?(?:the )?cloud\b"),
]
HW = [
    ("mac", r"\bmacs?\b"),
    ("macbook", r"\bmacbook"),
    ("mac_mini", r"\bmac ?mini\b"),
    ("mac_studio", r"\bmac ?studio\b"),
    ("mac_pro", r"\bmac ?pro\b"),
    ("macos", r"\bmacos\b"),
    ("mbp", r"\bmbp\b"),
    ("apple_silicon", r"\bapple silicon\b"),
    ("unified_memory", r"\bunified memory\b"),
    ("m_chip", r"\bm[1-5](?: (?:pro|max|ultra))?\b"),
    ("gpu", r"\bgpus?\b"),
    ("vram", r"\bvram\b"),
    ("rtx", r"\brtx\b"),
    ("gtx", r"\bgtx\b"),
    ("geforce", r"\bgeforce\b"),
    ("radeon", r"\bradeon\b"),
    ("radeon_rx", r"\b(?:rx ?)?(?:6[6-9]00|7[6-9]00|9070)(?: ?xtx?| ?gre)?\b"),
    ("nv_consumer", r"\b(?:10|20|30|40|50)(?:60|70|80|90)(?: ?ti)?\b"),
    ("rtx_pro_6000", r"\brtx (?:pro )?6000\b"),
    ("blackwell", r"\bblackwell\b"),
    ("hopper", r"\bhopper\b"),
    ("dc_gpu", r"\b(?:a100|h100|h200|b200|gb200|gb10|v100|p40|p100|a6000|a5000|a4000|a40|l40s|t4)\b"),
    ("dgx", r"\bdgx\b"),
    ("hgx", r"\bhgx\b"),
    ("instinct", r"\binstinct\b"),
    ("mi", r"\bmi[0-9]{3}x?\b"),
    ("arc", r"\b(?:a770|a750|b580|b570)\b"),
    ("intel_arc", r"\bintel arc\b"),
    ("ryzen", r"\bryzen\b"),
    ("threadripper", r"\bthreadripper\b"),
    ("epyc", r"\bepyc\b"),
    ("xeon", r"\bxeon\b"),
    ("strix", r"\bstrix (?:halo|point)\b"),
    ("ai_max", r"\bryzen ai max\b"),
    ("lunar_lake", r"\blunar lake\b"),
    ("cpu", r"\bcpus?\b"),
    ("ram", r"\bram\b"),
    ("ddr", r"\bddr[45]\b"),
    ("mem_bw", r"\bmemory bandwidth\b"),
    ("gb", r"\b\d{1,4} ?gb\b"),
    ("graphics_card", r"\b(?:graphics|video) cards?\b"),
    ("laptop", r"\blaptops?\b"),
    ("desktop", r"\bdesktops?\b"),
    ("workstation", r"\bworkstations?\b"),
    ("server", r"\bservers?\b"),
    ("rig", r"\brig\b"),
    ("raspberry_pi", r"\braspberry ?pi\b"),
    ("orange_pi", r"\borange ?pi\b"),
    ("jetson", r"\bjetson\b"),
    ("orin", r"\borin\b"),
    ("rk3588", r"\brk3588\b"),
    ("rockchip", r"\brockchip\b"),
    ("radxa", r"\bradxa\b"),
    ("npu", r"\bnpu\b"),
    ("snapdragon", r"\bsnapdragon\b"),
    ("iphone", r"\biphone\b"),
    ("android", r"\bandroid\b"),
    ("framework", r"\bframework (?:laptop|13|16)\b"),
    ("groq", r"\bgroq\b"),
    ("cerebras", r"\bcerebras\b"),
    ("tpu", r"\btpus?\b"),
]
SPEED = [
    ("tok_per_s", r"\btokens?\s*/\s*s"),
    ("tokens_per_second", r"\btokens? (?:per|a) second"),
    ("tok_s", r"\btok\s*/\s*s"),
    ("t_s", r"\bt/s\b"),
    ("tps", r"\btps\b"),
    ("ms_per_token", r"\bms (?:per|/) ?token"),
    ("prompt_eval", r"\bprompt eval\b"),
    ("prompt_processing", r"\bprompt processing\b"),
    ("specdec", r"\bspecdec\b"),
    ("spec_decoding", r"\bspeculative decoding\b"),
    ("throughput", r"\bthroughput\b"),
    ("latency", r"\blatency\b"),
    ("speed", r"\bspeed(?:s|up)?\b"),
    ("fast", r"\bfast(?:er|est)?\b"),
    ("slow", r"\bslow(?:er|down)?\b"),
    ("benchmark", r"\bbenchmark(?:s|ing|ed)?\b"),
    ("perf", r"\bperf(?:ormance)?\b"),
]
CATEGORIES = {"llm": LLM, "local": LOCAL, "hw": HW, "speed": SPEED}

FLAG_RE = {k: re.compile("|".join(p for _, p in v), re.I) for k, v in CATEGORIES.items()}
MATCH_RE = {
    k: re.compile("|".join(f"(?P<g{i}>{p})" for i, (_, p) in enumerate(v)), re.I)
    for k, v in CATEGORIES.items()
}
LABELS = {k: [lab for lab, _ in v] for k, v in CATEGORIES.items()}


def matched_labels(cat: str, text: str):
    found = []
    for m in MATCH_RE[cat].finditer(text):
        lab = LABELS[cat][int(m.lastgroup[1:])]
        if lab not in found:
            found.append(lab)
    return ";".join(found)


def norm(text: str) -> str:
    """匹配层归一化：还原 HTML 实体，<p> 变换行。其余标签保留（避免跨标签拼词）。"""
    return html.unescape(text).replace("<p>", "\n")


A_TAG = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>', re.S)
TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    t = html.unescape(text)
    t = t.replace("<p>", "\n")
    t = A_TAG.sub(lambda m: f"{m.group(2)} ({html.unescape(m.group(1))})", t)
    t = TAG.sub("", t)
    return t.strip()


def sample_block(row, extra="") -> str:
    head = (f"----- id={row['id']} | {row['month']} | by={row['by']} | time={row['time']} "
            f"| dead={row['dead']}{extra} -----\n"
            f"signals: llm={row['f_llm']} local={row['f_local']} hw={row['f_hw']} speed={row['f_speed']}\n"
            f"matched: llm[{row['m_llm']}] local[{row['m_local']}] hw[{row['m_hw']}] speed[{row['m_speed']}]\n")
    return head + clean(row["text"]) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*.parquet"))
    assert files, f"no parquet under {DATA}"

    counts = {"months": [], "totals": {}}
    hit_parts, near_parts = [], []
    tot = dict(comments=0, empty_text=0, placeholder=0, scanned=0,
               hits=0, near_a=0, near_b=0)

    for f in files:
        month = f.stem
        df = pq.ParquetFile(f).read(columns=COLS).to_pandas()
        c = df[df["type"] == 2].copy()
        n_comments = len(c)
        stripped = c["text"].str.strip()
        empty = stripped.eq("")
        placeholder = stripped.isin(PLACEHOLDERS)
        keep = ~(empty | placeholder)
        c = c[keep].copy()
        n_scanned = len(c)

        txt = c["text"].map(norm)
        for cat in CATEGORIES:
            c[f"f_{cat}"] = txt.str.contains(FLAG_RE[cat], regex=True)
        hit_mask = c["f_llm"] & (c["f_local"] | c["f_hw"] | c["f_speed"])
        n_sig = c["f_local"].astype(int) + c["f_hw"].astype(int) + c["f_speed"].astype(int)
        near_a_mask = c["f_llm"] & (n_sig == 0)
        near_b_mask = (~c["f_llm"]) & (n_sig >= 2)

        any_sig = c["f_llm"] | c["f_local"] | c["f_hw"] | c["f_speed"]
        sub = c[any_sig]
        for cat in CATEGORIES:
            c[f"m_{cat}"] = ""
            idx = sub.index[sub[f"f_{cat}"]]
            c.loc[idx, f"m_{cat}"] = [matched_labels(cat, t) for t in txt.loc[idx]]
        c["month"] = month
        c["jobpost_hint"] = c["text"].str.strip().str.contains(JOBPOST, regex=True)

        hits = c[hit_mask]
        near = c[near_a_mask | near_b_mask].copy()
        near["near_reason"] = "A_llm_only"
        near.loc[near_b_mask[near.index], "near_reason"] = "B_no_llm_multi"
        hit_parts.append(hits)
        near_parts.append(near)

        m = dict(month=month, comments=n_comments, empty_text=int(empty.sum()),
                 placeholder=int(placeholder.sum()), scanned=n_scanned,
                 hits=len(hits), near_a=int(near_a_mask.sum()), near_b=int(near_b_mask.sum()))
        counts["months"].append(m)
        for k in tot:
            tot[k] += m[k]
        print(f"{month}: comments={n_comments} empty={m['empty_text']} placeholder={m['placeholder']} "
              f"scanned={n_scanned} hits={m['hits']} near_a={m['near_a']} near_b={m['near_b']}")

    hits = pd.concat(hit_parts, ignore_index=True)
    near = pd.concat(near_parts, ignore_index=True)
    dup = int(hits["id"].duplicated().sum())
    counts["totals"] = tot
    counts["totals"]["hit_duplicate_ids"] = dup
    counts["totals"]["hit_rate_of_scanned"] = round(tot["hits"] / tot["scanned"], 4)
    counts["hits_signal_breakdown"] = {
        "with_local": int(hits["f_local"].sum()),
        "with_hw": int(hits["f_hw"].sum()),
        "with_speed": int(hits["f_speed"].sum()),
        "llm_only_of_hits": int((~(hits["f_local"] | hits["f_hw"] | hits["f_speed"])).sum()),
        "dead_flagged": int(hits["dead"].sum()),
        "jobpost_hint": int(hits["jobpost_hint"].sum()),
    }

    keep_cols = ["id", "month", "time", "by", "parent", "dead", "deleted",
                 "f_llm", "f_local", "f_hw", "f_speed",
                 "m_llm", "m_local", "m_hw", "m_speed", "jobpost_hint", "text"]
    hits[keep_cols].to_parquet(OUT / "hits.parquet", index=False)
    near[keep_cols + ["near_reason"]].to_parquet(OUT / "near.parquet", index=False)
    (OUT / "counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2))
    (OUT / "filter_spec.json").write_text(json.dumps(
        {k: v for k, v in CATEGORIES.items()}, ensure_ascii=False, indent=2))

    rng = random.Random(SEED)
    hit_idx = rng.sample(range(len(hits)), min(20, len(hits)))
    hit_sample = hits.iloc[sorted(hit_idx)]
    (OUT / "samples_hits.txt").write_text("\n".join(sample_block(r) for _, r in hit_sample.iterrows()))

    na = near[near["near_reason"] == "A_llm_only"]
    nb = near[near["near_reason"] == "B_no_llm_multi"]
    ia = rng.sample(range(len(na)), min(10, len(na)))
    ib = rng.sample(range(len(nb)), min(10, len(nb)))
    near_sample = pd.concat([na.iloc[sorted(ia)], nb.iloc[sorted(ib)]])
    (OUT / "samples_near.txt").write_text(
        "\n".join(sample_block(r, f" | near={r['near_reason']}") for _, r in near_sample.iterrows()))

    print("\n=== TOTALS ===")
    print(json.dumps(counts["totals"], ensure_ascii=False, indent=2))
    print("hits signal breakdown:", json.dumps(counts["hits_signal_breakdown"]))
    print(f"wrote hits.parquet({len(hits)}) near.parquet({len(near)}) counts.json "
          f"filter_spec.json samples_hits.txt samples_near.txt -> {OUT}")


if __name__ == "__main__":
    main()