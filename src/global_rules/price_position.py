"""位置判定模块 - 全局规则

规格来源：spec_global_rules.md 第一部分
零未来函数：仅使用当日及之前数据。
原著声明："位置决定性质"为原著原文，但量化阈值（30%/70%）原著未给出【未能核实】，
本模块采用市场通用250日百分位法，属于整理者分析，非权威来源。
"""

from typing import Any, Dict, List, Optional


class PricePosition:
    """位置判定引擎

    计算当前收盘价在近250个交易日高低点区间中的相对位置百分位，
    并分为低位（<30%）、中位（30%-70%）、高位（>70%）三档。
    """

    WINDOW_FULL = 250
    WINDOW_MIN = 20
    LOW_THRESHOLD = 30.0
    HIGH_THRESHOLD = 70.0

    def compute(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """计算位置判定

        Args:
            data: 行情数据，须包含 high/low/close 列表（按日期升序）
            date: 判定日期索引，默认为最后一日

        Returns:
            位置判定结果字典
        """
        high: List[float] = data.get("high", [])
        low: List[float] = data.get("low", [])
        close: List[float] = data.get("close", [])

        # 确定判定索引
        if date is not None and "dates" in data:
            try:
                idx = data["dates"].index(date)
            except ValueError:
                idx = len(close) - 1
        else:
            idx = len(close) - 1

        # 边界：数据不足（上市不足20日）
        if idx < self.WINDOW_MIN - 1:
            return {
                "position_pct": None,
                "position": "unknown",
                "hhv_250": None,
                "llv_250": None,
                "window_days": idx + 1,
                "data_quality": "insufficient_data",
                "note": "上市不足20个有效交易日，不判定位置",
            }

        # 确定窗口起始索引
        window_start = max(0, idx - self.WINDOW_FULL + 1)
        window_days = idx - window_start + 1
        window_shrunk = window_days < self.WINDOW_FULL

        # 提取窗口内数据，排除异常值
        window_high: List[float] = []
        window_low: List[float] = []
        for i in range(window_start, idx + 1):
            h = high[i] if i < len(high) else None
            l = low[i] if i < len(low) else None
            if h is not None and l is not None and h > 0 and l > 0:
                window_high.append(h)
                window_low.append(l)

        if len(window_high) < self.WINDOW_MIN:
            return {
                "position_pct": None,
                "position": "unknown",
                "hhv_250": None,
                "llv_250": None,
                "window_days": len(window_high),
                "data_quality": "insufficient_valid_data",
                "note": "有效交易日不足20日，不判定位置",
            }

        hhv = max(window_high)
        llv = min(window_low)
        current_close = close[idx] if idx < len(close) else None

        if current_close is None or current_close <= 0:
            return {
                "position_pct": None,
                "position": "unknown",
                "hhv_250": hhv,
                "llv_250": llv,
                "window_days": window_days,
                "data_quality": "invalid_close",
                "note": "当日收盘价异常，不判定位置",
            }

        # 区间为零边界
        if hhv == llv:
            return {
                "position_pct": None,
                "position": "mid",
                "hhv_250": hhv,
                "llv_250": llv,
                "window_days": window_days,
                "data_quality": "degenerate_interval",
                "note": "区间为零（HHV==LLV），位置归为mid但附加警告",
            }

        # 计算位置百分位
        position_pct = (current_close - llv) / (hhv - llv) * 100.0

        # 分档
        if position_pct < self.LOW_THRESHOLD:
            position = "low"
        elif position_pct > self.HIGH_THRESHOLD:
            position = "high"
        else:
            position = "mid"

        note_parts = [
            "位置判定为非原著扩展规则，阈值30%/70%为整理者分析，非权威来源",
            "仅作为量柱信号的过滤器，不单独作为交易信号",
        ]
        if window_shrunk:
            note_parts.insert(0, "窗口收缩：上市不足250日，使用上市以来全部数据")

        return {
            "position_pct": round(position_pct, 2),
            "position": position,
            "hhv_250": hhv,
            "llv_250": llv,
            "window_days": window_days,
            "data_quality": "valid",
            "note": "；".join(note_parts),
        }
