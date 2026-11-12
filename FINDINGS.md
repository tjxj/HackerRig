# 做 AI 买 Mac 还是攒 4090？——来自 Hacker News 2026 年网友实测的结论

> 数据基础：从 Hacker News 2026-01 至 2026-08-22 的评论里，扒出 **1213 条**本地跑大模型的实测记录，其中 **1160 条**是网友亲测（去重后），**790 条**生成速度进入统计，折成 **647 票**（每人·每机器·每模型一票，取该人自己的中位数，再对票取中位数；不足 5 条样本的格子只举例、不下结论）。
> 速度统一为**单流生成 tok/s**；投机解码开启、扩散模型、0.0 跑不动、批量/峰值吞吐都不进普通中位数（详见 [README](README.md) 口径）。
> 全部为网友自述，不是实验室基准；个体差异大，中位数只看趋势。**不到 5 票的格子本文只举例，不下结论。**

---

## 一句话答案（分场景）

- **跑稠密 27B（如 Qwen3.8-27B）追求快 → 攒 N 卡（4090 这一档）。** 同模型 Mac 中位只有 N 卡的约 1/4。
- **跑 MoE（如 Qwen3.6-35B-A3B，激活仅 3B）→ Mac 已经很能打，** 中位达到 N 卡的约 7 成，大统一内存还能装更大模型。
- **要装 100B+ 超大模型 → 大统一内存机器（Mac Ultra / Strix Halo / DGX Spark），** 但带宽是瓶颈，Strix Halo 是后悔重灾区。
- **4090 本身的实测样本太少（每个模型不到 5 票），下面只举例，不给 4090 的中位数结论。**

---

## 结论 1：跑稠密 27B 要快，N 卡明显胜过 Mac

以新模型 **Qwen3.8-27B**（稠密 27B）为例，单卡口径：

| 类别 | 中位 tok/s | 票数 | 样本 |
|---|---|---|---|
| Mac | **12.75** | 7 | 8 |
| N 卡 | **50** | 13 | 14 |

N 卡中位约为 Mac 的 **3.9 倍**（Mac/N 卡 = 0.26）。Mac 跑稠密 27B 普遍落在 10–20 tok/s，网友高频评价是「painfully slow」。

**Mac 举例**（Qwen3.8-27B）：
- M4 Pro / LM Studio：**12.75 tok/s** — <https://news.ycombinator.com/item?id=49307087>
- M4 Max：**20 tok/s** — <https://news.ycombinator.com/item?id=49371825>
- M5 Max：**30 tok/s**（同一人另一配置 15）— <https://news.ycombinator.com/item?id=49308246>

**4090 举例**（Qwen3.8-27B，仅 3 票，**只举例不下结论**）：
- 4090 / Q5_K_S / llama.cpp：**33 tok/s** — <https://news.ycombinator.com/item?id=49308684>
- 4090 / Q4_K_M / llama.cpp：**48 tok/s** — <https://news.ycombinator.com/item?id=49299812>
- 4090：**60 tok/s** — <https://news.ycombinator.com/item?id=49306201>

N 卡更高档位举例：RTX 5090 跑到 **180 tok/s** — <https://news.ycombinator.com/item?id=49392510>。

> 小结：稠密 27B 吃算力与显存带宽，N 卡优势明显；Mac 不是不能跑，是慢得影响交互。

---

## 结论 2：跑 MoE（35B-A3B），Mac 与 N 卡差距大幅缩小

以 **Qwen3.6-35B-A3B**（MoE，激活 3B）为例，单卡口径：

| 类别 | 中位 tok/s | 票数 | 样本 |
|---|---|---|---|
| Mac | **52.97** | 21 | 27 |
| N 卡 | **75** | 17 | 20 |
| A 卡 | **35** | 5 | 7 |
| 统一内存主机 | **50** | 7 | 8 |

Mac/N 卡 = **0.71**——差距从稠密的 0.26 收窄到 0.71（Mac 约达 N 卡七成，仍慢约三成）。机制：生成阶段稠密模型本就卡在内存带宽——每生成一个 token 都要把全部权重读一遍；MoE 每个 token 只读激活的那部分专家（这里约 3B），要读的权重量小得多，Mac 与 N 卡的带宽差距被大幅冲淡，加上统一内存装得下全部专家，所以 Mac 跑 MoE 不吃亏。这是本次数据里最关键的「分场景」证据。

**Mac 举例**（Qwen3.6-35B-A3B）：
- M2 Max / Q6_K / LM Studio：**52.97 tok/s** — <https://news.ycombinator.com/item?id=48197486>
- M4 Pro / MLX：**80.83 tok/s** — <https://news.ycombinator.com/item?id=49307087>
- M3 Max：**100 tok/s** — <https://news.ycombinator.com/item?id=49153378>

**4090 举例**（仅 1 票，**只举例不下结论**）：
- 4090 / Q4_K_XL / llama.cpp / 150k 上下文：**140 tok/s** — <https://news.ycombinator.com/item?id=47800312>

**N 卡 / A 卡举例**：
- RTX 3090 / Q4_K_XL：**135.7 tok/s** — <https://news.ycombinator.com/item?id=47843554>
- RTX 5090 / Q4_K_M：**259 tok/s** — <https://news.ycombinator.com/item?id=49101702>
- Radeon AI Pro R9700 / Q5：**100 tok/s** — <https://news.ycombinator.com/item?id=48518616>
- Radeon AI Pro R9700 / Q5_K_M：**80 tok/s** — <https://news.ycombinator.com/item?id=48364797>

> 小结：如果你主要跑 MoE 模型，Mac 的速度劣势明显缩小（约慢三成），且大内存能装下 24GB 显存塞不下的更大 MoE。A 卡单卡样本少（5 票）且分化大：高端 R9700 能到 80–100 tok/s，老卡/型号未指明低至 10–35，中位仅 35，不能一概而论（2×7900XT 的 80 tok/s 已归入多卡单列，不计进单卡中位）。

---

## 结论 3：要装超大模型，看大统一内存——但带宽是瓶颈，后悔集中

全站各类别中位（全部 eligible，未拆多卡）：Mac **30**（187 票）、N 卡 **55**（172 票）、A 卡 **31**（50 票）、统一内存主机 **30**（80 票）、纯 CPU **10**（27 票）、SBC **6.5**（15 票）。

统一内存主机（Strix Halo / DGX Spark / Framework Desktop 等）能装下大模型，但**带宽不足**导致稠密模型和 DeepSeek-V4-Flash 这类大 MoE 的 agentic 编码慢到不可用。**后悔按人算（一人多条只算一人）：统一内存主机是后悔比例最高的机器类别——57 人报过亲测、7 人后悔（12.3%）；其中 Strix Halo 尤甚，22 人实测、5 人后悔（22.7%）。**

举例（统一内存主机跑 Qwen3.6-35B-A3B，中位 50 / 7 票）：
- Strix Halo：**50 tok/s** — <https://news.ycombinator.com/item?id=47955711>
- Framework Desktop：**50 tok/s** — <https://news.ycombinator.com/item?id=48211129>
- DGX Spark：**52.5 tok/s** — <https://news.ycombinator.com/item?id=48522459>

> 小结：大统一内存买的是「装得下」，不是「跑得快」。跑 MoE 尚可，跑稠密或做 agentic 编码要慎重（见后悔一节）。

---

## 后悔的人都后悔什么（按人算：38 人后悔，52 条亲测）

速度已一人一票；后悔也按人算——一人反复抱怨只算一人，避免把一类机器顶上去（如 SwellJoe 一人就贡献 10 条后悔）。每类机器多少人报过亲测（亲测+去重）、其中多少人后悔、比例多少；后悔卡片仍全列 52 条：

| 机器类别 | 报过亲测 | 后悔人数 | 后悔比例 | 主要后悔什么 |
|---|---|---|---|---|
| 统一内存主机 | 57 | **7** | **12.3%** | Strix Halo 带宽不足（7 人中 5 人）：稠密 27B 仅 9–13.5 t/s、DeepSeek-V4-Flash 7–15 t/s，agentic 编码「每轮思考几十分钟」；超大模型装不下走 mmap（Kimi-K2-Thinking 0.1 t/s） |
| Mac | 119 | **11** | 9.2% | **11 人中 7 人嫌「跑稠密 27B 太慢」**：M4/M4 Pro/M5/M5 Pro 跑 Qwen3.6-27B 仅 9–13.5 t/s，「unusably slow」回退云端；其余 4 人为 oMLX 比 llama.cpp 慢、MTP 反而降速、16GB 内存不够、嫌模型笨等 |
| A 卡 | 45 | 4 | 8.9% | 后悔没上更大 VRAM（7900XT 没买 XTX）；qwen/gemma 支持质量差；电费算下来不如 OpenRouter |
| 其他 | 49 | 4 | 8.2% | 笔记本 KV cache 塞满掉速（MiniMax 17→2 t/s）；移动 GPU 2–3 t/s；4090+Tenstorrent 三卡仅 30 t/s 待优化 |
| N 卡 | 153 | 6 | 3.9% | 长上下文卡速（3090 跑 27B 128k 上下文突破不了 20 t/s）；编码质量比不上云；老架构双 3090 服务器仅 5 t/s；5070 频繁崩溃 |
| 纯 CPU | 28 | 1 | 3.6% | 8 核 CPU 跑 27B 仅 0.5 t/s |
| SBC | 8 | 0 | 0% | — |
| 机器未指明 | 55 | 7 | 12.7% | 泛指「7–10 t/s 不够正经工作」，建议本地至少凑到 10 t/s |
| **合计（按人去重）** | **443** | **38** | **8.6%** | 共 52 条后悔亲测（一人多条都列） |

> 同一人可在多类机器下各计一次，故各类人数相加多于合计；合计按人去重。比例 = 该类后悔人数 ÷ 该类报过亲测人数。

**代表性原帖：**
- Strix Halo 跑 DeepSeek-V4-Flash 仅 **7.32 t/s**，agentic 编码不可用 — <https://news.ycombinator.com/item?id=48165537>
- Strix Halo 跑 Qwen3.8-27B 约 **10–15 t/s**，「带宽不足」 — <https://news.ycombinator.com/item?id=49355870>
- M5 Pro 128GB 跑 Qwen3.6-27B **11 t/s**，「花一小时写几百行代码还跑不通」 — <https://news.ycombinator.com/item?id=47869692>
- M4 Pro 48GB 跑 Qwen3.6-27B Q6 仅 **9 t/s**，「统一内存机器上不太可用」 — <https://news.ycombinator.com/item?id=47870448>
- 3090 跑 27B 128k 上下文，开 MTP 也突破不了 **20 t/s** 上界 — <https://news.ycombinator.com/item?id=48185540>
- 2×7900XT 跑 35B-A3B 约 80 t/s，**后悔当初省几百块没上 XTX 换更大 VRAM** — <https://news.ycombinator.com/item?id=48555349>

> 规律：**Mac 的后悔以「稠密 27B 慢」居多（11 人中 7 人），Strix Halo 的后悔集中在「带宽不足」（22 人实测、5 人后悔），N 卡的后悔集中在「长上下文掉速 / 质量不如云」。** 跑 MoE 的 Mac 用户较少单纯因速度后悔（多为引擎/内存/MTP 问题）。

---

## 同一个人开关投机解码都报了，能快多少？

筛出**同一人·同机器·同模型·同一条评论**里既报了投机解码开启、又报了关闭速度的配对（第九步收紧：只取同一条评论内的开关对比，避免跨评论混上下文/引擎），共 **18 组：13 组更快、5 组更慢**。倍率 = 开启中位 ÷ 关闭中位（网友自述、非控制实验，仅供参考）。mirekrusin、wolttam 两组的关闭速度回原文补抽了作者自带基线（表中 *）。已剔除 florianleibert 一组：原帖是 8×MI300X 整套服务的总吞吐（90→508，约 5.6×），又混入每路 15.8 tok/s，三个口径混算出的 9.6× 站不住，且并非单流投机开关对比。下表为全部 18 组：

| 谁 | 机器 / 模型 | 方法 | 关闭 | 开启 | 倍率 |
|---|---|---|---|---|---|
| GreenGames | RTX 3090 / Qwen3.5-27B | DFlash | 38.0 | 129.5 / 134.78 / 207.6 | **3.55×** |
| nullc | RTX A6000 / Qwen3.6-27B | MTP | 19 | 55 | 2.89× |
| nullc | RTX A6000 / Qwen3.6-27B | MTP | 20 | 55 | 2.75× |
| _factor | 2×Instinct MI50 / Qwen3.6-27B | MTP | 20 | 50 | 2.5× |
| xlayn | 2×AMD GPU（型号未指明）/ Qwen3.6-27B | MTP | 20 | 46 | 2.3× |
| mirekrusin | 2×RTX 4090 / Qwen3.6-27B | MTP | 45* | 95 | 2.11× |
| Ilaurens | RTX 5000 Blackwell / Gemma-4-31B | MTP | 30 | 60 | 2.0× |
| UncleOxidant | Strix Halo / Qwen3.6-27B | MTP | 9 | 18 | 2.0× |
| alentred | RTX 3090 / Qwen3.6（尺寸未指明）| MTP | 32.5 | 65 | 2.0× |
| mhjkl | （机器/模型未指明）| MTP | 115 | 160 | 1.39× |
| SwellJoe | Strix Halo / DeepSeek-V4-Flash | MTP | 10.5 | 14.5 | 1.38× |
| LoganDark | M4 Max / Qwen3.5-9B | ngram | 120 | 150 | 1.25× |
| wolttam | DGX Spark / DeepSeek-V4-Flash | DSpark | 45* | 50 | 1.11× |
| **dofm** | M1 Max / Gemma-4-26B-A4B | MTP | **75** | **65** | **0.87×（更慢）** |
| **weirdcat** | M1 Max / Gemma-4-26B-A4B | MTP | **65** | **56** | **0.86×（更慢）** |
| **anon373839** | M3 Max / Qwen3.6-35B-A3B | MTP | **60** | **40** | **0.67×（更慢）** |
| **thc1006** | RTX 3090 / Qwen3.6-35B-A3B | ngram/draft | **135.7** | **63** | **0.46×（更慢）** |
| **spijdar** | RX 7900 XT / Qwen3.8-27B | MTP | **30** | **12** | **0.4×（更慢）** |

\* 关闭速度为回原文补抽的作者自带基线（mirekrusin「95 vs 45」、wolttam「40–50」取中点 45），仅供配对、不进速度统计。

- GreenGames 原帖（DFlash 三档 vs 自回归 38.0）— <https://news.ycombinator.com/item?id=47838789>
- mirekrusin 原帖（MTP 95 vs 关闭基线 45，OFF 补抽）— <https://news.ycombinator.com/item?id=49272781>
- nullc 原帖（MTP 把 qwen3.6-27B 从 ~20 提到 55 t/s）— <https://news.ycombinator.com/item?id=48030405>
- thc1006 原帖（开了反而从 135.7 掉到 63）— <https://news.ycombinator.com/item?id=47843554>
- anon373839 M3 Max 开 MTP 反而掉到约 40 t/s（60→40），多次尝试皆降速，后悔 — <https://news.ycombinator.com/item?id=48728670>

> 结论：**按 18 组配对的实际结果（中位按全部配对算，不只算变快的）：MTP 最常见（14 组）——全部 14 组中位 2.0×，其中 10 组更快（1.38–2.89×）、4 组更慢（0.4–0.87×）；DFlash 1 组更快（3.55×）；ngram（1.25×）、DSpark（1.11×）各 1 组偏快，ngram/草稿模型（0.46×）1 组偏慢。合计 13 快 5 慢（最低 0.4×），不是稳赚。** 是否值得开，取决于模型、方法和上下文，得自己测。

---

## 反直觉的发现（单独列）

1. **MoE 让 Mac 与 N 卡的差距大幅缩小。** 同为 27B/35B 级别，稠密 Qwen3.8-27B 的 Mac/N 卡中位比是 **0.26**（12.75 vs 50），MoE Qwen3.6-35B-A3B 却是 **0.71**（52.97 vs 75，Mac 约达 N 卡七成）。「Mac 跑 AI 慢」主要体现在稠密模型上；跑 MoE 时差距小得多。
   — <https://news.ycombinator.com/item?id=48197486>（Mac MoE 52.97）、<https://news.ycombinator.com/item?id=49307087>（Mac 稠密 12.75）

2. **投机解码不一定快，18 组里 5 组开了更慢。** thc1006 在 3090 上跑 35B-A3B，开 ngram/draft 从 135.7 掉到 63（0.46×）；spijdar 在 7900XT 上跑 3.8-27B 从 30 掉到 12（0.4×）；anon373839 在 M3 Max 上开 MTP 从 60 掉到 40（0.67×）。
   — <https://news.ycombinator.com/item?id=47843554>、<https://news.ycombinator.com/item?id=49304616>、<https://news.ycombinator.com/item?id=48728670>

3. **Strix Halo 后悔比例最高（22 人实测、5 人后悔，22.7%）。** 「统一内存大 = 快」是错觉：128GB 装得下，但带宽不足，稠密 27B 只有 9–13.5 t/s，DeepSeek-V4-Flash agentic 编码 7–15 t/s 不可用。（后悔按人算，避免一人多条把比例顶高。）
   — <https://news.ycombinator.com/item?id=48165537>、<https://news.ycombinator.com/item?id=48392746>

4. **长上下文会吃掉速度。** 同一台笔记本跑 MiniMax-M2.5：空上下文 17 t/s，到 30k 上下文掉到 5–10 t/s，KV cache 塞满被丢弃重算的瞬间偶发 **2 t/s**。空上下文跑分参考价值有限。
   — <https://news.ycombinator.com/item?id=47069953>、<https://news.ycombinator.com/item?id=48185540>

5. **速度够也可能后悔——痛点是质量/审查，不是 tok/s。** MacBook Ultra 跑各类模型 25–70 t/s 却嫌模型「dumb as a brick」；Strix Halo 跑 gpt-oss 40 t/s 却嫌被审查得「lobotomized」；3090 跑 35B-A3B 50 t/s 却嫌编码质量比不上云。
   — <https://news.ycombinator.com/item?id=48693165>、<https://news.ycombinator.com/item?id=48147937>、<https://news.ycombinator.com/item?id=48545399>

---

## 口径与局限（务必先读）

- **自述非基准**：全部来自评论自述，量化、上下文、引擎、散热、后台负载各不相同，中位数只反映趋势，不能当采购跑分。
- **4090 样本不足**：单卡 4090 每个模型不到 5 票，本文对 4090 只举例、不给中位数结论；类别中位用的是「N 卡整体」。
- **速度口径**：单流生成 tok/s；区间取中点（卡片显示原文）；投机解码开启 / 扩散模型 / 0.0 跑不动 / 批量峰值不进普通中位数；多卡多机单列。
- **投票口径**：每人·每机器·每模型一票（取该人自己的中位数），再对票取中位数；样本 < 5 的格子不下结论。
- **后悔按人算**：每类机器多少人报过亲测、其中多少人后悔、比例多少（一人多条只算一人，避免反复抱怨顶高某类）；后悔卡片仍全列 52 条。
- **投机配对口径**：同一人·同机器·同模型·**同一条评论**里 ON/OFF 都有单流生成 tok/s 才配对（第九步收紧，避免跨评论混上下文/引擎）；缺的关闭速度回原文补抽作者自带基线（mirekrusin、wolttam）。倍率中位按全部配对算（不只算变快的）。把整套服务总吞吐与每路速度混用的配对已剔除（florianleibert 9.6×）；开着 MTP 测的速度（anon373839 100/50、nullc 55）改标投机解码、退出速度统计。
- **时间窗**：2026-01 至 2026-08-22，新模型（Qwen3.8 / Qwen3.6）占多数，老模型样本偏少。
- 完整统计口径、复现步骤、数据来源与许可见 [README.md](README.md)。
