"""倍量柱信号卡 - 规格卡3

规格来源：spec_batch1_basic_volume.md 规格卡3（倍量柱）
补充：spec_batch1_addendum.md（追加 position/nature 字段）
原著：《量柱擒涨停》（第4版）第二单元"倍量柱——实力与雄心的温度计"
零未来函数：倍量柱为当日确认信号（T日收盘后），仅使用当日及之前数据。

判定条件：
  V[t] / V[t-1] >= 1.9 且 C[t] > C[t-1]

位置-性质映射（spec_global_rules.md）：
  低位：主力建仓/启动信号
  中位：中性/换手性质
  高位：主力出货/诱多信号
"""

from typing import Any, Dict, List, Optional

from .base import BaseSignal
from ..utils.data_loader import DataLoader


class DoubleVolumeSignal(BaseSignal):
    """倍量柱信号检测引擎"""

    signal_id = "double_volume"
    signal_name = "倍量柱"

    VOLUME_RATIO_THRESHOLD = 1.9

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """检测倍量柱信号"""
        volume: List[float] = data.get("volume", [])
        close: List[float] = data.get("close", [])
        dates: List[str] = data.get("dates", [])

        if date is not None and dates:
            try:
                idx = dates.index(date)
            except ValueError:
                idx = len(volume) - 1
        else:
            idx = len(volume) - 1

        current_date = dates[idx] if (dates and idx < len(dates)) else None

        # 边界1：新股上市首日不判定（无V[t-1]数据）
        if DataLoader.is_new_stock_first_day(data, idx):
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=None, v_t_1=None, volume_ratio=None,
                c_t=None, c_t_1=None, price_change_pct=None,
                data_quality="new_stock_first_day",
                position_result=self._compute_position(data, date),
                note="新股上市首日，不判定倍量柱（无V[t-1]数据）",
            )

        # 边界2：数据异常
        current_vol = volume[idx] if idx < len(volume) else None
        current_close = close[idx] if idx < len(close) else None
        if current_vol is None or current_vol < 0 or current_close is None or current_close <= 0:
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=current_vol, v_t_1=None, volume_ratio=None,
                c_t=current_close, c_t_1=None, price_change_pct=None,
                data_quality="invalid_data",
                position_result=self._compute_position(data, date),
                note="当日成交量或收盘价数据异常，不判定倍量柱",
            )

        # 边界3：V[t-1]==0（停牌后首日），不判定（分母为0）
        prev_vol = volume[idx - 1] if idx - 1 >= 0 else None
        prev_close = close[idx - 1] if idx - 1 >= 0 else None
        if DataLoader.is_suspended(prev_vol) or prev_vol is None or prev_vol <= 0:
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=current_vol, v_t_1=prev_vol, volume_ratio=None,
                c_t=current_close, c_t_1=prev_close, price_change_pct=None,
                data_quality="suspended_prev_day",
                position_result=self._compute_position(data, date),
                note="前一日停牌（V[t-1]==0）或数据无效，不判定倍量柱（分母为0无意义）",
            )

        # 计算
        volume_ratio = round(current_vol / prev_vol, 4)
        price_change_pct = round((current_close - prev_close) / prev_close * 100, 4) if prev_close and prev_close > 0 else None

        # 判定
        volume_ok = volume_ratio >= self.VOLUME_RATIO_THRESHOLD
        price_ok = current_close > prev_close if prev_close is not None else False
        is_signal = volume_ok and price_ok

        position_result = self._compute_position(data, date)

        note_parts = []
        if volume_ok and not price_ok:
            note_parts.append("量能达标但价格不达标（放量下跌不是倍量柱）")
        if not volume_ok and price_ok:
            note_parts.append("价格上涨但量能未达1.9倍阈值")

        return self._build_result(
            idx=idx, current_date=current_date, is_signal=is_signal,
            v_t=current_vol, v_t_1=prev_vol, volume_ratio=volume_ratio,
            c_t=current_close, c_t_1=prev_close, price_change_pct=price_change_pct,
            data_quality="valid",
            position_result=position_result,
            note="；".join(note_parts) if note_parts else None,
        )

    def is_double_volume(self, data: Dict[str, Any], idx: int) -> bool:
        """纯判定方法：判定指定索引日是否为倍量柱

        供黄金柱等复合信号复用，不输出完整JSON，仅返回bool。
        严格按规格实现：V[t]/V[t-1] >= 1.9 且 C[t] > C[t-1]，含全部边界检查。

        Args:
            data: 行情数据（含 volume/close 列表）
            idx: 判定日索引

        Returns:
            True if 倍量柱，False otherwise
        """
        volume: List[float] = data.get("volume", [])
        close: List[float] = data.get("close", [])

        # 边界1：新股上市首日不判定
        if DataLoader.is_new_stock_first_day(data, idx):
            return False

        # 边界2：数据异常
        current_vol = volume[idx] if idx < len(volume) else None
        current_close = close[idx] if idx < len(close) else None
        if current_vol is None or current_vol < 0 or current_close is None or current_close <= 0:
            return False

        # 边界3：V[t-1]==0（停牌后首日）或数据无效，不判定
        prev_vol = volume[idx - 1] if idx - 1 >= 0 else None
        prev_close = close[idx - 1] if idx - 1 >= 0 else None
        if DataLoader.is_suspended(prev_vol) or prev_vol is None or prev_vol <= 0:
            return False

        # 判定：量能 >= 1.9 且 价格上涨
        volume_ratio = current_vol / prev_vol
        volume_ok = volume_ratio >= self.VOLUME_RATIO_THRESHOLD
        price_ok = current_close > prev_close if prev_close is not None else False
        return volume_ok and price_ok

    def _get_nature(self, position: str) -> str:
        """倍量柱位置-性质映射"""
        if position == "low":
            return "主力建仓/启动信号（原著：倍量柱是主力进场的明牌）"
        elif position == "high":
            return "主力出货/诱多信号（高位倍量需防对倒出货）"
        elif position == "mid":
            return "中性/换手性质（原著未明确定义，为整理者分析，非权威来源）"
        return "无法判定性质"

    def _build_result(
        self, idx: int, current_date: Optional[str], is_signal: bool,
        v_t: Optional[float], v_t_1: Optional[float], volume_ratio: Optional[float],
        c_t: Optional[float], c_t_1: Optional[float], price_change_pct: Optional[float],
        data_quality: str, position_result: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        position = position_result.get("position", "unknown")
        nature = self._get_nature(position)

        result: Dict[str, Any] = {
            "signal_id": self.signal_id,
            "signal_name": self.signal_name,
            "date": current_date,
            "is_signal": is_signal,
            "values": {
                "v_t": v_t,
                "v_t_1": v_t_1,
                "volume_ratio": volume_ratio,
                "c_t": c_t,
                "c_t_1": c_t_1,
                "price_change_pct": price_change_pct,
            },
            "confirmation_date": current_date,
            "data_quality": data_quality,
            "position": position,
            "nature": nature,
            "position_detail": position_result,
        }
        if note:
            result["note"] = note
        return result
