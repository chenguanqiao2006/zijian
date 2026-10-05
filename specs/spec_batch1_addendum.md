# 量学信号规格说明书 · 批次1补充说明

> 文档编号：spec_batch1_addendum
> 文档版本：1.0
> 生成日期：2026-10-05
> 适用对象：spec_batch1_basic_volume.md（批次1：7张基础量柱卡）
> 补充依据：spec_global_rules.md（全局规则文件）

---

## 一、补充事由

批次1的7张基础量柱卡（高量柱、低量柱、倍量柱、平量柱、缩量柱、梯量柱、黄金柱）定稿于全局规则文件建立之前。

全局规则文件（spec_global_rules.md）第三部分明确规定：
> 所有量柱信号的输出JSON，必须包含 position 和 nature 两个字段。

因此，批次1的7张卡在输出JSON时，必须按本补充说明追加 position 和 nature 字段。

---

## 二、补充规则

1. 批次1的7张卡，输出JSON时必须在原有字段基础上追加：
   - position：位置判定结果（low / mid / high / unknown）
   - nature：基于位置和信号类型，从全局规则文件的位置-性质映射表查得的性质描述

2. position 和 nature 字段的取值规则，以 spec_global_rules.md 为准。

3. 批次1原文件的所有内容（定义、公式、判定条件、边界情况、测试用例）保持不变，无需重写。

---

## 三、7张卡的输出示例（仅展示追加字段）

### 高量柱

    {
      "signal_id": "high_volume",
      "date": "2026-10-05",
      "is_signal": true,
      "position": "low",
      "nature": "主力吸筹/建仓信号（启动柱，需后三日验证）",
      "values": { ... }
    }

### 低量柱

    {
      "signal_id": "low_volume",
      "date": "2026-10-05",
      "is_signal": true,
      "position": "low",
      "nature": "见底/拐点信号",
      "values": { ... }
    }

### 倍量柱

    {
      "signal_id": "double_volume",
      "date": "2026-10-05",
      "is_signal": true,
      "position": "low",
      "nature": "主力建仓/启动信号",
      "values": { ... }
    }

### 平量柱

    {
      "signal_id": "flat_volume",
      "date": "2026-10-05",
      "is_signal": true,
      "position": "low",
      "nature": "蓄势/待涨信号",
      "values": { ... }
    }

### 缩量柱

    {
      "signal_id": "shrink_volume",
      "date": "2026-10-05",
      "is_signal": true,
      "position": "low",
      "nature": "抛压衰竭/见底信号",
      "values": { ... }
    }

### 梯量柱

    {
      "signal_id": "ladder_volume",
      "date": "2026-10-05",
      "is_signal": true,
      "position": "low",
      "nature": "温和吸筹/启动信号",
      "values": { ... }
    }

### 黄金柱

    {
      "signal_id": "golden_volume",
      "base_pillar_date": "2026-09-30",
      "confirmation_date": "2026-10-09",
      "is_signal": true,
      "position": "low",
      "nature": "托底黄金柱——保护性、自救性，应在次日确认后再介入",
      "strength": "strong",
      "base_pillar_type": "double_volume",
      "values": { ... }
    }

---

## 四、测试用例补充要求

批次1原文件的测试用例无需重写。但在实际实现时，测试用例必须扩展验证 position 和 nature 字段：

1. 原测试用例的验证项全部保留
2. 追加验证 position 字段是否与输入数据的位置判定结果一致
3. 追加验证 nature 字段是否与全局规则文件的映射表一致

---

## 五、与其他文件的关系

1. 本补充说明是 spec_batch1_basic_volume.md 的正式补充，与批次1原文件具有同等效力。
2. 本补充说明与全局规则文件冲突时，以全局规则文件为准。
3. 批次1原文件与本补充说明合并阅读时，视为完整的批次1规格。

---

## 免责声明

本补充说明为量学理论的形式化规格文档，仅供学习研究使用，不构成任何投资建议。所有字段定义来自 spec_global_rules.md，性质映射表的原著依据以该文件为准。