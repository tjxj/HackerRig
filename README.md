# HackerRig

**做 AI 买 Mac 还是攒显卡（4090）？** 这个项目从 Hacker News 2026 年的评论里，把网友**亲手跑本地大模型**的实测扒出来——什么机器、跑什么模型、每秒多少 token、满意还是后悔——做成一个能查的**离线静态网站**，用真实自述数据回答这个问题。

结论速览见 **[FINDINGS.md](FINDINGS.md)**（每条结论带中位数、票数和原帖链接）。

---

## 这是什么

- 一个**纯静态、可离线**的网站（`web/`），无需联网、无需构建、无任何外部依赖。
- 一套**按编号可重跑**的数据流水线（`scripts/`），从原始 HN parquet 一路到网站数据。
- 数据：2026-01 至 2026-08-22 的 HN 评论中，**1213 条**本地跑大模型的实测记录（其中 **1160 条**网友亲测、去重后），**790 条**生成速度进入统计，折成 **647 票**；**52 条**明确后悔（出自 **38 人**，后悔统计按人去重）。

网站有三个视图（「三问」）＋一个后悔页：
1. **按机器查**：各类机器（Mac / N 卡 / A 卡 / 统一内存主机 / 纯 CPU / SBC）的速度中位数与实测卡片。
2. **按模型查**：同一模型在不同机器上的表现。
3. **同模型对比**：选定一个模型，横向比各类机器（单卡口径，多卡/多机单列）。
- **后悔实测页**：顶部按人统计每类机器多少人报过亲测、其中多少人后悔、比例多少（一人多条只算一人）；下方后悔记录按机器分组、全列 52 条。
- 每张卡片都能点回 HN 原帖；速度、量化、引擎、上下文、满意度都来自原文，原文没写的填 `null`。

## 怎么打开

直接用浏览器打开即可，`file://` 协议就能正常工作（网址同步用 hash 实现，离线可还原）：

```bash
open web/index.html        # macOS
# 或在浏览器里直接打开 web/index.html
```

想起本地服务也可以（可选）：

```bash
cd web && python3 -m http.server 8000
# 浏览器访问 http://localhost:8000
```

不需要安装任何东西就能**看网站**。只有**重跑流水线**才需要 Python 依赖（见下）。

## 数据从哪来

- **来源**：Hugging Face 数据集 [`open-index/hacker-news`](https://huggingface.co/datasets/open-index/hacker-news)，按月分片的 parquet。
- **许可**：**ODC-By 1.0**（Open Data Commons Attribution License）。见 [数据许可与署名](#数据许可与署名)。
- **范围**：本项目只用了 `2026-01` 到 `2026-08-22` 的分片（8 个 parquet 文件），**只读，不改不删**。
- **schema**（依据数据集自带 README）：`type` 为 int8 枚举（1=story 2=comment 3=poll 4=pollopt 5=job）；`text` 是 HN 原始 HTML（`/` 写作 `&#x2F;`、`'` 写作 `&#x27;`）；缺失值用空串/0/空列表表示。

**放置数据**（重跑流水线时需要）：把 2026 年的 parquet 分片放到 `data/2026/`，或用环境变量指向任意位置：

```bash
export HACKERRIG_DATA=/path/to/hacker-news/data/2026
```

脚本默认读取仓库下的 `data/2026/`（可用 `HACKERRIG_DATA` 覆盖）。源数据始终只读。

## 统计口径

**进入统计的记录**：网友亲测（`first_person=true`）且去重保留（`dedup_status=keep`）。

**速度**：
- 统一为**单流生成速度 tok/s**（`speed_kind` 为 generation/unspecified，单位 tok/s；ms/token 已换算）。
- **区间取中点**进统计（如「25–30 tok/s」取 27.5），卡片仍显示原文；「超过 60」「最高 32」这类**单边界不进**。
- **不进普通中位数**：投机解码开启（MTP/DFlash/DSpark/EAGLE/草稿模型等）、扩散文本模型、0.0 跑不动、批量/峰值吞吐。这些在卡片上单独标注。
- **多卡/多机单列**：卡数写进机器名（如「2× RTX 3090」），与单卡分开算；同模型对比里单独成行。

**中位数（关键）**：
- **每人·每机器·每模型一票**——先取该人自己多条记录的中位数作为一票，再对所有票取中位数。避免话多的人刷屏。
- **不足 5 条样本的格子不给中位数**（只举例、不下结论）。

**满意度**：`satisfied`（满意）/ `mixed`（褒贬不一）/ `regret`（后悔）/ `neutral`（中性）/ `null`（未表态）。

**字段政策**：原文没写的一律填 `null`，**不推断、不编造**。从上文（父评论/故事标题）补来的信息打「补自上文」标记并链到来源评论。

## 怎么复现

依赖（仅重跑流水线需要）：Python 3 + `pandas` + `pyarrow`；浏览器测试另需 `playwright`（chromium）。

```bash
pip install pandas pyarrow playwright
python3 -m playwright install chromium
```

脚本按编号重跑（`-I` 隔离运行，避免当前目录干扰）。**所有脚本都不调用任何大模型 API**——抽取判断由 Claude（含并行子代理）**亲自读评论**做出，脚本只做机械编排/补全/审计：

```bash
# 阶段一：摸底 → 粗筛 → 分层
python3 -I scripts/01_profile.py        # 字段/类型/正文格式摸底
python3 -I scripts/01b_probe.py         # 校准探针
python3 -I scripts/02_coarse_filter.py  # 宽口径粗筛（llm AND (local OR hw OR speed)）
python3 -I scripts/03_tier.py           # 精读优先级分层

# 阶段二：精读抽取（Claude 子代理亲自读，脚本编排/补全/审计）
python3 -I scripts/04a_batches.py       # 切批
python3 -I scripts/04b_parents.py       # 父评论
python3 -I scripts/04c_ancestors.py     # 更深祖先（--ids）
python3 -I scripts/04e_context.py --batch batch_NNN   # 备齐精读上下文
python3 -I scripts/04g_batch_check.py --batch batch_NNN
python3 -I scripts/04d_apply_context.py               # 父链补全（幂等）
python3 -I scripts/04f_finalize.py --batch batch_NNN --next batch_MMM
python3 -I scripts/05_audit.py          # 全量审计
python3 -I scripts/06_merge.py          # 合并最终数据集
python3 -I scripts/05_audit.py --merged

# 阶段三：清洗归一 → 建站 → 测试
python3 -I scripts/07e_apply_norm.py    # 应用映射/裁定/口径补丁 → measurements_clean.jsonl + stats.json
python3 -I scripts/08_build_web.py      # 生成 web/data.js
python3 -I scripts/09_test_web.py       # 无头浏览器验收（桌面+手机）

# 阶段四：结论与开源整理
python3 -I scripts/14_step7_findings.py # 结论数据底稿（FINDINGS.md 的每个数字）
python3 -I scripts/15_step7_scan.py     # 开源前敏感信息扫描
```

- 中间结果落盘在 `out/<步骤号>_*/`（parquet/json/jsonl/counts/样本）。
- 随机样本固定种子 `SEED=42`，可复现。
- 第六步口径裁定与前后对比：`scripts/11_step6_scope.py`、`12_step6_apply.py`、`13_step6_compare.py`（产出 `out/07_clean/step6_compare.txt`）。

## 已知局限

- **自述，不是实验室基准**：量化、上下文长度、引擎、散热、后台负载各不相同，中位数只反映趋势，不能当采购跑分。
- **4090 样本不足**：单卡 4090 每个模型不到 5 票，FINDINGS 对 4090 **只举例、不下中位数结论**；类别中位用的是「N 卡整体」。
- **时间窗与新模型偏置**：2026-01 至 2026-08-22，Qwen3.8 / Qwen3.6 等新模型占多数，老模型样本偏少。
- **速度 ≠ 满意度**：有人速度够却因模型质量/审查后悔（见 FINDINGS 反直觉一节）。
- **覆盖范围**：精读了优先级最高的 1153 条评论（抽出 712 条、拆成 1213 条记录）；另有一层（A+，551 条）尚未精读，未纳入。
- **长上下文掉速**：很多数字是短上下文测的，长上下文/agentic 场景会明显更慢。

## 数据许可与署名

本网站与数据衍生自 **[`open-index/hacker-news`](https://huggingface.co/datasets/open-index/hacker-news)**，依 **ODC-By 1.0**（Open Data Commons Attribution License v1.0）授权。

- 许可全文：<https://opendatacommons.org/licenses/by/1.0/>
- **署名要求**：使用本数据时请注明来源「Hacker News 数据，来自 open-index/hacker-news（ODC-By）」，并保留指向原数据集的链接。
- 数据中包含**公开的 HN 用户名与评论文本**（含评论者自己提到的文件路径等），均为公开内容，按 ODC-By 再分发；本项目不收集任何私密个人信息。
- 原始评论版权归原作者；本项目仅为聚合与统计整理。

## 开源前检查（本地整理，未建仓库、未推送）

`scripts/15_step7_scan.py` 扫描交付物（`scripts/`、`web/`、根目录 `.md`）的结果：
- **密钥/令牌：0 处**；**邮箱：0 处**。
- **本机路径**：早期脚本里硬编码的数据目录已改为可配置（`HACKERRIG_DATA` / 相对 `data/2026`），源码不再含本机绝对路径。
- `web/data.js` 中出现的 `D:\...` 等路径是**公开评论原文**里网友自己的 Windows 路径，属数据内容，非本项目机密。
- 大体积中间产物（`out/`）与数据软链（`data/`）建议不入库（见 `.gitignore`）。

## 目录结构

```
HackerRig/
├── web/              # 静态网站（直接打开 index.html）
│   ├── index.html    # 三问视图
│   ├── regret.html   # 后悔实测页
│   ├── app.js / style.css
│   └── data.js       # 内嵌数据（window.HACKERRIG_DATA）
├── scripts/          # 按编号可重跑的流水线（01 → 15）
├── out/              # 中间结果与统计（建议不入库）
├── data/2026/        # 源 parquet（软链或自行下载，只读）
├── FINDINGS.md       # 结论（带中位数/票数/原帖链接）
├── README.md         # 本文件
└── CLAUDE.md         # 项目工作约定
```
