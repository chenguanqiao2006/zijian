"""峰谷线（peak_valley_line）—— 顶底互换的进攻线

规格：spec_batch3_price_line.md 规格卡5
原著：《量线捉涨停》（第4版）第10讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 峰顶线与谷底线自然重合（价位差≤δ=0.01）
2. 顶底互换：股价突破原峰顶线后回踩该线不破
3. 三级飞跃：第一级（峰谷线）、第二级（精准峰谷线）、第三级（黄金顶）
4. 单向力道：只有向上支撑
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine
from .peak_line import PeakLine
from .valley_line import ValleyLine


# 重合容差（原著要求"自然重合"，工程化建议δ=0.01元）
OVERLAP_DELTA = 0.01


class PeakValleyLine(BasePriceLine):
    """峰谷线规格卡实现"""

    signal_id = "peak_valley_line"
    signal_name = "峰谷线"
    line_type = "horizontal"

    def __init__(self, peak_line_detector=None, valley_line_detector=None,
                 golden_volume_checker=None):
        """初始化峰谷线检测器。

        Args:
            peak_line_detector: 峰顶线检测器（PeakLine实例）
            valley_line_detector: 谷底线检测器（ValleyLine实例）
            golden_volume_checker: 黄金柱纯判定函数（用于三级飞跃判定）
        """
        super().__init__()
        self._peak_detector = peak_line_detector or PeakLine()
        self._valley_detector = valley_line_detector or ValleyLine()
        self._golden_volume_checker = golden_volume_checker

    def _find_all_peaks(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """找出所有有效峰顶线取点"""
        _, h, _, _, _ = self._extract_series(data)
        n = len(h)
        peaks = []
        for idx in range(5, n - 1):
            # 阶段性真顶（简化判定）
            left_start = max(0, idx - 5)
            if h[idx] != max(h[left_start:idx + 1]):
                continue
            if h[idx + 1] >= h[idx]:
                continue
            o = data.get("open", [])
            c = data.get("close", [])
            v = data.get("volume", [])
            # 高量柱简化判定
            if idx >= 9:
                window = v[max(0, idx - 9):idx + 1]
                if v[idx] == max(window) and v[idx] > 0:
                    line_price = max(o[idx], c[idx])
                    peaks.append({"idx": idx, "price": line_price, "date": data.get("dates", [])[idx] if idx < len(data.get("dates", [])) else f"idx_{idx}"})
        return peaks

    def _find_all_valleys(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """找出所有有效谷底线取点"""
        _, _, l, _, _ = self._extract_series(data)
        n = len(l)
        valleys = []
        for idx in range(5, n - 1):
            left_start = max(0, idx - 5)
            if l[idx] != min(l[left_start:idx + 1]):
                continue
            if l[idx + 1] <= l[idx]:
                continue
            o = data.get("open", [])
            c = data.get("close", [])
            v = data.get("volume", [])
            if idx >= 9:
                window = v[max(0, idx - 9):idx + 1]
                if v[idx] == min(window) and v[idx] > 0:
                    line_price = min(o[idx], c[idx])
                    valleys.append({"idx": idx, "price": line_price, "date": data.get("dates", [])[idx] if idx < len(data.get("dates", [])) else f"idx_{idx}"})
        return valleys

    def _check_break_pullback(self, data: Dict[str, Any], peak_idx: int, line_price: float) -> Tuple[bool, str]:
        """检查顶底互换：股价突破原峰顶线后回踩不破。
        返回 (is_confirmed, confirm_type)。
        """
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)
        if peak_idx + 2 >= n:
            return False, "unverified"

        broken = False
        for i in range(peak_idx + 1, n):
            if c[i] > line_price:
                broken = True
            # 回踩不破（实体收盘价 >= line_price）
            if broken and c[i] >= line_price:
                return True, "break_pullback_confirmed"
            # 回踩跌破（实体收盘价 < line_price）
            if broken and c[i] < line_price:
                return False, "异化失败"

        if broken:
            return False, "break_no_pullback"
        return False, "no_break_yet"

    def _determine_three_level(self, data: Dict[str, Any], peak_idx: int,
                                 valley_idx: int, line_price: float) -> str:
        """判定三级飞跃等级。
        第一级：峰谷线（峰顶线与谷底线重合）
        第二级：精准峰谷线（峰顶线有多个取点重合，即精准线武装）
        第三级：黄金顶（黄金柱支撑的峰谷线）
        """
        # 检查是否有黄金柱支撑（第三级）
        if self._golden_volume_checker is not None:
            try:
                # 检查峰顶线取点或谷底线取点是否为黄金柱
                if self._golden_volume_checker(data, peak_idx) or self._golden_volume_checker(data, valley_idx):
                    return "第三级（黄金顶）"
            except Exception:
                pass

        # 检查是否为精准峰谷线（第二级）—— 简化：峰顶线取点附近有多个同价位
        _, h, _, _, _ = self._extract_series(data)
        peak_count = 0
        for i in range(len(h)):
            if abs(h[i] - line_price) <= OVERLAP_DELTA:
                peak_count += 1
        if peak_count >= 2:
            return "第二级（精准峰谷线）"

        return "第一级（峰谷线）"

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """峰谷线检测主入口"""
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)

        if n < 10:
            return self._invalid_result(date, "数据不足，无法判定峰谷线")

        t_idx = n - 1

        # 第一步：找所有峰顶线和谷底线取点
        peaks = self._find_all_peaks(data)
        valleys = self._find_all_valleys(data)

        if not peaks or not valleys:
            return self._invalid_result(date, "未找到峰顶线或谷底线取点")

        # 第二步：找重合的峰顶线和谷底线
        best_pair = None
        min_diff = float('inf')
        for peak in peaks:
            for valley in valleys:
                # 谷底线取点应在峰顶线取点之后（顶底互换的时间顺序）
                if valley["idx"] <= peak["idx"]:
                    continue
                diff = abs(peak["price"] - valley["price"])
                if diff <= OVERLAP_DELTA and diff < min_diff:
                    min_diff = diff
                    best_pair = (peak, valley)

        if best_pair is None:
            return self._invalid_result(date, "峰顶线与谷底线未重合，不构成峰谷线")

        peak, valley = best_pair
        line_price = (peak["price"] + valley["price"]) / 2
        重合精度 = abs(peak["price"] - valley["price"])

        # 第三步：顶底互换确认（突破后回踩不破）
        is_confirmed, confirm_type = self._check_break_pullback(data, peak["idx"], line_price)

        # 第四步：三级飞跃等级
        three_level = self._determine_three_level(data, peak["idx"], valley["idx"], line_price)

        # 第五步：位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 第六步：性质描述
        nature = "顶底互换进攻线（整理者分析，非权威来源）"

        # 置信度
        confidence = "confirmed" if is_confirmed else "unconfirmed"

        result = {
            "signal_id": self.signal_id,
            "date": date or (data.get("dates", [])[t_idx] if t_idx < len(data.get("dates", [])) else f"idx_{t_idx}"),
            "is_valid": True,
            "line_type": self.line_type,
            "line_price": round(line_price, 4),
            "peak_anchor_date": peak["date"],
            "valley_anchor_date": valley["date"],
            "重合精度": round(重合精度, 4),
            "峰谷类型": "单峰单谷",
            "三级飞跃等级": three_level,
            "position": position,
            "nature": nature,
            "confidence": confidence,
            "confirm_type": confirm_type,
        }

        return result

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "line_type": self.line_type,
            "line_price": None,
            "peak_anchor_date": None,
            "valley_anchor_date": None,
            "重合精度": None,
            "峰谷类型": None,
            "三级飞跃等级": None,
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
