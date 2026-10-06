"""灯塔线（lighthouse_line）—— 趋势与趋幅的导航线

规格：spec_batch3_price_line.md 规格卡7
原著：《量线捉涨停》（第4版）第12讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 中心：黄金柱的实顶（max(O,C)），黄金柱须已确认（后三日验证）
2. 平衡线：以黄金柱实顶为价位的水平线
3. 斜衡线：以黄金柱实顶为端点，与左侧关键穴位连线
4. 灯塔线是一组线（多条射线），不是单一线
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


class LighthouseLine(BasePriceLine):
    """灯塔线规格卡实现"""

    signal_id = "lighthouse_line"
    signal_name = "灯塔线"

    def __init__(self, golden_volume_checker=None):
        """初始化灯塔线检测器。

        Args:
            golden_volume_checker: 黄金柱纯判定函数 is_golden_volume(data, idx) -> bool
        """
        super().__init__()
        self._golden_volume_checker = golden_volume_checker

    def _is_golden_pillar_simple(self, data: Dict[str, Any], idx: int) -> Tuple[bool, str]:
        """简化版黄金柱判定：
        1. 基柱为倍量柱或高量柱
        2. 后三日收盘价均值 >= 基柱实顶（不破实顶）
        3. 后三日量均 <= 基柱量（量不过顶）
        返回 (is_golden, reason)
        """
        o, _, _, c, v = self._extract_series(data)
        n = len(c)
        if idx + 3 >= n:
            return False, "后三日数据不足"

        # 基柱为倍量柱或高量柱（简化）
        base_is_candidate = False
        if idx >= 1 and v[idx - 1] > 0 and v[idx] / v[idx - 1] >= 1.9:
            base_is_candidate = True
        if idx >= 9:
            window = v[max(0, idx - 9):idx + 1]
            # 高量柱要求：严格大于窗口内其他值（去重后唯一最大值），避免平量误判
            unique_vals = sorted(set(window), reverse=True)
            if len(unique_vals) >= 2 and v[idx] == unique_vals[0] and unique_vals[0] > unique_vals[1] and v[idx] > 0:
                base_is_candidate = True

        if not base_is_candidate:
            return False, "基柱非倍量柱或高量柱"

        # 后三日收盘价均值 >= 基柱实顶（不破实顶）
        real_top = max(o[idx], c[idx])
        next3_close = c[idx + 1:idx + 4]
        avg_close = sum(next3_close) / 3
        if avg_close < real_top:
            return False, "后三日收盘价均值低于基柱实顶（跌破实顶）"

        # 后三日量均 <= 基柱量（量不过顶）
        next3_vol = v[idx + 1:idx + 4]
        avg_vol = sum(next3_vol) / 3
        if avg_vol > v[idx]:
            return False, "后三日量均超过基柱量（量过顶）"

        return True, "黄金柱确认"

    def _find_golden_pillar(self, data: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
        """找最近的已确认黄金柱。
        返回 (idx, reason)
        """
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)

        # 从右往左找（找最近的黄金柱）
        for idx in range(n - 4, 9, -1):
            if idx < 0:
                continue
            # 优先使用注入的黄金柱判定函数
            if self._golden_volume_checker is not None:
                try:
                    if self._golden_volume_checker(data, idx):
                        return idx, "黄金柱确认（注入判定）"
                except Exception:
                    pass
            # 简化版黄金柱判定
            is_golden, reason = self._is_golden_pillar_simple(data, idx)
            if is_golden:
                return idx, reason

        return None, "未找到已确认黄金柱"

    def _find_left_key_points(self, data: Dict[str, Any], center_idx: int, center_price: float) -> List[Dict[str, Any]]:
        """找左侧关键穴位（七个生根穴位之一），用于斜衡线取点。
        返回关键点列表，每个点包含 idx, price, point_type。
        """
        o, h, l, c, v = self._extract_series(data)
        key_points = []

        # 在中心左侧找关键穴位
        for idx in range(max(0, center_idx - 60), center_idx):
            if idx < 1:
                continue
            # 大阴实顶
            if c[idx] < o[idx]:
                body = o[idx] - c[idx]
                prev_body = abs(c[idx - 1] - o[idx - 1]) if idx >= 1 else 0
                if body > 0 and (prev_body == 0 or body >= prev_body * 1.5):
                    key_points.append({"idx": idx, "price": max(o[idx], c[idx]), "point_type": "big_yin_real_top"})
                    continue

            # 大阳实底
            if c[idx] > o[idx]:
                body = c[idx] - o[idx]
                prev_body = abs(c[idx - 1] - o[idx - 1]) if idx >= 1 else 0
                if body > 0 and (prev_body == 0 or body >= prev_body * 1.5):
                    key_points.append({"idx": idx, "price": min(o[idx], c[idx]), "point_type": "big_yang_real_bottom"})
                    continue

            # 倍量柱实顶
            if v[idx - 1] > 0 and v[idx] / v[idx - 1] >= 1.9:
                key_points.append({"idx": idx, "price": max(o[idx], c[idx]), "point_type": "double_volume_real_top"})
                continue

            # 真顶（阶段性高点）
            if idx >= 5 and idx + 1 < len(h):
                left_start = max(0, idx - 5)
                if h[idx] == max(h[left_start:idx + 1]) and h[idx + 1] < h[idx]:
                    key_points.append({"idx": idx, "price": h[idx], "point_type": "true_peak"})
                    continue

            # 真底（阶段性低点）
            if idx >= 5 and idx + 1 < len(l):
                left_start = max(0, idx - 5)
                if l[idx] == min(l[left_start:idx + 1]) and l[idx + 1] > l[idx]:
                    key_points.append({"idx": idx, "price": l[idx], "point_type": "true_valley"})
                    continue

        # 去重（同一idx只保留一个）
        seen = set()
        unique_points = []
        for p in key_points:
            if p["idx"] not in seen:
                seen.add(p["idx"])
                unique_points.append(p)

        return unique_points[:5]  # 最多取5个关键点

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """灯塔线检测主入口"""
        o, _, _, c, v = self._extract_series(data)
        n = len(c)

        if n < 13:  # 至少需要黄金柱+后三日+左侧关键点
            return self._invalid_result(date, "数据不足，无法判定灯塔线")

        t_idx = n - 1

        # 第一步：找已确认黄金柱
        golden_idx, golden_reason = self._find_golden_pillar(data)
        if golden_idx is None:
            return self._invalid_result(date, f"未找到已确认黄金柱（{golden_reason}）")

        # 第二步：计算中心价位（黄金柱实顶）
        center_price = max(o[golden_idx], c[golden_idx])
        dates = data.get("dates", [])
        center_date = dates[golden_idx] if golden_idx < len(dates) else f"idx_{golden_idx}"

        # 第三步：构建灯塔线（平衡线 + 斜衡线射线）
        lines = []

        # 平衡线（水平射线）
        lines.append({"type": "balance", "price": round(center_price, 4)})

        # 斜衡线（以黄金柱实顶为端点，与左侧关键穴位连线）
        key_points = self._find_left_key_points(data, golden_idx, center_price)
        for kp in key_points:
            interval = golden_idx - kp["idx"]
            if interval <= 0:
                continue
            slope = (center_price - kp["price"]) / interval
            lines.append({
                "type": "slant",
                "slope": round(slope, 6),
                "anchor_date": dates[kp["idx"]] if kp["idx"] < len(dates) else f"idx_{kp['idx']}",
                "anchor_price": round(kp["price"], 4),
                "point_type": kp["point_type"],
            })

        # 第四步：位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 第五步：性质描述
        nature = "趋势导航线（整理者分析，非权威来源）"

        result = {
            "signal_id": self.signal_id,
            "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
            "is_valid": True,
            "center_date": center_date,
            "center_price": round(center_price, 4),
            "golden_pillar_confirmed": True,
            "lines": lines,
            "有效射程": "未量化【未能核实】",
            "position": position,
            "nature": nature,
            "confidence": "confirmed",
        }

        return result

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "center_date": None,
            "center_price": None,
            "golden_pillar_confirmed": False,
            "lines": [],
            "有效射程": None,
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
