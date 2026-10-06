"""平衡线（balance_line）—— 多空共享的警戒线

规格：spec_batch3_price_line.md 规格卡3
原著：《量线捉涨停》（第4版）第8讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 取点：七个生根穴位（大阴实顶/大阳实底/将军柱黄金柱实顶实底/倍量柱实顶/左峰）
2. 取点原则："上行找实顶，下行找实底，实点靠整点，无点找密点"
3. 画线：水平线
4. 确认日：大阴实顶/大阳实底/倍量柱当日确认；将军柱/黄金柱需后三日确认
5. 有效性：碰线/咬线/坐线行为验证
6. 攻防：碰线择机而退，咬线择机而进
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


# 大阴/大阳的实体倍数阈值（实体 > 前日实体 × BIG_YIN_YANG_RATIO）
BIG_YIN_YANG_RATIO = 1.5
# 最小实体阈值（避免极小实体被误判为大阴/大阳）
MIN_BODY_RATIO = 0.005  # 实体/价格 > 0.5%


class BalanceLine(BasePriceLine):
    """平衡线规格卡实现"""

    signal_id = "balance_line"
    signal_name = "平衡线"
    line_type = "horizontal"

    def __init__(self, double_volume_checker=None, golden_volume_checker=None,
                 general_volume_checker=None):
        """初始化平衡线检测器。

        Args:
            double_volume_checker: 倍量柱纯判定函数
            golden_volume_checker: 黄金柱纯判定函数
            general_volume_checker: 将军柱纯判定函数
        """
        super().__init__()
        self._double_volume_checker = double_volume_checker
        self._golden_volume_checker = golden_volume_checker
        self._general_volume_checker = general_volume_checker

    def _is_big_yin(self, data: Dict[str, Any], idx: int) -> bool:
        """判断是否为大阴线（C < O 且实体较大）"""
        o, _, _, c, _ = self._extract_series(data)
        if idx >= len(c) or idx < 1:
            return False
        if c[idx] >= o[idx]:
            return False  # 不是阴线
        body = o[idx] - c[idx]
        if body <= 0:
            return False
        # 实体/价格 > 最小阈值
        if body / c[idx] < MIN_BODY_RATIO:
            return False
        # 实体 > 前日实体 × 1.5
        prev_body = abs(c[idx - 1] - o[idx - 1])
        if prev_body > 0 and body < prev_body * BIG_YIN_YANG_RATIO:
            return False
        return True

    def _is_big_yang(self, data: Dict[str, Any], idx: int) -> bool:
        """判断是否为大阳线（C > O 且实体较大）"""
        o, _, _, c, _ = self._extract_series(data)
        if idx >= len(c) or idx < 1:
            return False
        if c[idx] <= o[idx]:
            return False  # 不是阳线
        body = c[idx] - o[idx]
        if body <= 0:
            return False
        if body / c[idx] < MIN_BODY_RATIO:
            return False
        prev_body = abs(c[idx - 1] - o[idx - 1])
        if prev_body > 0 and body < prev_body * BIG_YIN_YANG_RATIO:
            return False
        return True

    def _is_double_volume_simple(self, volumes: List[float], idx: int) -> bool:
        """简化版倍量柱判定：V[idx] / V[idx-1] >= 1.9 且 C[idx] > C[idx-1]"""
        if idx < 1 or idx >= len(volumes):
            return False
        if volumes[idx - 1] <= 0:
            return False
        return volumes[idx] / volumes[idx - 1] >= 1.9

    def _find_anchor(self, data: Dict[str, Any], t_idx: int) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """寻找平衡线取点。
        从右往左找最近的有效取点（七个生根穴位之一）。
        返回 (anchor_idx, anchor_type, balance_type)。

        anchor_type 取值：
        - big_yin_real_top: 大阴实顶
        - big_yang_real_bottom: 大阳实底
        - double_volume_real_top: 倍量柱实顶
        - golden_pillar: 黄金柱
        - general_pillar: 将军柱
        - left_peak: 左峰
        """
        o, h, _, c, v = self._extract_series(data)
        n = len(c)
        if n < 3:
            return None, None, None

        # 从右往左找（找最近的有效取点）
        for idx in range(t_idx, max(0, t_idx - 60), -1):
            if idx >= n or idx < 1:
                continue

            # 1. 大阴实顶（当日确认）
            if self._is_big_yin(data, idx):
                return idx, "big_yin_real_top", "real_point"

            # 2. 大阳实底（当日确认）
            if self._is_big_yang(data, idx):
                return idx, "big_yang_real_bottom", "real_point"

            # 3. 倍量柱实顶（当日确认）
            if self._double_volume_checker is not None:
                try:
                    if self._double_volume_checker(data, idx):
                        return idx, "double_volume_real_top", "real_point"
                except Exception:
                    pass
            if self._is_double_volume_simple(v, idx):
                return idx, "double_volume_real_top", "real_point"

            # 4. 黄金柱（需后三日确认，即 idx+3 <= t_idx）
            if self._golden_volume_checker is not None and idx + 3 <= t_idx:
                try:
                    if self._golden_volume_checker(data, idx):
                        return idx, "golden_pillar", "real_point"
                except Exception:
                    pass

            # 5. 将军柱（需后三日确认）
            if self._general_volume_checker is not None and idx + 3 <= t_idx:
                try:
                    if self._general_volume_checker(data, idx):
                        return idx, "general_pillar", "real_point"
                except Exception:
                    pass

        # 6. 左峰（左侧最近高峰的实顶）
        left_peak_idx = self._find_left_peak(data, t_idx)
        if left_peak_idx is not None:
            return left_peak_idx, "left_peak", "real_point"

        return None, None, None

    def _find_left_peak(self, data: Dict[str, Any], t_idx: int) -> Optional[int]:
        """找左峰：左侧最近的阶段性高峰实顶"""
        o, h, _, c, _ = self._extract_series(data)
        n = len(c)
        if n < 5:
            return None

        # 在 t_idx 左侧找最高价
        search_end = min(t_idx, n - 1)
        if search_end < 5:
            return None
        left_highs = h[:search_end]
        peak_idx = left_highs.index(max(left_highs))
        # 确认是阶段性高点（后续至少1根低于它）
        if peak_idx + 1 < n and h[peak_idx + 1] < h[peak_idx]:
            return peak_idx
        return None

    def _compute_line_price(self, data: Dict[str, Any], idx: int, anchor_type: str) -> float:
        """根据取点类型计算线价"""
        o, _, _, c, _ = self._extract_series(data)
        if anchor_type in ("big_yin_real_top", "double_volume_real_top", "left_peak"):
            # 上行找实顶
            return self._real_top(o[idx], c[idx])
        elif anchor_type == "big_yang_real_bottom":
            # 下行找实底
            return self._real_bottom(o[idx], c[idx])
        elif anchor_type in ("golden_pillar", "general_pillar"):
            # 王牌柱：取实顶（默认上行）
            return self._real_top(o[idx], c[idx])
        else:
            return self._real_top(o[idx], c[idx])

    def _check_touch_verify(self, data: Dict[str, Any], anchor_idx: int, line_price: float) -> Tuple[bool, str]:
        """检查平衡线的触线验证（碰线/咬线/坐线）"""
        _, h, l, c, _ = self._extract_series(data)
        n = len(c)
        if anchor_idx + 1 >= n:
            return False, "unverified"

        tolerance = line_price * 0.005
        touched = False
        for i in range(anchor_idx + 1, n):
            # 碰线：价格区间覆盖line_price
            if l[i] <= line_price + tolerance and h[i] >= line_price - tolerance:
                touched = True
                # 咬线：实体咬在平衡线上（实体跨线）
                if min(c[i], data.get("open", c)[i]) <= line_price <= max(c[i], data.get("open", c)[i]):
                    return True, "bite_line"
                # 坐线：收盘价在线上方附近
                if c[i] >= line_price - tolerance and c[i] <= line_price + tolerance * 2:
                    return True, "sit_line"

        if touched:
            return True, "touch_line"
        return False, "unverified"

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """平衡线检测主入口"""
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)

        if n < 3:
            return self._invalid_result(date, "数据不足，无法判定平衡线")

        t_idx = n - 1

        # 第一步：找取点
        anchor_idx, anchor_type, balance_type = self._find_anchor(data, t_idx)
        if anchor_idx is None:
            return self._invalid_result(date, "未找到符合七个生根穴位的取点")

        # 第二步：计算线价
        line_price = self._compute_line_price(data, anchor_idx, anchor_type)

        # 第三步：触线验证
        is_verified, verify_type = self._check_touch_verify(data, anchor_idx, line_price)

        # 第四步：位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 第五步：性质描述
        nature = self._get_nature(position)

        # 置信度
        confidence = "confirmed" if is_verified else "unconfirmed"

        # 日期
        dates = data.get("dates", [])
        anchor_date = dates[anchor_idx] if anchor_idx < len(dates) else f"idx_{anchor_idx}"

        return {
            "signal_id": self.signal_id,
            "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
            "is_valid": True,
            "line_type": self.line_type,
            "line_price": round(line_price, 4),
            "anchor_date": anchor_date,
            "anchor_type": anchor_type,
            "balance_type": balance_type,
            "position": position,
            "nature": nature,
            "confidence": confidence,
            "verify_type": verify_type,
        }

    def _get_nature(self, position: str) -> str:
        """平衡线的性质映射"""
        if position == "unknown":
            return "无法判定性质"
        return "多空警戒线（整理者分析，非权威来源）"

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "line_type": self.line_type,
            "line_price": None,
            "anchor_date": None,
            "anchor_type": None,
            "balance_type": None,
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
