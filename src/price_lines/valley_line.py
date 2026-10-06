"""谷底线（valley_line）—— 探底与回升的生命线

规格：spec_batch3_price_line.md 规格卡2
原著：《量线捉涨停》（第4版）第7讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 取点：阶段性真底（左侧至少N=5根K线内最低），对应低量柱或黄金柱，优先取实底
2. 确认：后续至少1根K线最低价 > 取点最低价（T+1日收盘后确认）
3. 画线：水平线，line_price = 实底（优先）或虚底
4. 有效性：取点确认 + 量柱生根 + 触线验证（触线反弹或跌破后反抽不过）
5. 异化：股价有效跌破后，谷底线由支撑线转为压力线（底顶互换）
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


# 观察窗口N：阶段性真底的左侧观察K线数（原著未给量化N，工程化建议N≥5）
VALLEY_WINDOW = 5
# 确认所需后续K线数
CONFIRM_BARS = 1
# 极端缩量阈值：V[t] < V[t-1] × 0.1
EXTREME_SHRINK_RATIO = 0.1


class ValleyLine(BasePriceLine):
    """谷底线规格卡实现"""

    signal_id = "valley_line"
    signal_name = "谷底线"
    line_type = "horizontal"

    def __init__(self, low_volume_checker=None, golden_volume_checker=None):
        """初始化谷底线检测器。

        Args:
            low_volume_checker: 低量柱纯判定函数，若为None则使用内置简化判定。
            golden_volume_checker: 黄金柱纯判定函数，若为None则跳过黄金柱检查。
        """
        super().__init__()
        self._low_volume_checker = low_volume_checker
        self._golden_volume_checker = golden_volume_checker

    def _is_low_volume_simple(self, volumes: List[float], idx: int) -> bool:
        """简化版低量柱判定：V[idx] == LLV(V, 10)。
        完整判定应复用 LowVolumeSignal 的规格。
        """
        if idx < 9:
            return False
        window = volumes[max(0, idx - 9):idx + 1]
        return volumes[idx] == min(window) and volumes[idx] > 0

    def _is_anchor_volume_valid(self, data: Dict[str, Any], idx: int) -> Tuple[bool, str]:
        """检查取点K线的量柱是否为低量柱或黄金柱（量线生根）。
        返回 (is_valid, volume_type)。
        """
        volumes = data.get("volume", [])
        if idx >= len(volumes):
            return False, "none"

        # 优先使用注入的低量柱判定函数
        if self._low_volume_checker is not None:
            try:
                if self._low_volume_checker(data, idx):
                    return True, "low_volume"
            except Exception:
                pass

        # 简化版低量柱判定
        if self._is_low_volume_simple(volumes, idx):
            return True, "low_volume"

        # 黄金柱检查（若注入了判定函数）
        if self._golden_volume_checker is not None:
            try:
                if self._golden_volume_checker(data, idx):
                    return True, "golden_volume"
            except Exception:
                pass

        return False, "none"

    def _is_extreme_shrink(self, data: Dict[str, Any], idx: int) -> bool:
        """检查是否为极端缩量真底（V[idx] < V[idx-1] × 0.1）。"""
        volumes = data.get("volume", [])
        if idx < 1 or idx >= len(volumes):
            return False
        if volumes[idx - 1] <= 0:
            return False
        return volumes[idx] < volumes[idx - 1] * EXTREME_SHRINK_RATIO

    def _find_valley_anchor(self, data: Dict[str, Any], t_idx: int) -> Tuple[Optional[int], Optional[str]]:
        """寻找阶段性真底取点。
        在 t_idx 之前（含t_idx）寻找满足条件的真底。
        返回 (anchor_idx, anchor_price_type)，找不到返回 (None, None)。

        真底条件：
        1. 左侧至少VALLEY_WINDOW根K线内最低价
        2. 右侧至少CONFIRM_BARS根K线最低价 > 取点最低价（已确认）
        3. 取点K线对应量柱为低量柱或黄金柱
        """
        _, _, l, _, _ = self._extract_series(data)
        n = len(l)
        if n < VALLEY_WINDOW + CONFIRM_BARS + 1:
            return None, None

        # 从右往左找（找最近的有效真底）
        for idx in range(t_idx, VALLEY_WINDOW - 1, -1):
            if idx >= n:
                continue
            # 条件1：左侧VALLEY_WINDOW根内最低
            left_start = max(0, idx - VALLEY_WINDOW)
            if l[idx] != min(l[left_start:idx + 1]):
                continue

            # 条件2：右侧至少CONFIRM_BARS根确认（最低价 > 取点最低价）
            if idx + CONFIRM_BARS >= n:
                continue  # 后续数据不足，未确认
            right_end = min(n, idx + CONFIRM_BARS + 1)
            if min(l[idx + 1:right_end]) <= l[idx]:
                continue  # 后续创新低，取点失效

            # 条件3：量柱生根（低量柱或黄金柱）
            vol_valid, _ = self._is_anchor_volume_valid(data, idx)
            if not vol_valid:
                continue

            # 取点价位类型：优先实底
            return idx, "real_bottom"

        return None, None

    def _check_touch_verify(self, data: Dict[str, Any], anchor_idx: int, line_price: float) -> Tuple[bool, str]:
        """检查谷底线的触线验证。
        在取点之后的K线中，是否出现：
        - 触线反弹（股价接近line_price后反弹，验证支撑作用）
        - 或有效跌破后反抽不过（验证异化后的压力作用）
        返回 (is_verified, verify_type)。
        """
        _, _, l, c, _ = self._extract_series(data)
        n = len(c)
        if anchor_idx + 1 >= n:
            return False, "unverified"

        # 容差：股价接近line_price的范围（0.5%）
        tolerance = line_price * 0.005

        touched = False
        broken = False
        for i in range(anchor_idx + 1, n):
            # 触线：最低价接近或触及line_price
            if l[i] <= line_price + tolerance:
                touched = True
                # 触线后反弹（收盘价 > line_price）→ 支撑验证
                if c[i] > line_price:
                    return True, "touch_rise"
                # 有效跌破（收盘价 < line_price）→ 可能异化
                if c[i] < line_price:
                    broken = True

            # 跌破后反抽不过（收盘价 <= line_price）→ 异化压力验证
            if broken and c[i] <= line_price and l[i] <= line_price + tolerance:
                return True, "break_pressure"

        if touched:
            return False, "touch_unconfirmed"
        return False, "unverified"

    def _check_异化状态(self, data: Dict[str, Any], anchor_idx: int, line_price: float) -> str:
        """检查谷底线的异化状态。
        - 未异化：股价仍在line_price上方
        - 已异化（底顶互换）：股价有效跌破后反抽不过
        - 异化失败：跌破后反抽突破
        """
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)
        if anchor_idx + 1 >= n:
            return "未异化"

        broken = False
        for i in range(anchor_idx + 1, n):
            if c[i] < line_price:
                broken = True
            if broken and c[i] > line_price:
                return "异化失败"
        if broken:
            return "已异化（底顶互换）"
        return "未异化"

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """谷底线检测主入口。"""
        _, _, l, c, v = self._extract_series(data)
        n = len(c)

        # 基础校验
        if n < VALLEY_WINDOW + CONFIRM_BARS + 1:
            return self._invalid_result(date, "数据不足，无法判定谷底线")

        # T日索引
        t_idx = n - 1

        # 第一步：找阶段性真底取点
        anchor_idx, anchor_price_type = self._find_valley_anchor(data, t_idx)
        if anchor_idx is None:
            return self._invalid_result(date, "未找到符合条件的阶段性真底")

        # 第二步：计算线价
        o = data.get("open", [])
        if anchor_price_type == "real_bottom":
            line_price = self._real_bottom(o[anchor_idx], c[anchor_idx])
        else:
            line_price = l[anchor_idx]

        # 第三步：极端缩量标记
        extreme_shrink = self._is_extreme_shrink(data, anchor_idx)

        # 第四步：触线验证
        is_verified, verify_type = self._check_touch_verify(data, anchor_idx, line_price)

        # 第五步：异化状态
        异化状态 = self._check_异化状态(data, anchor_idx, line_price)

        # 第六步：位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 第七步：性质描述
        nature = self._get_nature(position)

        # 置信度
        if is_verified:
            confidence = "confirmed"
        else:
            confidence = "unconfirmed"

        # 取点日期
        dates = data.get("dates", [])
        anchor_date = dates[anchor_idx] if anchor_idx < len(dates) else f"idx_{anchor_idx}"

        result = {
            "signal_id": self.signal_id,
            "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
            "is_valid": True,
            "line_type": self.line_type,
            "line_price": round(line_price, 4),
            "anchor_date": anchor_date,
            "anchor_price_type": anchor_price_type,
            "position": position,
            "nature": nature,
            "confidence": confidence,
            "verify_type": verify_type,
            "异化状态": 异化状态,
        }

        # 极端缩量标记
        if extreme_shrink:
            result["note"] = "极端缩量真底，需人工复核"

        return result

    def _get_nature(self, position: str) -> str:
        """谷底线的性质映射（整理者分析，非权威来源）"""
        if position == "unknown":
            return "无法判定性质"
        if position == "low":
            return "底部支撑生命线（整理者分析，非权威来源）"
        if position == "mid":
            return "阶段性支撑线（整理者分析，非权威来源）"
        return "高位支撑线（整理者分析，非权威来源）"

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        """返回无效结果"""
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "line_type": self.line_type,
            "line_price": None,
            "anchor_date": None,
            "anchor_price_type": None,
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
