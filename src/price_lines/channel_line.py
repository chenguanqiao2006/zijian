"""通道线（channel_line）—— 趋向与趋幅的回归线

规格：spec_batch3_price_line.md 规格卡8
原著：《量线捉涨停》（第4版）第13讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 上升通道：下轨=两个真底连线，上轨=平行线
2. 下降通道：上轨=两个真顶连线，下轨=平行线
3. 三维画法：地线（下轨）、天线（上轨）、人线（中轨）
4. 通道宽度、平行容差
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


# 平行容差
PARALLEL_EPSILON = 0.001
# 通道宽度阈值（过窄<1%，过宽>50%）
WIDTH_NARROW_RATIO = 0.01
WIDTH_WIDE_RATIO = 0.50


class ChannelLine(BasePriceLine):
    """通道线规格卡实现"""

    signal_id = "channel_line"
    signal_name = "通道线"

    def _find_two_valleys(self, data: Dict[str, Any]) -> Optional[Tuple[int, int]]:
        """找两个真底（用于上升通道下轨）。
        返回 (idx1, idx2)，idx1 < idx2
        """
        _, _, l, _, v = self._extract_series(data)
        n = len(l)
        valleys = []

        for idx in range(5, n - 1):
            # 阶段性真底
            left_start = max(0, idx - 5)
            if l[idx] != min(l[left_start:idx + 1]):
                continue
            if l[idx + 1] <= l[idx]:
                continue
            # 量柱生根（低量柱简化）
            if idx >= 9:
                window = v[max(0, idx - 9):idx + 1]
                if v[idx] == min(window) and v[idx] > 0:
                    valleys.append(idx)

        if len(valleys) >= 2:
            # 取最近的两个真底
            return valleys[-2], valleys[-1]
        return None

    def _find_two_peaks(self, data: Dict[str, Any]) -> Optional[Tuple[int, int]]:
        """找两个真顶（用于下降通道上轨）。
        返回 (idx1, idx2)，idx1 < idx2
        """
        _, h, _, _, v = self._extract_series(data)
        n = len(h)
        peaks = []

        for idx in range(5, n - 1):
            left_start = max(0, idx - 5)
            if h[idx] != max(h[left_start:idx + 1]):
                continue
            if h[idx + 1] >= h[idx]:
                continue
            if idx >= 9:
                window = v[max(0, idx - 9):idx + 1]
                if v[idx] == max(window) and v[idx] > 0:
                    peaks.append(idx)

        if len(peaks) >= 2:
            return peaks[-2], peaks[-1]
        return None

    def _compute_line(self, data: Dict[str, Any], idx1: int, idx2: int,
                       price_type: str) -> Tuple[float, float, float, float]:
        """计算两点连线的斜率和截距。
        返回 (slope, intercept, price1, price2)
        """
        o, h, l, c, _ = self._extract_series(data)
        if price_type == "low":
            p1, p2 = l[idx1], l[idx2]
        elif price_type == "high":
            p1, p2 = h[idx1], h[idx2]
        elif price_type == "close":
            p1, p2 = c[idx1], c[idx2]
        else:
            p1, p2 = o[idx1], o[idx2]

        interval = idx2 - idx1
        if interval <= 0:
            return 0.0, p1, p1, p2
        slope = (p2 - p1) / interval
        intercept = p1  # 以idx1为x=0
        return round(slope, 6), round(intercept, 4), p1, p2

    def _compute_channel_width(self, data: Dict[str, Any], lower_slope: float,
                                 lower_intercept: float, lower_idx1: int) -> float:
        """计算通道宽度：近期最高价与对应下轨价的最大差值。"""
        _, h, _, _, _ = self._extract_series(data)
        n = len(h)
        max_diff = 0.0

        for i in range(lower_idx1, n):
            lower_price = lower_intercept + lower_slope * (i - lower_idx1)
            diff = h[i] - lower_price
            if diff > max_diff:
                max_diff = diff

        return round(max_diff, 4)

    def _check_parallel(self, slope1: float, slope2: float) -> bool:
        """检查两条线是否平行（斜率差在容差内）"""
        return abs(slope1 - slope2) < PARALLEL_EPSILON

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """通道线检测主入口"""
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)

        if n < 12:
            return self._invalid_result(date, "数据不足，无法判定通道线")

        t_idx = n - 1
        dates = data.get("dates", [])

        # 优先找上升通道（两个真底确定下轨）
        valleys = self._find_two_valleys(data)
        if valleys is not None:
            v1, v2 = valleys
            lower_slope, lower_intercept, p1, p2 = self._compute_line(data, v1, v2, "low")

            # 计算通道宽度
            channel_width = self._compute_channel_width(data, lower_slope, lower_intercept, v1)

            # 上轨（与下轨平行）
            upper_intercept = round(lower_intercept + channel_width, 4)
            # 中轨
            mid_intercept = round((lower_intercept + upper_intercept) / 2, 4)

            # 通道宽度检查
            width_ratio = channel_width / p1 if p1 > 0 else 0
            note = None
            if width_ratio < WIDTH_NARROW_RATIO:
                note = "窄通道，可能为噪音，可靠性低"
            elif width_ratio > WIDTH_WIDE_RATIO:
                note = "宽通道，可能不是同一趋势"

            # 位置判定
            position_result = self._compute_position(data, date)
            position = position_result.get("position", "unknown")

            result = {
                "signal_id": self.signal_id,
                "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
                "is_valid": True,
                "channel_type": "upward",
                "slope": lower_slope,
                "lower_intercept": lower_intercept,
                "upper_intercept": upper_intercept,
                "mid_intercept": mid_intercept,
                "channel_width": channel_width,
                "lower_anchors": [
                    dates[v1] if v1 < len(dates) else f"idx_{v1}",
                    dates[v2] if v2 < len(dates) else f"idx_{v2}",
                ],
                "upper_anchors": [],  # 上轨为平行线，无独立取点
                "position": position,
                "nature": "上升通道（整理者分析，非权威来源）",
                "confidence": "confirmed",
            }
            if note:
                result["note"] = note
            return result

        # 其次找下降通道（两个真顶确定上轨）
        peaks = self._find_two_peaks(data)
        if peaks is not None:
            p1_idx, p2_idx = peaks
            upper_slope, upper_intercept, hp1, hp2 = self._compute_line(data, p1_idx, p2_idx, "high")

            # 计算通道宽度（近期最低价与对应上轨价的最大差值）
            _, _, l, _, _ = self._extract_series(data)
            max_diff = 0.0
            for i in range(p1_idx, n):
                upper_price = upper_intercept + upper_slope * (i - p1_idx)
                diff = upper_price - l[i]
                if diff > max_diff:
                    max_diff = diff
            channel_width = round(max_diff, 4)

            # 下轨（与上轨平行）
            lower_intercept = round(upper_intercept - channel_width, 4)
            mid_intercept = round((lower_intercept + upper_intercept) / 2, 4)

            # 位置判定
            position_result = self._compute_position(data, date)
            position = position_result.get("position", "unknown")

            result = {
                "signal_id": self.signal_id,
                "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
                "is_valid": True,
                "channel_type": "downward",
                "slope": upper_slope,
                "lower_intercept": lower_intercept,
                "upper_intercept": upper_intercept,
                "mid_intercept": mid_intercept,
                "channel_width": channel_width,
                "lower_anchors": [],
                "upper_anchors": [
                    dates[p1_idx] if p1_idx < len(dates) else f"idx_{p1_idx}",
                    dates[p2_idx] if p2_idx < len(dates) else f"idx_{p2_idx}",
                ],
                "position": position,
                "nature": "下降通道（整理者分析，非权威来源）",
                "confidence": "confirmed",
            }
            return result

        return self._invalid_result(date, "未找到足够的真底或真顶取点，无法构成通道线")

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "channel_type": None,
            "slope": None,
            "lower_intercept": None,
            "upper_intercept": None,
            "mid_intercept": None,
            "channel_width": None,
            "lower_anchors": [],
            "upper_anchors": [],
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
