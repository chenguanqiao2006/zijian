"""缩量柱信号卡 - 规格卡5

规格来源：spec_batch1_basic_volume.md 规格卡5（缩量柱）
补充：spec_batch1_addendum.md（追加 position/nature 字段）
原著：《量柱擒涨停》（第4版）第二单元"缩量柱——价格与趋势的温度计"
零未来函数：缩量柱为当日确认信号（T日收盘后，T日为第三根连续缩量柱）。

判定条件：
  V[t] < V[t-1] < V[t-2]  （连续3根严格递减）

位置-性质映射（spec_global_rules.md）：
  低位：底部抛压枯竭/建仓信号
  中位：中性/整理性质
  高位：高位缩量/出货后信号
"""

from typing import Any, Dict, List, Optional

from .base import BaseSignal
from ..utils.data_loader import DataLoader


class ShrinkVolumeSignal(BaseSignal):
    """缩量柱信号检测引擎"""

    signal_id = "shrink_volume"
    signal_name = "缩量柱"

    MIN_CONSECUTIVE = 3
    EXTREME_SHRINK_RATIO = 0.1

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """检测缩量柱信号"""
        volume: List[float] = data.get("volume", [])
        dates: List[str] = data.get("dates", [])

        if date is not None and dates:
            try:
                idx = dates.index(date)
            except ValueError:
                idx = len(volume) - 1
        else:
            idx = len(volume) - 1

        current_date = dates[idx] if (dates and idx < len(dates)) else None

        # 边界1：新股上市首日不判定
        if DataLoader.is_new_stock_first_day(data, idx):
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=None, v_t_1=None, v_t_2=None,
                shrink_ratio_t=None, shrink_ratio_t1=None, consecutive_count=0,
                extreme_shrink=False, needs_human_review=False,
                data_quality="new_stock_first_day",
                position_result=self._compute_position(data, date),
                note="新股上市首日，不判定缩量柱（需至少3个有效交易日）",
            )

        # 边界2：数据不足
        if idx < 2:
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=None, v_t_1=None, v_t_2=None,
                shrink_ratio_t=None, shrink_ratio_t1=None, consecutive_count=0,
                extreme_shrink=False, needs_human_review=False,
                data_quality="insufficient_data",
                position_result=self._compute_position(data, date),
                note="上市不足3个有效交易日，不判定缩量柱",
            )

        current_vol = volume[idx] if idx < len(volume) else None
        prev_vol = volume[idx - 1] if idx - 1 >= 0 else None
        prev2_vol = volume[idx - 2] if idx - 2 >= 0 else None

        # 边界3：数据异常
        if (current_vol is None or current_vol < 0 or
                prev_vol is None or prev_vol < 0 or
                prev2_vol is None or prev2_vol < 0):
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
                shrink_ratio_t=None, shrink_ratio_t1=None, consecutive_count=0,
                extreme_shrink=False, needs_human_review=False,
                data_quality="invalid_data",
                position_result=self._compute_position(data, date),
                note="成交量数据异常（负数或空值），缩量序列中断",
            )

        # 边界4：停牌日
        if (DataLoader.is_suspended(current_vol) or
                DataLoader.is_suspended(prev_vol) or
                DataLoader.is_suspended(prev2_vol)):
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
                shrink_ratio_t=None, shrink_ratio_t1=None, consecutive_count=0,
                extreme_shrink=False, needs_human_review=False,
                data_quality="suspended_in_sequence",
                position_result=self._compute_position(data, date),
                note="缩量序列中存在停牌日（V==0），缩量序列中断",
            )

        # 计算
        shrink_ratio_t = round(current_vol / prev_vol, 4) if prev_vol and prev_vol > 0 else None
        shrink_ratio_t1 = round(prev_vol / prev2_vol, 4) if prev2_vol and prev2_vol > 0 else None

        # 判定连续3根严格递减
        shrink_t = current_vol < prev_vol
        shrink_t1 = prev_vol < prev2_vol
        is_signal = shrink_t and shrink_t1

        # 计算连续缩量天数
        consecutive_count = self._count_consecutive(volume, idx)

        # 极端缩量检测
        extreme_shrink = False
        needs_human_review = False
        if prev_vol and prev_vol > 0 and current_vol < prev_vol * self.EXTREME_SHRINK_RATIO:
            extreme_shrink = True
            needs_human_review = True

        position_result = self._compute_position(data, date)

        note_parts = []
        if shrink_t and not shrink_t1:
            note_parts.append("仅2根递减（V[t-1]未小于V[t-2]），不判定（原著要求连续3根以上）")
        if extreme_shrink:
            note_parts.append("极端缩量（V[t] < V[t-1] × 0.1），需人工复核，不得直接作为交易依据")

        return self._build_result(
            idx=idx, current_date=current_date, is_signal=is_signal,
            v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
            shrink_ratio_t=shrink_ratio_t, shrink_ratio_t1=shrink_ratio_t1,
            consecutive_count=consecutive_count,
            extreme_shrink=extreme_shrink, needs_human_review=needs_human_review,
            data_quality="valid",
            position_result=position_result,
            note="；".join(note_parts) if note_parts else None,
        )

    def _count_consecutive(self, volume: List[float], idx: int) -> int:
        """计算从idx向前连续缩量的天数"""
        count = 1
        i = idx
        while i > 0:
            v_curr = volume[i] if i < len(volume) else None
            v_prev = volume[i - 1] if i - 1 >= 0 else None
            if (v_curr is None or v_prev is None or
                    v_curr <= 0 or v_prev <= 0 or
                    DataLoader.is_suspended(v_prev)):
                break
            if v_curr < v_prev:
                count += 1
                i -= 1
            else:
                break
        return count

    def _get_nature(self, position: str) -> str:
        """缩量柱位置-性质映射"""
        if position == "low":
            return "底部抛压枯竭/建仓信号（原著：缩量柱是价格与趋势的温度计）"
        elif position == "high":
            return "高位缩量/出货后信号（整理者分析，非权威来源）"
        elif position == "mid":
            return "中性/整理性质（原著未明确定义，为整理者分析，非权威来源）"
        return "无法判定性质"

    def _build_result(
        self, idx: int, current_date: Optional[str], is_signal: bool,
        v_t: Optional[float], v_t_1: Optional[float], v_t_2: Optional[float],
        shrink_ratio_t: Optional[float], shrink_ratio_t1: Optional[float],
        consecutive_count: int, extreme_shrink: bool, needs_human_review: bool,
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
                "v_t_2": v_t_2,
                "shrink_ratio_t": shrink_ratio_t,
                "shrink_ratio_t1": shrink_ratio_t1,
                "consecutive_count": consecutive_count,
                "extreme_shrink": extreme_shrink,
                "needs_human_review": needs_human_review,
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
