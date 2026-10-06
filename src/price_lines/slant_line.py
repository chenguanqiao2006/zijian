"""斜衡线（slant_line）—— 量价与时空的坐标线

规格：spec_batch3_price_line.md 规格卡4
原著：《量线捉涨停》（第4版）第9讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 取点：两个同方向拐点（上升斜衡线=两个真底低点抬高，下降斜衡线=两个真顶高点降低）
2. 画线：斜线（斜率k + 截距b）
3. 确认日：两个取点均确认后（第二个取点日收盘后）
4. 有效性：触线反弹/回落验证
5. 边界：短间隔标注可靠性低、斜率为0退化为平衡线
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


# 两个取点最小间隔（原著未给量化间隔，工程化建议≥3根K线）
MIN_INTERVAL = 3
# 斜率容差（|k| < ε 退化为平衡线）
SLOPE_EPSILON = 0.001
# 真顶/真底观察窗口
TREND_WINDOW = 5


class SlantLine(BasePriceLine):
    """斜衡线规格卡实现"""

    signal_id = "slant_line"
    signal_name = "斜衡线"
    line_type = "slant"

    def __init__(self, high_volume_checker=None, low_volume_checker=None,
                 golden_volume_checker=None):
        """初始化斜衡线检测器。

        Args:
            high_volume_checker: 高量柱纯判定函数（真顶取点用）
            low_volume_checker: 低量柱纯判定函数（真底取点用）
            golden_volume_checker: 黄金柱纯判定函数
        """
        super().__init__()
        self._high_volume_checker = high_volume_checker
        self._low_volume_checker = low_volume_checker
        self._golden_volume_checker = golden_volume_checker

    def _is_high_volume_simple(self, volumes: List[float], idx: int) -> bool:
        """简化版高量柱判定"""
        if idx < 9:
            return False
        window = volumes[max(0, idx - 9):idx + 1]
        return volumes[idx] == max(window) and volumes[idx] > 0

    def _is_low_volume_simple(self, volumes: List[float], idx: int) -> bool:
        """简化版低量柱判定"""
        if idx < 9:
            return False
        window = volumes[max(0, idx - 9):idx + 1]
        return volumes[idx] == min(window) and volumes[idx] > 0

    def _is_peak_valid(self, data: Dict[str, Any], idx: int) -> bool:
        """判断是否为有效真顶（阶段性高点+量柱生根+已确认）"""
        _, h, _, _, v = self._extract_series(data)
        n = len(h)
        if idx < TREND_WINDOW or idx + 1 >= n:
            return False
        # 左侧TREND_WINDOW根内最高
        left_start = max(0, idx - TREND_WINDOW)
        if h[idx] != max(h[left_start:idx + 1]):
            return False
        # 右侧至少1根确认（最高价 < 取点最高价）
        if h[idx + 1] >= h[idx]:
            return False
        # 量柱生根（高量柱或黄金柱）
        if self._high_volume_checker is not None:
            try:
                if self._high_volume_checker(data, idx):
                    return True
            except Exception:
                pass
        if self._is_high_volume_simple(v, idx):
            return True
        if self._golden_volume_checker is not None:
            try:
                if self._golden_volume_checker(data, idx):
                    return True
            except Exception:
                pass
        return False

    def _is_valley_valid(self, data: Dict[str, Any], idx: int) -> bool:
        """判断是否为有效真底（阶段性低点+量柱生根+已确认）"""
        _, _, l, _, v = self._extract_series(data)
        n = len(l)
        if idx < TREND_WINDOW or idx + 1 >= n:
            return False
        # 左侧TREND_WINDOW根内最低
        left_start = max(0, idx - TREND_WINDOW)
        if l[idx] != min(l[left_start:idx + 1]):
            return False
        # 右侧至少1根确认（最低价 > 取点最低价）
        if l[idx + 1] <= l[idx]:
            return False
        # 量柱生根（低量柱或黄金柱）
        if self._low_volume_checker is not None:
            try:
                if self._low_volume_checker(data, idx):
                    return True
            except Exception:
                pass
        if self._is_low_volume_simple(v, idx):
            return True
        if self._golden_volume_checker is not None:
            try:
                if self._golden_volume_checker(data, idx):
                    return True
            except Exception:
                pass
        return False

    def _find_two_anchors(self, data: Dict[str, Any], t_idx: int) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """寻找两个取点（同方向拐点）。
        返回 (anchor1_idx, anchor2_idx, trend_direction)。
        优先找上升斜衡线（两个真底，低点抬高），其次找下降斜衡线（两个真顶，高点降低）。
        """
        o, h, l, c, _ = self._extract_series(data)
        n = len(c)

        # 收集所有有效真底
        valleys = []
        for idx in range(TREND_WINDOW, min(t_idx + 1, n - 1)):
            if self._is_valley_valid(data, idx):
                valleys.append(idx)

        # 收集所有有效真顶
        peaks = []
        for idx in range(TREND_WINDOW, min(t_idx + 1, n - 1)):
            if self._is_peak_valid(data, idx):
                peaks.append(idx)

        # 找上升斜衡线：两个真底，低点抬高，间隔≥MIN_INTERVAL
        for i in range(len(valleys) - 1, 0, -1):
            for j in range(i - 1, -1, -1):
                if valleys[i] - valleys[j] >= MIN_INTERVAL:
                    # 低点抬高
                    valley1_price = self._real_bottom(o[valleys[j]], c[valleys[j]])
                    valley2_price = self._real_bottom(o[valleys[i]], c[valleys[i]])
                    if valley2_price > valley1_price:
                        return valleys[j], valleys[i], "up"

        # 找下降斜衡线：两个真顶，高点降低，间隔≥MIN_INTERVAL
        for i in range(len(peaks) - 1, 0, -1):
            for j in range(i - 1, -1, -1):
                if peaks[i] - peaks[j] >= MIN_INTERVAL:
                    # 高点降低
                    peak1_price = self._real_top(o[peaks[j]], c[peaks[j]])
                    peak2_price = self._real_top(o[peaks[i]], c[peaks[i]])
                    if peak2_price < peak1_price:
                        return peaks[j], peaks[i], "down"

        return None, None, None

    def _compute_slope_intercept(self, data: Dict[str, Any],
                                   idx1: int, idx2: int,
                                   trend_direction: str) -> Tuple[float, float, float, float]:
        """计算斜线的斜率和截距。
        以第一个取点为基准（x=0），返回 (slope, intercept, price1, price2)。
        slope = (price2 - price1) / (idx2 - idx1)
        intercept = price1
        """
        o, _, _, c, _ = self._extract_series(data)
        if trend_direction == "up":
            price1 = self._real_bottom(o[idx1], c[idx1])
            price2 = self._real_bottom(o[idx2], c[idx2])
        else:
            price1 = self._real_top(o[idx1], c[idx1])
            price2 = self._real_top(o[idx2], c[idx2])

        interval = idx2 - idx1
        if interval <= 0:
            return 0.0, price1, price1, price2
        slope = (price2 - price1) / interval
        intercept = price1  # 以idx1为x=0
        return round(slope, 6), round(intercept, 4), price1, price2

    def _check_touch_verify(self, data: Dict[str, Any],
                              idx1: int, slope: float, intercept: float,
                              trend_direction: str) -> Tuple[bool, str]:
        """检查斜衡线的触线验证。
        对于上升斜衡线：触线反弹（股价回踩线后反弹）
        对于下降斜衡线：触线回落（股价反抽线后回落）
        """
        _, h, l, c, _ = self._extract_series(data)
        n = len(c)
        if idx1 + 2 >= n:
            return False, "unverified"

        tolerance = intercept * 0.005 if intercept > 0 else 0.05
        touched = False

        for i in range(idx1 + 1, n):
            # 计算当日线价（以idx1为基准）
            line_price = intercept + slope * (i - idx1)
            # 触线：价格区间覆盖线价
            if l[i] <= line_price + tolerance and h[i] >= line_price - tolerance:
                touched = True
                if trend_direction == "up" and c[i] > line_price:
                    return True, "touch_rise"
                if trend_direction == "down" and c[i] < line_price:
                    return True, "touch_fall"

        if touched:
            return False, "touch_unconfirmed"
        return False, "unverified"

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """斜衡线检测主入口"""
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)

        if n < TREND_WINDOW + MIN_INTERVAL + 2:
            return self._invalid_result(date, "数据不足，无法判定斜衡线")

        t_idx = n - 1

        # 第一步：找两个取点
        idx1, idx2, trend_direction = self._find_two_anchors(data, t_idx)
        if idx1 is None or idx2 is None:
            return self._invalid_result(date, "未找到两个同方向有效拐点")

        # 第二步：计算斜率和截距
        slope, intercept, price1, price2 = self._compute_slope_intercept(
            data, idx1, idx2, trend_direction)

        # 第三步：斜率为0检查（退化为平衡线）
        if abs(slope) < SLOPE_EPSILON:
            return self._invalid_result(date, "斜率为0，应改用平衡线规格卡")

        # 第四步：短间隔标记
        short_interval = (idx2 - idx1) < MIN_INTERVAL * 2

        # 第五步：触线验证
        is_verified, verify_type = self._check_touch_verify(
            data, idx1, slope, intercept, trend_direction)

        # 第六步：位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 第七步：性质描述
        nature = self._get_nature(position, trend_direction)

        # 置信度
        confidence = "confirmed" if is_verified else "unconfirmed"

        # 日期
        dates = data.get("dates", [])
        anchor1_date = dates[idx1] if idx1 < len(dates) else f"idx_{idx1}"
        anchor2_date = dates[idx2] if idx2 < len(dates) else f"idx_{idx2}"

        result = {
            "signal_id": self.signal_id,
            "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
            "is_valid": True,
            "line_type": self.line_type,
            "slope": slope,
            "intercept": intercept,
            "anchor1_date": anchor1_date,
            "anchor1_price": round(price1, 4),
            "anchor2_date": anchor2_date,
            "anchor2_price": round(price2, 4),
            "trend_direction": trend_direction,
            "position": position,
            "nature": nature,
            "confidence": confidence,
            "verify_type": verify_type,
        }

        if short_interval:
            result["note"] = "短间隔斜衡线，可靠性低"

        return result

    def _get_nature(self, position: str, trend_direction: str) -> str:
        """斜衡线的性质映射"""
        if position == "unknown":
            return "无法判定性质"
        if trend_direction == "up":
            return "上升趋势支撑线（整理者分析，非权威来源）"
        return "下降趋势压力线（整理者分析，非权威来源）"

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "line_type": self.line_type,
            "slope": None,
            "intercept": None,
            "anchor1_date": None,
            "anchor1_price": None,
            "anchor2_date": None,
            "anchor2_price": None,
            "trend_direction": None,
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
