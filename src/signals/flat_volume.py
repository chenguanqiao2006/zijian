"""平量柱信号卡 - 规格卡4

规格来源：spec_batch1_basic_volume.md 规格卡4（平量柱）
补充：spec_batch1_addendum.md（追加 position/nature 字段）
原著：《量柱擒涨停》（第4版）第二单元"平量柱——蓄势与爆发的温度计"
零未来函数：平量柱为当日确认信号（T日收盘后，T日为第二根连续平量柱）。

判定条件：
  0.95 <= V[t]/V[t-1] <= 1.05 且 0.95 <= V[t-1]/V[t-2] <= 1.05
  （连续至少2根满足单根平量条件）

位置-性质映射（spec_global_rules.md）：
  低位：底部蓄势/变盘前兆信号
  中位：中性/均衡性质
  高位：高位滞涨/观望信号
"""

from typing import Any, Dict, List, Optional

from .base import BaseSignal
from ..utils.data_loader import DataLoader


class FlatVolumeSignal(BaseSignal):
    """平量柱信号检测引擎"""

    signal_id = "flat_volume"
    signal_name = "平量柱"

    RATIO_LOWER = 0.95
    RATIO_UPPER = 1.05
    MIN_CONSECUTIVE = 2
    SUPER_LONG_THRESHOLD = 8

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """检测平量柱信号"""
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

        # 边界1：新股上市首日不判定（需至少3个有效交易日）
        if DataLoader.is_new_stock_first_day(data, idx):
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=None, v_t_1=None, v_t_2=None,
                ratio_t_t1=None, ratio_t1_t2=None, consecutive_count=0,
                data_quality="new_stock_first_day",
                position_result=self._compute_position(data, date),
                note="新股上市首日，不判定平量柱（需至少3个有效交易日）",
            )

        # 边界2：数据不足（需至少3个有效交易日：V[t], V[t-1], V[t-2]）
        if idx < 2:
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=None, v_t_1=None, v_t_2=None,
                ratio_t_t1=None, ratio_t1_t2=None, consecutive_count=0,
                data_quality="insufficient_data",
                position_result=self._compute_position(data, date),
                note="上市不足3个有效交易日，不判定平量柱",
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
                ratio_t_t1=None, ratio_t1_t2=None, consecutive_count=0,
                data_quality="invalid_data",
                position_result=self._compute_position(data, date),
                note="成交量数据异常（负数或空值），平量序列中断",
            )

        # 边界4：V[t-1]==0 或 V[t-2]==0（停牌日），不判定
        if DataLoader.is_suspended(prev_vol) or DataLoader.is_suspended(prev2_vol):
            return self._build_result(
                idx=idx, current_date=current_date, is_signal=False,
                v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
                ratio_t_t1=None, ratio_t1_t2=None, consecutive_count=0,
                data_quality="suspended_in_sequence",
                position_result=self._compute_position(data, date),
                note="平量序列中存在停牌日（V==0），不判定平量柱",
            )

        # 计算比值
        ratio_t_t1 = round(current_vol / prev_vol, 4) if prev_vol and prev_vol > 0 else None
        ratio_t1_t2 = round(prev_vol / prev2_vol, 4) if prev2_vol and prev2_vol > 0 else None

        # 判定连续平量
        flat_t_t1 = (ratio_t_t1 is not None and self.RATIO_LOWER <= ratio_t_t1 <= self.RATIO_UPPER)
        flat_t1_t2 = (ratio_t1_t2 is not None and self.RATIO_LOWER <= ratio_t1_t2 <= self.RATIO_UPPER)

        # 计算连续平量天数（向前追溯）
        consecutive_count = self._count_consecutive(volume, idx)

        is_signal = flat_t_t1 and flat_t1_t2

        position_result = self._compute_position(data, date)

        note_parts = []
        if flat_t_t1 and not flat_t1_t2:
            note_parts.append("仅1根平量（V[t-1]/V[t-2]超出5%误差），不判定（原著要求两根以上）")
        if consecutive_count >= self.SUPER_LONG_THRESHOLD:
            note_parts.append(f"超长平量（连续{consecutive_count}根），变盘概率更高")

        return self._build_result(
            idx=idx, current_date=current_date, is_signal=is_signal,
            v_t=current_vol, v_t_1=prev_vol, v_t_2=prev2_vol,
            ratio_t_t1=ratio_t_t1, ratio_t1_t2=ratio_t1_t2,
            consecutive_count=consecutive_count,
            data_quality="valid",
            position_result=position_result,
            note="；".join(note_parts) if note_parts else None,
        )

    def _count_consecutive(self, volume: List[float], idx: int) -> int:
        """计算从idx向前连续平量的天数"""
        count = 1  # 至少包含当日
        i = idx
        while i > 0:
            v_curr = volume[i] if i < len(volume) else None
            v_prev = volume[i - 1] if i - 1 >= 0 else None
            if (v_curr is None or v_prev is None or
                    v_curr <= 0 or v_prev <= 0 or
                    DataLoader.is_suspended(v_prev)):
                break
            ratio = v_curr / v_prev
            if self.RATIO_LOWER <= ratio <= self.RATIO_UPPER:
                count += 1
                i -= 1
            else:
                break
        return count

    def is_flat_second_pillar(self, data: Dict[str, Any], idx: int) -> bool:
        """纯判定方法：判定指定索引日是否为平量序列的第二根持平柱（平量柱第二柱）

        供黄金柱基柱候选复用。"平量柱第二柱"指连续平量序列的第二根：
        当日平量（0.95 <= V[idx]/V[idx-1] <= 1.05），
        前一日平量（0.95 <= V[idx-1]/V[idx-2] <= 1.05），
        且 T-2日不是平量序列一部分（即T-1日是平量序列第一柱）。

        注意：此判定仅使用 idx 日及之前数据，不涉及未来数据。

        Args:
            data: 行情数据（含 volume 列表）
            idx: 判定日索引

        Returns:
            True if 平量柱第二柱，False otherwise
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

        # 判定1：当日平量
        if prev_vol <= 0:
            return False
        ratio_t = current_vol / prev_vol
        flat_today = self.RATIO_LOWER <= ratio_t <= self.RATIO_UPPER
        if not flat_today:
            return False

        # 判定2：前一日平量
        if prev2_vol <= 0:
            return False
        ratio_prev = prev_vol / prev2_vol
        flat_prev = self.RATIO_LOWER <= ratio_prev <= self.RATIO_UPPER
        if not flat_prev:
            return False

        # 判定3：T-2日不是平量序列一部分（即T-1日是平量序列第一柱）
        # 若 idx < 3（无T-3日），则默认T-1日是第一柱
        if idx >= 3:
            prev3_vol = volume[idx - 3] if idx - 3 >= 0 else None
            if prev3_vol is not None and prev3_vol > 0 and not DataLoader.is_suspended(prev3_vol):
                ratio_prev2 = prev2_vol / prev3_vol
                flat_prev2 = self.RATIO_LOWER <= ratio_prev2 <= self.RATIO_UPPER
                # 若T-2日也平量，则T-1日不是第一柱，当日不是第二柱
                if flat_prev2:
                    return False

        return True

    def _get_nature(self, position: str) -> str:
        """平量柱位置-性质映射"""
        if position == "low":
            return "底部蓄势/变盘前兆信号（原著：平量柱是蓄势与爆发的温度计）"
        elif position == "high":
            return "高位滞涨/观望信号（整理者分析，非权威来源）"
        elif position == "mid":
            return "中性/均衡性质（原著未明确定义，为整理者分析，非权威来源）"
        return "无法判定性质"

    def _build_result(
        self, idx: int, current_date: Optional[str], is_signal: bool,
        v_t: Optional[float], v_t_1: Optional[float], v_t_2: Optional[float],
        ratio_t_t1: Optional[float], ratio_t1_t2: Optional[float],
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
                "ratio_t_t1": ratio_t_t1,
                "ratio_t1_t2": ratio_t1_t2,
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
