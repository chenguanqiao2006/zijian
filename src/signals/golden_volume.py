"""黄金柱信号卡 - 规格卡7

规格来源：spec_batch1_basic_volume.md 规格卡7（黄金柱）
补充：spec_batch1_addendum.md（追加 position/nature 字段）
补充：spec_batch1_addendum_v2.md（阳胜柱前置条件 + 不破实顶最低价口径）
原著：《量柱擒涨停》（第4版）第三单元"黄金柱——牛股与黑马的温度计"
零未来函数：黄金柱为滞后确认信号，确认日为基柱后第三日收盘后（T+3日）。

判定条件（含addendum_v2阳胜柱前置）：
  golden_volume[t+3] =
    (double_volume[t] OR high_volume[t] OR ladder_volume_first[t] OR flat_volume_second[t])
    AND (C[t] > C[left_ying] AND V[t] > V[left_ying])  -- 阳胜柱前置（addendum_v2）
    AND ((C[t+1] + C[t+2] + C[t+3]) / 3 >= MAX(C[t], O[t]))  -- 收盘价均值条件
    AND (V[t+1] <= V[t] AND V[t+2] <= V[t] AND V[t+3] <= V[t])  -- 量条件
    AND (MIN(L[t+1], L[t+2], L[t+3]) >= MAX(C[t], O[t]))  -- 不破实顶（最低价口径）

位置-性质映射（spec_global_rules.md）：
  低位：主力高度控盘/拉升支撑信号
  中位：中性/换手性质
  高位：高位出货/诱多信号
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseSignal
from .double_volume import DoubleVolumeSignal
from .high_volume import HighVolumeSignal
from .flat_volume import FlatVolumeSignal
from .ladder_volume import LadderVolumeSignal
from ..utils.data_loader import DataLoader


class GoldenVolumeSignal(BaseSignal):
    """黄金柱信号检测引擎"""

    signal_id = "golden_volume"
    signal_name = "黄金柱"

    DOUBLE_VOLUME_THRESHOLD = 1.9
    EXTREME_SHRINK_RATIO = 0.1

    def __init__(self):
        super().__init__()
        self._double_signal = DoubleVolumeSignal()
        self._high_signal = HighVolumeSignal()
        self._flat_signal = FlatVolumeSignal()
        self._ladder_signal = LadderVolumeSignal()

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """检测黄金柱信号

        黄金柱为滞后确认信号，date参数指定的是确认日（T+3日），
        信号会自动向前追溯3日找到基柱日（T日）。

        Args:
            data: 行情数据，须包含 volume/close/open/high/low 列表
            date: 确认日期（T+3日），默认为最后一日

        Returns:
            黄金柱判定结果JSON
        """
        volume: List[float] = data.get("volume", [])
        close: List[float] = data.get("close", [])
        open_: List[float] = data.get("open", [])
        high: List[float] = data.get("high", [])
        low: List[float] = data.get("low", [])
        dates: List[str] = data.get("dates", [])

        # 确认日索引（T+3日）
        if date is not None and dates:
            try:
                confirm_idx = dates.index(date)
            except ValueError:
                confirm_idx = len(volume) - 1
        else:
            confirm_idx = len(volume) - 1

        # 基柱日索引（T日 = 确认日 - 3）
        base_idx = confirm_idx - 3

        confirm_date = dates[confirm_idx] if (dates and confirm_idx < len(dates)) else None
        base_date = dates[base_idx] if (dates and 0 <= base_idx < len(dates)) else None

        # 边界1：数据不足（需至少4个有效交易日：T日至T+3日）
        if base_idx < 0:
            return self._build_result(
                base_idx=base_idx, confirm_idx=confirm_idx,
                base_date=base_date, confirm_date=confirm_date,
                is_signal=False, base_pillar_type=None, strength="none",
                data_quality="insufficient_data",
                position_result=self._compute_position(data, date),
                note="数据不足：确认日前推3日无有效基柱日，黄金柱需至少4个连续有效交易日",
            )

        # 边界2：新股上市（需至少10个有效交易日历史数据）
        if base_idx < 9:
            return self._build_result(
                base_idx=base_idx, confirm_idx=confirm_idx,
                base_date=base_date, confirm_date=confirm_date,
                is_signal=False, base_pillar_type=None, strength="none",
                data_quality="new_stock",
                position_result=self._compute_position(data, date),
                note="新股上市不足10个有效交易日，不判定黄金柱",
            )

        # 提取基柱日数据（T日）
        base_v = volume[base_idx] if base_idx < len(volume) else None
        base_c = close[base_idx] if base_idx < len(close) else None
        base_o = open_[base_idx] if base_idx < len(open_) else None
        base_real_top = max(base_c, base_o) if (base_c is not None and base_o is not None) else None

        # 提取后三日数据（T+1, T+2, T+3）
        day1_v = volume[base_idx + 1] if base_idx + 1 < len(volume) else None
        day1_c = close[base_idx + 1] if base_idx + 1 < len(close) else None
        day1_l = low[base_idx + 1] if base_idx + 1 < len(low) else None
        day2_v = volume[base_idx + 2] if base_idx + 2 < len(volume) else None
        day2_c = close[base_idx + 2] if base_idx + 2 < len(close) else None
        day2_l = low[base_idx + 2] if base_idx + 2 < len(low) else None
        day3_v = volume[base_idx + 3] if base_idx + 3 < len(volume) else None
        day3_c = close[base_idx + 3] if base_idx + 3 < len(close) else None
        day3_l = low[base_idx + 3] if base_idx + 3 < len(low) else None

        # 边界3：数据异常
        if any(v is None or v < 0 for v in [base_v, day1_v, day2_v, day3_v]):
            return self._build_result(
                base_idx=base_idx, confirm_idx=confirm_idx,
                base_date=base_date, confirm_date=confirm_date,
                is_signal=False, base_pillar_type=None, strength="none",
                data_quality="invalid_volume",
                position_result=self._compute_position(data, date),
                note="成交量数据异常（负数或空值），黄金柱判定失效",
            )

        # 边界4：后三日中存在停牌日
        if any(DataLoader.is_suspended(v) for v in [day1_v, day2_v, day3_v]):
            return self._build_result(
                base_idx=base_idx, confirm_idx=confirm_idx,
                base_date=base_date, confirm_date=confirm_date,
                is_signal=False, base_pillar_type=None, strength="none",
                data_quality="suspended_in_validation",
                position_result=self._compute_position(data, date),
                note="后三日中存在停牌日，黄金柱判定失效（后三日必须为连续有效交易日）",
            )

        # === 判定1：基柱条件（四种候选之一）===
        base_pillar_type, base_pillar_ok = self._check_base_pillar(
            data, volume, close, open_, base_idx
        )

        # === 判定2：阳胜柱前置条件（addendum_v2）===
        yang_sheng_ok, left_ying_idx, yang_sheng_note = self._check_yang_sheng(
            volume, close, open_, base_idx
        )

        # === 判定3：后三日收盘价均值条件 ===
        avg_close_after = None
        close_avg_hold = False
        if all(c is not None for c in [day1_c, day2_c, day3_c]) and base_real_top is not None:
            avg_close_after = round((day1_c + day2_c + day3_c) / 3, 4)
            close_avg_hold = avg_close_after >= base_real_top

        # === 判定4：后三日量条件 ===
        volume_not_exceed = all(
            v is not None and base_v is not None and v <= base_v
            for v in [day1_v, day2_v, day3_v]
        )

        # === 判定5：不破实顶（最低价口径，addendum_v2）===
        min_low_after = None
        hold_real_top = False
        if all(l is not None for l in [day1_l, day2_l, day3_l]) and base_real_top is not None:
            min_low_after = min(day1_l, day2_l, day3_l)
            hold_real_top = min_low_after >= base_real_top

        # === 总判定 ===
        is_signal = (
            base_pillar_ok and yang_sheng_ok and
            close_avg_hold and volume_not_exceed and hold_real_top
        )

        # === 信号强度分级（可选最强版）===
        strength = "none"
        strong_version = False
        if is_signal:
            price_strong = (day1_c is not None and day2_c is not None and day3_c is not None and
                           day1_c < day2_c < day3_c)
            volume_strong = (day1_v is not None and day2_v is not None and day3_v is not None and
                            day1_v > day2_v > day3_v)
            if price_strong and volume_strong:
                strength = "strong"
                strong_version = True
            else:
                strength = "normal"

        # 极端缩量检测（后三日中）
        extreme_shrink = False
        if base_v and base_v > 0:
            for v in [day1_v, day2_v, day3_v]:
                if v is not None and v < base_v * self.EXTREME_SHRINK_RATIO:
                    extreme_shrink = True
                    break

        position_result = self._compute_position(data, date)

        note_parts = []
        if not base_pillar_ok:
            note_parts.append("基柱不属于四种候选形态（倍量柱/高量柱/梯量柱第一柱/平量柱第二柱）")
        if not yang_sheng_ok:
            note_parts.append(f"基柱不满足阳胜柱前置条件：{yang_sheng_note}")
        if not close_avg_hold:
            note_parts.append("后三日收盘价均值低于基柱实顶（不满足价升核心条件）")
        if not volume_not_exceed:
            note_parts.append("后三日某日量超过基柱量（不满足量缩核心条件）")
        if not hold_real_top:
            note_parts.append("后三日最低价跌破基柱实顶（不破实顶条件不满足）")
        if extreme_shrink and is_signal:
            note_parts.append("后三日中存在极端缩量（V < V[t] × 0.1），需人工复核")

        return self._build_result(
            base_idx=base_idx, confirm_idx=confirm_idx,
            base_date=base_date, confirm_date=confirm_date,
            is_signal=is_signal, base_pillar_type=base_pillar_type,
            strength=strength,
            base_v=base_v, base_c=base_c, base_o=base_o, base_real_top=base_real_top,
            day1_v=day1_v, day1_c=day1_c, day2_v=day2_v, day2_c=day2_c,
            day3_v=day3_v, day3_c=day3_c,
            avg_close_after=avg_close_after, min_low_after=min_low_after,
            close_avg_hold=close_avg_hold, volume_not_exceed=volume_not_exceed,
            hold_real_top=hold_real_top, strong_version=strong_version,
            yang_sheng_ok=yang_sheng_ok, left_ying_idx=left_ying_idx,
            data_quality="valid",
            position_result=position_result,
            note="；".join(note_parts) if note_parts else None,
        )

    def _check_base_pillar(
        self, data: Dict[str, Any], volume: List[float],
        close: List[float], open_: List[float], base_idx: int
    ) -> Tuple[Optional[str], bool]:
        """检查基柱是否为四种候选形态之一（复用已实现的信号卡纯判定方法）

        基柱候选 = 倍量柱 OR 高量柱 OR 梯量柱第一柱 OR 平量柱第二柱
        每种候选的判定严格按对应信号卡规格实现，不做简化。

        Returns:
            (base_pillar_type, is_match)：基柱类型和是否命中
        """
        # 候选1：倍量柱（复用 DoubleVolumeSignal.is_double_volume）
        if self._double_signal.is_double_volume(data, base_idx):
            return "double_volume", True

        # 候选2：高量柱（复用 HighVolumeSignal.is_high_volume，双标准A OR B）
        if self._high_signal.is_high_volume(data, base_idx):
            return "high_volume", True

        # 候选3：梯量柱第一柱（复用 LadderVolumeSignal.is_ladder_first_pillar）
        if self._ladder_signal.is_ladder_first_pillar(data, base_idx):
            return "ladder_volume_first", True

        # 候选4：平量柱第二柱（复用 FlatVolumeSignal.is_flat_second_pillar）
        if self._flat_signal.is_flat_second_pillar(data, base_idx):
            return "flat_volume_second", True

        return None, False

    def _check_yang_sheng(
        self, volume: List[float], close: List[float], open_: List[float], base_idx: int
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """检查阳胜柱前置条件（addendum_v2，严格实现）

        规格原文：yang_win[t] = (C[t] > C[left_ying]) AND (V[t] > V[left_ying])
        其中 left_ying 为"向左遍历第一个满足 C[day] < O[day] 的交易日"。

        判定逻辑：
        1. 从 base_idx-1 向左遍历，找第一个满足 C[day] < O[day] 的交易日作为 left_ying
        2. 若找不到 left_ying（上市以来无阴柱），返回 False，标注"无左侧阴柱"
        3. 严格判断 C[t] > C[left_ying] 且 V[t] > V[left_ying]（严格大于，非大于等于）

        Returns:
            (is_yang_sheng, left_ying_idx, note)：是否阳胜柱，左侧最近阴柱索引，备注
        """
        base_v = volume[base_idx] if base_idx < len(volume) else None
        base_c = close[base_idx] if base_idx < len(close) else None

        # 步骤1：向左查找最近阴柱（C[day] < O[day]）
        left_ying_idx = None
        for i in range(base_idx - 1, -1, -1):
            c_i = close[i] if i < len(close) else None
            o_i = open_[i] if i < len(open_) else None
            # 阴柱定义：收盘价 < 开盘价（严格小于）
            if c_i is not None and o_i is not None and c_i < o_i:
                left_ying_idx = i
                break

        # 步骤2：若找不到 left_ying
        if left_ying_idx is None:
            return False, None, "无左侧阴柱（上市以来未出现C<O的阴线），阳胜柱前置条件不满足"

        # 步骤3：严格判断阳胜柱条件
        left_ying_c = close[left_ying_idx] if left_ying_idx < len(close) else None
        left_ying_v = volume[left_ying_idx] if left_ying_idx < len(volume) else None

        if base_c is None or base_v is None or left_ying_c is None or left_ying_v is None:
            return False, left_ying_idx, "数据缺失，阳胜柱条件无法判定"

        # 严格大于（addendum_v2："胜过"为严格大于，不是大于等于）
        price_win = base_c > left_ying_c
        volume_win = base_v > left_ying_v

        if not price_win and not volume_win:
            return False, left_ying_idx, f"价柱未胜（C[t]={base_c} <= C[left_ying]={left_ying_c}）且量柱未胜（V[t]={base_v} <= V[left_ying]={left_ying_v}）"
        elif not price_win:
            return False, left_ying_idx, f"价柱未胜（C[t]={base_c} <= C[left_ying]={left_ying_c}）"
        elif not volume_win:
            return False, left_ying_idx, f"量柱未胜（V[t]={base_v} <= V[left_ying]={left_ying_v}）"

        return True, left_ying_idx, None

    def _get_nature(self, position: str) -> str:
        """黄金柱位置-性质映射"""
        if position == "low":
            return "主力高度控盘/拉升支撑信号（原著：黄金柱是牛股与黑马的温度计）"
        elif position == "high":
            return "高位出货/诱多信号（高位黄金柱需防主力对倒制造假象）"
        elif position == "mid":
            return "中性/换手性质（原著未明确定义，为整理者分析，非权威来源）"
        return "无法判定性质"

    def _build_result(
        self, base_idx: int = -1, confirm_idx: int = -1,
        base_date: Optional[str] = None, confirm_date: Optional[str] = None,
        is_signal: bool = False, base_pillar_type: Optional[str] = None,
        strength: str = "none",
        base_v: Optional[float] = None, base_c: Optional[float] = None,
        base_o: Optional[float] = None, base_real_top: Optional[float] = None,
        day1_v: Optional[float] = None, day1_c: Optional[float] = None,
        day2_v: Optional[float] = None, day2_c: Optional[float] = None,
        day3_v: Optional[float] = None, day3_c: Optional[float] = None,
        avg_close_after: Optional[float] = None, min_low_after: Optional[float] = None,
        close_avg_hold: bool = False, volume_not_exceed: bool = False,
        hold_real_top: bool = False, strong_version: bool = False,
        yang_sheng_ok: bool = True, left_ying_idx: Optional[int] = None,
        data_quality: str = "valid", position_result: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        position = position_result.get("position", "unknown") if position_result else "unknown"
        nature = self._get_nature(position)

        result: Dict[str, Any] = {
            "signal_id": self.signal_id,
            "signal_name": self.signal_name,
            "base_pillar_date": base_date,
            "confirmation_date": confirm_date,
            "is_signal": is_signal,
            "strength": strength,
            "base_pillar_type": base_pillar_type,
            "values": {
                "base_v": base_v,
                "base_c": base_c,
                "base_o": base_o,
                "base_real_top": base_real_top,
                "day1_v": day1_v,
                "day1_c": day1_c,
                "day2_v": day2_v,
                "day2_c": day2_c,
                "day3_v": day3_v,
                "day3_c": day3_c,
                "avg_close_after": avg_close_after,
                "min_low_after": min_low_after,
                "close_avg_hold": close_avg_hold,
                "volume_not_exceed": volume_not_exceed,
                "hold_real_top": hold_real_top,
                "strong_version": strong_version,
            },
            "golden_line_price": base_real_top,
            "data_quality": data_quality,
            "yang_sheng_ok": yang_sheng_ok,
            "position": position,
            "nature": nature,
            "position_detail": position_result,
        }
        if note:
            result["note"] = note
        return result
