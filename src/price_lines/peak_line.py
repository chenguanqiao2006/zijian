"""峰顶线（peak_line）—— 测顶攻顶的预警线

规格：spec_batch3_price_line.md 规格卡1
原著：《量线捉涨停》（第4版）第6讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 取点：阶段性真顶（左侧至少N=5根K线内最高），对应高量柱或黄金柱，优先取实顶
2. 确认：后续至少1根K线最高价 < 取点最高价（T+1日收盘后确认）
3. 画线：水平线，line_price = 实顶（优先）或虚顶
4. 有效性：取点确认 + 量柱生根 + 触线验证（触线回落或突破后回踩不破）
5. 异化：股价有效突破后，峰顶线由压力线转为支撑线（顶底互换）
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


# 观察窗口N：阶段性真顶的左侧观察K线数（原著未给量化N，工程化建议N≥5）
PEAK_WINDOW = 5
# 确认所需后续K线数
CONFIRM_BARS = 1


class PeakLine(BasePriceLine):
    """峰顶线规格卡实现"""

    signal_id = "peak_line"
    signal_name = "峰顶线"
    line_type = "horizontal"

    def __init__(self, high_volume_checker=None, golden_volume_checker=None):
        """初始化峰顶线检测器。

        Args:
            high_volume_checker: 高量柱纯判定函数 is_high_volume(data, idx) -> bool，
                                 若为None则使用内置简化判定。
            golden_volume_checker: 黄金柱纯判定函数，若为None则跳过黄金柱检查。
        """
        super().__init__()
        self._high_volume_checker = high_volume_checker
        self._golden_volume_checker = golden_volume_checker

    def _is_high_volume_simple(self, volumes: List[float], idx: int) -> bool:
        """简化版高量柱判定：V[idx] == HHV(V, 10)。
        完整判定应复用 HighVolumeSignal 的双标准A OR B。
        """
        if idx < 9:
            return False
        window = volumes[max(0, idx - 9):idx + 1]
        return volumes[idx] == max(window) and volumes[idx] > 0

    def _is_anchor_volume_valid(self, data: Dict[str, Any], idx: int) -> Tuple[bool, str]:
        """检查取点K线的量柱是否为高量柱或黄金柱（量线生根）。
        返回 (is_valid, volume_type)。
        """
        volumes = data.get("volume", [])
        if idx >= len(volumes):
            return False, "none"

        # 优先使用注入的高量柱判定函数
        if self._high_volume_checker is not None:
            try:
                if self._high_volume_checker(data, idx):
                    return True, "high_volume"
            except Exception:
                pass

        # 简化版高量柱判定
        if self._is_high_volume_simple(volumes, idx):
            return True, "high_volume"

        # 黄金柱检查（若注入了判定函数）
        if self._golden_volume_checker is not None:
            try:
                if self._golden_volume_checker(data, idx):
                    return True, "golden_volume"
            except Exception:
                pass

        return False, "none"

    def _find_peak_anchor(self, data: Dict[str, Any], t_idx: int) -> Tuple[Optional[int], Optional[str]]:
        """寻找阶段性真顶取点。
        在 t_idx 之前（含t_idx）寻找满足条件的真顶。
        返回 (anchor_idx, anchor_price_type)，找不到返回 (None, None)。

        真顶条件：
        1. 左侧至少PEAK_WINDOW根K线内最高价
        2. 右侧至少CONFIRM_BARS根K线最高价 < 取点最高价（已确认）
        3. 取点K线对应量柱为高量柱或黄金柱
        """
        _, h, _, _, _ = self._extract_series(data)
        n = len(h)
        if n < PEAK_WINDOW + CONFIRM_BARS + 1:
            return None, None

        # 从右往左找（找最近的有效真顶）
        for idx in range(t_idx, PEAK_WINDOW - 1, -1):
            if idx >= n:
                continue
            # 条件1：左侧PEAK_WINDOW根内最高
            left_start = max(0, idx - PEAK_WINDOW)
            if h[idx] != max(h[left_start:idx + 1]):
                continue

            # 条件2：右侧至少CONFIRM_BARS根确认（最高价 < 取点最高价）
            if idx + CONFIRM_BARS >= n:
                continue  # 后续数据不足，未确认
            right_end = min(n, idx + CONFIRM_BARS + 1)
            if max(h[idx + 1:right_end]) >= h[idx]:
                continue  # 后续创新高，取点失效

            # 条件3：量柱生根（高量柱或黄金柱）
            vol_valid, _ = self._is_anchor_volume_valid(data, idx)
            if not vol_valid:
                continue

            # 取点价位类型：优先实顶
            return idx, "real_top"

        return None, None

    def _check_touch_verify(self, data: Dict[str, Any], anchor_idx: int, line_price: float) -> Tuple[bool, str]:
        """检查峰顶线的触线验证。
        在取点之后的K线中，是否出现：
        - 触线回落（股价接近line_price后回落，验证压力作用）
        - 或有效突破后回踩不破（验证异化后的支撑作用）
        返回 (is_verified, verify_type)。
        """
        _, h, _, c, _ = self._extract_series(data)
        n = len(c)
        if anchor_idx + 1 >= n:
            return False, "unverified"

        # 容差：股价接近line_price的范围（0.5%）
        tolerance = line_price * 0.005

        touched = False
        broken = False
        for i in range(anchor_idx + 1, n):
            # 触线：最高价接近或触及line_price
            if h[i] >= line_price - tolerance:
                touched = True
                # 触线后回落（收盘价 < line_price）→ 压力验证
                if c[i] < line_price:
                    return True, "touch_fall"
                # 有效突破（收盘价 > line_price）→ 可能异化
                if c[i] > line_price:
                    broken = True

            # 突破后回踩不破（收盘价 >= line_price）→ 异化支撑验证
            if broken and c[i] >= line_price and h[i] >= line_price - tolerance:
                return True, "break_support"

        if touched:
            return False, "touch_unconfirmed"
        return False, "unverified"

    def _check_异化状态(self, data: Dict[str, Any], anchor_idx: int, line_price: float) -> str:
        """检查峰顶线的异化状态。
        - 未异化：股价仍在line_price下方
        - 已异化（顶底互换）：股价有效突破后回踩不破
        - 异化失败：突破后回踩跌破
        """
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)
        if anchor_idx + 1 >= n:
            return "未异化"

        broken = False
        for i in range(anchor_idx + 1, n):
            if c[i] > line_price:
                broken = True
            if broken and c[i] < line_price:
                return "异化失败"
        if broken:
            return "已异化（顶底互换）"
        return "未异化"

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """峰顶线检测主入口。

        Args:
            data: 行情数据字典，须含 open/high/low/close/volume 序列
            date: 检测日期（可选）

        Returns:
            峰顶线检测结果JSON
        """
        _, h, _, c, v = self._extract_series(data)
        n = len(c)

        # 基础校验
        if n < PEAK_WINDOW + CONFIRM_BARS + 1:
            return self._invalid_result(date, "数据不足，无法判定峰顶线")

        # T日索引（最后一根K线）
        t_idx = n - 1

        # 第一步：找阶段性真顶取点
        anchor_idx, anchor_price_type = self._find_peak_anchor(data, t_idx)
        if anchor_idx is None:
            return self._invalid_result(date, "未找到符合条件的阶段性真顶")

        # 第二步：计算线价
        o = data.get("open", [])
        if anchor_price_type == "real_top":
            line_price = self._real_top(o[anchor_idx], c[anchor_idx])
        else:
            line_price = h[anchor_idx]

        # 第三步：触线验证
        is_verified, verify_type = self._check_touch_verify(data, anchor_idx, line_price)

        # 第四步：异化状态
        异化状态 = self._check_异化状态(data, anchor_idx, line_price)

        # 第五步：位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 第六步：性质描述
        nature = self._get_nature(position)

        # 置信度
        if is_verified:
            confidence = "confirmed"
        else:
            confidence = "unconfirmed"

        # 取点日期
        dates = data.get("dates", [])
        anchor_date = dates[anchor_idx] if anchor_idx < len(dates) else f"idx_{anchor_idx}"

        return {
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

    def _get_nature(self, position: str) -> str:
        """峰顶线的性质映射（整理者分析，非权威来源）"""
        if position == "unknown":
            return "无法判定性质"
        if position == "high":
            return "高位压力线（整理者分析，非权威来源）"
        if position == "mid":
            return "阶段性压力线（整理者分析，非权威来源）"
        return "低位压力线（整理者分析，非权威来源）"

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
