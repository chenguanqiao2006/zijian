# ONBOARD.md · 跨模型接入手册

> 本文件是「量学解盘引擎」项目的**外置大脑**之一，定义任何模型接入本项目的话术与导航。
> 若你是项目负责人，请把本文档的话术复制给你要接入的模型。
> 若你是刚接入本项目的模型，请先读 SOUL.md → MEMORY.md → GLOBAL.md，再读本文件，然后开始任务。

---

## 一、项目接入主话术（用于能联网的模型）

**使用场景**：开新对话时，把下面话术直接发给模型。

**主话术正文**：

> 先读 GitHub 仓库 chenguanqiao2006/zijian 根目录下的三份文件：
> 1. SOUL.md
> 2. MEMORY.md
> 3. GLOBAL.md
>
> 读完输出理解确认，再等我下达任务。
>
> 三份文件链接：
> https://github.com/chenguanqiao2006/zijian/blob/main/SOUL.md
> https://github.com/chenguanqiao2006/zijian/blob/main/MEMORY.md
> https://github.com/chenguanqiao2006/zijian/blob/main/GLOBAL.md
>
> 若你能访问该仓库，可直接读取；若不能访问，请明确告知我，我将把三份文件内容粘贴给你。

---

## 二、项目接入备用话术（用于不能联网的模型）

**使用场景**：模型无法联网访问 GitHub 时，先发话术，再依次粘贴三份文件内容。

**备用话术正文**：

> 你是「量学解盘引擎」项目的新接入模型。请先读完以下三份文件（我随后粘贴），
> 再输出理解确认，然后等我下达任务：
>
> 1. SOUL.md（身份与行为准则）
> 2. MEMORY.md（项目长期记忆）
> 3. GLOBAL.md（工作流程规范）
>
> 读完后再询问我是否需要进一步阅读 PROJECT_MEMORY.md（完整档案）和 specs/ 目录（规格文件）。

---

## 三、角色声明（多模型并行时可选附加）

**使用场景**：多个模型同时协作时，明确各自角色，避免职责重叠。

**角色声明正文**：

> 【本对话的角色声明】
> 你在本项目中的角色是：[规格架构师 / 规格生成员 / 校验者]
> 三选一，由你根据自身能力判断：
> - 能联网搜索 + 能写文件 → 规格生成员
> - 能审核逻辑 + 能做一致性审计 → 规格架构师
> - 仅能读取文件 + 能核查内容 → 校验者

---

## 四、项目当前状态（截至 2026-10-06）

| 项 | 状态 |
|:---|:---|
| 规格体系 | 13 份规格文件已定稿 |
| 规格文件层级 | principles → data_contract → global_rules → 批次1-7 |
| 批次1 代码（7张基础量柱卡） | ✅ 完成 |
| 批次2 代码（2张王牌柱） | ✅ 完成 |
| 累计测试 | 94 passed / 0 failed |
| GitHub Actions | ✅ 首次跑通（Python 3.10 + 3.11） |
| 下一批次 | 批次3（量线绘制规则，8条） |
| 当前阶段 | 代码实现进行中——批次3 待启动 |

---

## 五、项目完整导航

### 5.1 GitHub 仓库根目录

| 文件 | 定位 |
|:---|:---|
| SOUL.md | 身份与行为准则（外置大脑1） |
| MEMORY.md | 项目长期记忆（外置大脑2） |
| GLOBAL.md | 工作流程规范（外置大脑3） |
| ONBOARD.md | 本文档，跨模型接入手册（外置大脑4） |
| PROJECT_MEMORY.md | 完整档案（真相源） |
| README.md | 项目简介 |
| requirements.txt | Python 依赖 |

### 5.2 specs/ 目录（13 份规格文件）

| 文件 | 定位 |
|:---|:---|
| spec_principles.md | 公理层（最高优先） |
| spec_data_contract.md | 数据契约层 |
| spec_global_rules.md | 全局规则层 |
| spec_batch1_basic_volume.md | 批次1：7张基础量柱卡 |
| spec_batch1_addendum.md | 批次1补充v1 |
| spec_batch1_addendum_v2.md | 批次1补充v2 |
| spec_batch2_ace_pillar.md | 批次2：将军柱、元帅柱 |
| spec_batch3_price_line.md | 批次3：8条量线绘制规则 |
| spec_batch4_line_technique.md | 批次4：10张量线战法卡 |
| spec_batch5_wave.md | 批次5：9张量波规格卡 |
| spec_batch6_combination_technique.md | 批次6：12张组合战法卡 |
| spec_batch7_twelve_words.md | 批次7：3张十二字令卡 |
| README.md | specs 目录说明 |

### 5.3 src/ 目录（代码实现）

| 路径 | 内容 |
|:---|:---|
| src/__init__.py | 包初始化 |
| src/signals/ | 信号卡实现（base.py + 9张信号） |
| src/global_rules/ | 全局规则（price_position.py） |
| src/utils/ | 工具（data_loader.py） |

### 5.4 tests/ 目录（测试用例）

| 路径 | 内容 |
|:---|:---|
| tests/test_*.py | 各信号卡与位置判定的测试（共 94 个测试） |

### 5.5 .github/workflows/

| 路径 | 内容 |
|:---|:---|
| test.yml | GitHub Actions 配置（Python 3.10 + 3.11 双版本跑 pytest） |

---

## 六、阅读顺序建议

**任何新接入模型，请按以下顺序阅读：**

1. **SOUL.md** — 先知道"我是谁、红线是什么"
2. **MEMORY.md** — 再知道"项目在哪、下一步做什么"
3. **GLOBAL.md** — 再知道"我该怎么工作"
4. **ONBOARD.md**（本文件）— 最后知道"我该怎么接入、怎么导航"
5. **PROJECT_MEMORY.md** — 需要完整背景时读
6. **specs/ 目录** — 需要具体规格时读

---

## 七、给不同模型的特别提示

### 7.1 给可联网模型（如豆包）

- 你可执行 git push（需 GitHub token，含 repo + workflow 两个 scope）
- 你每次完成任务后须落盘飞书云盘 + 回报
- 你联网核实时须多源交叉验证，标注来源

### 7.2 给不可联网模型（如 DeepSeek）

- 你不得提供任何需联网核实的原始信息（ISBN、原文、页码等）
- 你的职责限于：已发来文件的逻辑审核、跨文件一致性检查、结构审核、矛盾发现
- 你可在 GitHub 上读文件（若可联网），但不得凭空生成原始数据

### 7.3 给所有模型

- **真相源永远是 specs/ 目录下的文件，不是任何模型的记忆**
- 若你的输出与规格文件冲突，以规格文件为准
- 若你发现规格文件本身有矛盾或歧义，回报，不擅自判断

---

## 八、项目负责人维护说明

- 本文件由项目负责人维护
- 项目状态变化时，请同步更新第四章"项目当前状态"
- 三件套（SOUL / MEMORY / GLOBAL）不轻易变更；本文件（ONBOARD）随项目进度小幅更新

---

*本文件由项目负责人维护，位于 GitHub 仓库根目录。*
