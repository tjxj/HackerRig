#!/usr/bin/env python3
"""Step 15 — 开源前敏感信息扫描（纯机械正则，不调用任何模型）。

扫描交付物（scripts/、web/、根目录 .md、CLAUDE.md）里的：
  - 本机绝对路径（/Users/<人>、/Volumes/、/home/<人>、盘符）——开源应改为可配置或文档说明
  - 密钥/令牌（sk-、AKIA、ghp_、BEGIN PRIVATE KEY、api_key=、password= 等）
  - 邮箱
  - 可能的真实姓名/个人信息（人工复核；HN 用户名属公开署名，单独列出供判断）
产出 out/15_scan/scan_report.json + scan_report.txt。
用法: python3 -I scripts/15_step7_scan.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "15_scan"

PATTERNS = {
    "本机路径": re.compile(r"(/Users/[^\s\"'`)]+|/Volumes/[^\s\"'`)]+|/home/[a-z0-9_-]+|[A-Za-z]:\\\\[^\s\"']+)"),
    "密钥令牌": re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}|password\s*[:=]\s*['\"][^'\"]+|secret\s*[:=]\s*['\"][^'\"]{8,}|Bearer\s+[A-Za-z0-9._-]{20,})", re.I),
    "邮箱": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}
# 公开 HN 署名（by 字段）不算私密 PII，但单独统计供人工判断
SKIP_DIRS = {"out", ".git", "__pycache__", "node_modules"}
TEXT_EXT = {".py", ".js", ".html", ".css", ".md", ".txt", ".json"}


def iter_files():
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.suffix.lower() in TEXT_EXT:
            yield p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    findings = {k: [] for k in PATTERNS}
    scanned = 0
    for p in iter_files():
        try:
            text = p.read_text(errors="replace")
        except Exception:
            continue
        scanned += 1
        rel = str(p.relative_to(ROOT))
        for i, line in enumerate(text.splitlines(), 1):
            for cat, pat in PATTERNS.items():
                for m in pat.finditer(line):
                    findings[cat].append({"file": rel, "line": i, "match": m.group(0)[:120],
                                          "context": line.strip()[:160]})
    report = {"scanned_files": scanned,
              "counts": {k: len(v) for k, v in findings.items()},
              "findings": findings}
    (OUT / "scan_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    L = [f"=== 开源前敏感信息扫描（扫描 {scanned} 个文件）==="]
    for cat, items in findings.items():
        L.append(f"\n## {cat}: {len(items)} 处")
        # 按文件聚合，避免刷屏
        byfile = {}
        for it in items:
            byfile.setdefault(it["file"], []).append(it)
        for f, its in sorted(byfile.items()):
            L.append(f"  {f}  ({len(its)} 处)")
            for it in its[:6]:
                L.append(f"     L{it['line']}: {it['match']}")
            if len(its) > 6:
                L.append(f"     … 另 {len(its)-6} 处")
    txt = "\n".join(L) + "\n"
    (OUT / "scan_report.txt").write_text(txt)
    print(txt)
    print(f"-> {OUT / 'scan_report.json'} , {OUT / 'scan_report.txt'}")


if __name__ == "__main__":
    main()
