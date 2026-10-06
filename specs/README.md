# 量学解盘引擎（LiangXue Analysis Engine）

> 基于量学理论体系的结构化技术分析工具。

## 项目定位

对已实现的历史行情数据，执行量学理论框架下的**形态学识别**与**术语学转译**。

**项目边界（明确排除项）：**
- 不具备预测功能
- 不构成投资建议
- 不涉及交易执行
- 不提供目标价位测算

## 项目结构

量学解盘引擎/
├── PROJECT_MEMORY.md          （项目知识库，唯一真相源）
├── README.md                  （本文件）
├── specs/                     （规格说明书，11份）
│   ├── spec_principles.md     （公理层）
│   ├── spec_global_rules.md   （全局规则层）
│   ├── spec_batch1_basic_volume.md   （批次1：7张基础量柱卡）
│   ├── spec_batch1_addendum.md       （批次1补充v1）
│   ├── spec_batch1_addendum_v2.md    （批次1补充v2）
│   ├── spec_batch2_ace_pillar.md     （批次2：将军柱、元帅柱）
│   ├── spec_batch3_price_line.md     （批次3：8条量线绘制规则）
│   ├── spec_batch4_line_technique.md （批次4：10张量线战法卡）
│   ├── spec_batch5_wave.md           （批次5：9张量波规格卡）
│   └── spec_batch6_combination_technique.md  （批次6：12张组合战法卡）
├── docs/                      （理论著作交付物，暂未上传）
├── src/                       （代码实现，待建）
├── tests/                     （测试用例，待建）
└── .github/
    └── workflows/             （GitHub Actions，待建）

## 方法论

**规格驱动开发（Specification-Driven Development）**

规格是代码的规范依据，代码是规格的具体实现。

- 规格未定，不写代码
- 规格变更，代码同步变更
- 规格冲突，以 specs/ 目录文件为准

## 核心准则

1. **零幻觉**：禁止虚构版本号、年份、术语定义；无法核实的信息标注【未能核实】
2. **规格优先**：规格文件的权威性高于任何模型记忆
3. **客观描述**：仅陈述形态特征，不推断主体意图
4. **零未来函数**：信号判定严格遵循时间顺序，禁止使用未来数据
5. **参数时效性**：参数以适配当前市场环境为最高准则

## 规格体系概览

| 层级 | 文件 | 内容 |
|:---|:---|:---|
| 公理层 | spec_principles.md | 三先规律、三不定律、位置决定性质、左证明右确认等底层原则 |
| 全局层 | spec_global_rules.md | 位置判定规则、位置-性质映射表、输出字段规范 |
| 量柱层 | batch1 + batch2 | 高量柱/低量柱/倍量柱/平量柱/缩量柱/梯量柱/黄金柱；将军柱/元帅柱 |
| 量线层 | batch3 + batch4 | 8条量线绘制规则；10张量线战法卡 |
| 量波层 | batch5 | 9张量波规格卡 |
| 组合层 | batch6 | 12张组合战法卡 |

## 项目文档

- 完整项目知识库、交接文档、当前阶段、决策记录：见 PROJECT_MEMORY.md
- 任何模型接手本项目前，须先完整阅读 PROJECT_MEMORY.md

## 免责声明

本项目为量学理论的形式化规格工程，仅供学习研究使用，**不构成任何投资建议**。股市有风险，投资需谨慎。