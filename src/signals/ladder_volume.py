"""梯量柱信号卡 - 规格卡6

规格来源：spec_batch1_basic_volume.md 规格卡6（梯量柱）
补充：spec_batch1_addendum.md（追加 position/nature 字段）
原著：《量柱擒涨停》（第4版）第二单元"梯量柱——谋攻与防守的温度计"
零未来函数：梯量柱为当日确认信号（T日收盘后，T日为第三根连续梯量柱）。

判定条件：
  V[t] > V[t-1] > V[t-2]  （连续3根严格递增）

位置-性质映射（spec_global_rules.md）：
  低位：底部启动/动能积累信号
  中位：中性/趋势性质
  高位：高位派发/动能衰竭信号
"""

from typing import Any, Dict, List, Optional

from .base import BaseSignal
from ..utils.data_loader import DataLoader


class LadderVolumeSignal(BaseSignal):
    """梯量柱信号检测引擎"""

    signal_id = "ladder_volume"
    signal_name = "梯量柱"

    MIN_CONSECUTIVE = 3
    SUPER_LONG_THRESHOLD = 5

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """检测梯量柱信号"""
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
                increase_ratio_t=None, increase_ratio_t1=None, consecutive_count=0,
                data_quality="new_stock_first_day",
                position_result=self._compute_position(data, date),
                note="新股上市首日，不判定梯量柱（需至少3个有效交易日）",
            )

        # 边界2：数据不足
        if idx < 2:
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=None, v_t_1=None, v_t_2=None,
                increase_ratio_t=None, increase_ratio_t1=None, consecutive_count=0,
                data_quality="insufficient_data",
                position_result=self._compute_position(data, date),
                note="上市不足3个有效交易日，不判定梯量柱",
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
                increase_ratio_t=None, increase_ratio_t1=None, consecutive_count=0,
                data_quality="invalid_data",
                position_result=self._compute_position(data, date),
                note="成交量数据异常（负数或空值），梯量序列中断",
            )

        # 边界4：停牌日
        if (DataLoader.is_suspended(current_vol) or
                DataLoader.is_suspended(prev_vol) or
                DataLoader.is_suspended(prev2_vol)):
            return self._build_result(
idx=idx, current_date=current_date, is_signal=False,
                v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
                increase_ratio_t=None, increase_ratio_t1=None, consecutive_count=0,
                data_quality="suspended_in_sequence",
                position_result=self._compute_position(data, date),
                note="梯量序列中存在停牌日（V==0），梯量序列中断",
            )

        # 计算
        increase_ratio_t = round(current_vol / prev_vol, 4) if prev_vol and prev_vol > 0 else None
        increase_ratio_t1 = round(prev_vol / prev2_vol, 4) if prev2_vol and prev2_vol > 0 else None

        # 判定连续3根严格递增
        increase_t = current_vol > prev_vol
        increase_t1 = prev_vol > prev2_vol
        is_signal = increase_t and increase_t1

        # 计算连续梯量天数
        consecutive_count = self._count_consecutive(volume, idx)

        position_result = self._compute_position(data, date)

        note_parts = []
        if increase_t and not increase_t1:
            note_parts.append("仅2根递增（V[t-1]未大于V[t-2]），不判定（原著要求连续3根以上）")
if consecutive_count >= self.SUPER_LONG_THRESHOLD:
            note_parts.append(f"超长梯量（连续{consecutive_count}根），原著口诀'梯量盯三防四'提示第4根可能变盘")

        return self._build_result(
            idx=idx, current_date=current_date, is_signal=is_signal,
            v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
            increase_ratio_t=increase_ratio_t, increase_ratio_t1=increase_ratio_t1,
            consecutive_count=consecutive_count,
            data_quality="valid",
            position_result=position_result,
            note="；".join(note_parts) if note_parts else None,
        )

    def _count_consecutive(self, volume: List[float], idx: int) -> int:
        """计算从idx向前连续梯量的天数"""
        count = 1
        i = idx
        while i > 0:
            v_curr = volume[i] if i < len(volume) else None
            v_prev = volume[i - 1] if i - 1 >= 0 else None
            if (v_curr is None or v_prev is None or
                    v_curr <= 0 or v_prev <= 0 or
                    DataLoader.is_suspended(v_prev)):
break
            if v_curr > v_prev:
                count += 1
                i -= 1
            else:
                break
        return count

    def is_ladder_first_pillar(self, data: Dict[str, Any], idx: int) -> bool:
        """纯判定方法：判定指定索引日是否为梯量序列的第一根递增柱（梯量柱第一柱）

        供黄金柱基柱候选复用。"梯量柱第一柱"指连续梯量序列的起点柱：
        当日递增（V[idx] > V[idx-1]），且前一日不递增（V[idx-1] <= V[idx-2]），
        即当日是新一轮梯量递增的起点。

        注意：此判定仅使用 idx 日及之前数据，不涉及未来数据。
        后三日是否继续递增由黄金柱的量缩条件单独约束。

        Args:
            data: 行情数据（含 volume 列表）
            idx: 判定日索引

        Returns:
            True if 梯量柱第一柱，False otherwise
        """
        volume: List[float] = data.get("volume", [])

        # 边界：需至少3个有效交易日（V[idx], V[idx-1], V[idx-2]）
        if idx < 2:
            return False

        current_vol = volume[idx] if idx < len(volume) else None
        prev_vol = volume[idx - 1] if idx - 1 >= 0 else None
        prev2_vol = volume[idx - 2] if idx - 2 >= 0 else None

        # 边界：数据异常
        if (current_vol is None or current_vol < 0 or
prev_vol is None or prev_vol < 0 or
                prev2_vol is None or prev2_vol < 0):
            return False

        # 边界：停牌日（V==0）
        if (DataLoader.is_suspended(current_vol) or
                DataLoader.is_suspended(prev_vol) or
                DataLoader.is_suspended(prev2_vol)):
            return False

        # 判定：当日递增 且 前一日不递增（即当日是梯量序列起点）
        increase_today = current_vol > prev_vol
        not_increase_prev = prev_vol <= prev2_vol
        return increase_today and not_increase_prev

    def _get_nature(self, position: str) -> str:
        """梯量柱位置-性质映射"""
        if position == "low":
            return "底部启动/动能积累信号（原著：梯量柱是谋攻与防守的温度计）"
        elif position == "high":
            return "高位派发/动能衰竭信号（整理者分析，非权威来源）"
        elif position == "mid":
            return "中性/趋势性质（原著未明确定义，为整理者分析，非权威来源）"
        return "无法判定性质"

    def _build_result(
        self, idx: int, current_date: Optional[str], is_signal: bool,
        v_t: Optional[float], v_t_1: Optional[float], v_t_2: Optional[float],
increase_ratio_t: Optional[float], increase_ratio_t1: Optional[float],
        consecutive_count: int, data_quality: str,
        position_result: Dict[str, Any], note: Optional[str] = None,
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
                "increase_ratio_t": increase_ratio_t,
                "increase_ratio_t1": increase_ratio_t1,
                "consecutive_count": consecutive_count,
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