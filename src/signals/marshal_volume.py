"""元帅柱信号卡 - 批次2规格卡2

规格来源：spec_batch2_ace_pillar.md 规格卡2（元帅柱）
全局规则：spec_global_rules.md（position/nature 字段）
原著：《伏击涨停》（修订升级版）第8章"伏击涨停的王牌——涨停起搏器"第六节"元帅柱的三个标准"
零未来函数：元帅柱为滞后确认信号，确认日为跳空当日基柱后第三日收盘后（T+3日）。
授衔日为跳空前一日（T-1日）。

判定条件：
  gap_up[t] = (L[t] > H[t-1])  -- 向上跳空缺口（严格大于）
  ace_pillar[t] = general_volume[t] OR golden_volume[t]  -- 跳空当日基柱后三日形成王牌柱
  marshal_volume[t-1] = gap_up[t] AND ace_pillar[t]  -- 授衔条件
  gap_not_filled = (L[t+1] > H[t-1]) AND (L[t+2] > H[t-1]) AND (L[t+3] > H[t-1])  -- 缺口未回补（强化）

位置-性质映射【原著未明确，为整理者分析，非权威来源】：
  低位：行情起点信号
  中位：趋势加速信号
  高位：跳空补空警示
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseSignal
from .general_volume import GeneralVolumeSignal
from .golden_volume import GoldenVolumeSignal
from ..utils.data_loader import DataLoader


class MarshalVolumeSignal(BaseSignal):
    """元帅柱信号检测引擎"""

    signal_id = "marshal_volume"
    signal_name = "元帅柱"

    EXTREME_SHRINK_RATIO = 0.1
    GAP_SUSPICIOUS_PCT = 1.0  # 跳空幅度<1%标注疑似跳空
    GAP_TOO_HIGH_PCT = 5.0  # 跳空幅度>5%需人工复核

    def __init__(self):
        super().__init__()
        self._general_signal = GeneralVolumeSignal()
        self._golden_signal = GoldenVolumeSignal()

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """检测元帅柱信号

        元帅柱为滞后确认信号，date参数指定的是确认日（T+3日），
        信号会自动向前追溯：确认日T+3 → 基柱日T（跳空日）→ 授衔日T-1。

        Args:
            data: 行情数据，须包含 volume/close/open/high/low 列表
            date: 确认日期（T+3日），默认为最后一日

        Returns:
            元帅柱判定结果JSON
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

        # 跳空日索引（T日 = 确认日 - 3）
        gap_idx = confirm_idx - 3
        # 授衔日索引（T-1日 = 跳空日 - 1）
        marshal_idx = gap_idx - 1

        confirm_date = dates[confirm_idx] if (dates and confirm_idx < len(dates)) else None
        gap_date = dates[gap_idx] if (dates and 0 <= gap_idx < len(dates)) else None
        marshal_date = dates[marshal_idx] if (dates and 0 <= marshal_idx < len(dates)) else None

        # 边界1：数据不足（需至少5个有效交易日：T-1日至T+3日）
        if marshal_idx < 0:
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                data_quality="insufficient_data",
                position_result=self._compute_position(data, gap_date),
                note="数据不足：确认日前推4日无有效授衔日，元帅柱需至少5个连续有效交易日",
            )

        # 边界2：新股上市（需至少10个有效交易日历史数据）
        if gap_idx < 9:
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                data_quality="new_stock",
                position_result=self._compute_position(data, gap_date),
                note="新股上市不足10个有效交易日，不判定元帅柱",
            )

        # 提取跳空日数据（T日）
        gap_l = low[gap_idx] if gap_idx < len(low) else None
        gap_o = open_[gap_idx] if gap_idx < len(open_) else None
        gap_c = close[gap_idx] if gap_idx < len(close) else None
        gap_v = volume[gap_idx] if gap_idx < len(volume) else None

        # 提取跳空前一日数据（T-1日，元帅柱候选日）
        prev_h = high[marshal_idx] if marshal_idx < len(high) else None
        prev_v = volume[marshal_idx] if marshal_idx < len(volume) else None
        prev_c = close[marshal_idx] if marshal_idx < len(close) else None
        prev_o = open_[marshal_idx] if marshal_idx < len(open_) else None

        # 提取后三日最低价（用于缺口回补核查）
        day1_l = low[gap_idx + 1] if gap_idx + 1 < len(low) else None
        day2_l = low[gap_idx + 2] if gap_idx + 2 < len(low) else None
        day3_l = low[gap_idx + 3] if gap_idx + 3 < len(low) else None

        # 边界3：数据异常
        if (gap_l is None or gap_l < 0 or prev_h is None or prev_h < 0 or
                gap_v is None or gap_v < 0):
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                data_quality="invalid_data",
                position_result=self._compute_position(data, gap_date),
                note="价格或成交量数据异常（负数或空值），元帅柱判定失效",
            )

        # 边界3.5：授衔日（T-1日）停牌，跳空判定需跳空前一日为有效交易日
        if prev_v is None or prev_v <= 0:
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                gap_l=gap_l, prev_h=prev_h, gap_up=False, gap_pct=None,
                data_quality="marshal_day_suspended",
                position_result=self._compute_position(data, gap_date),
                note="授衔日停牌，跳空判定需跳空前一日为有效交易日",
            )

        # 边界4：后三日中存在停牌日
        day1_v = volume[gap_idx + 1] if gap_idx + 1 < len(volume) else None
        day2_v = volume[gap_idx + 2] if gap_idx + 2 < len(volume) else None
        day3_v = volume[gap_idx + 3] if gap_idx + 3 < len(volume) else None
        if any(DataLoader.is_suspended(v) for v in [day1_v, day2_v, day3_v]):
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                data_quality="suspended_in_validation",
                position_result=self._compute_position(data, gap_date),
                note="后三日中存在停牌日，元帅柱判定失效",
            )

        # === 判定1：跳空缺口（L[t] > H[t-1]，严格大于）===
        gap_up = gap_l > prev_h

        # 跳空幅度
        gap_pct = None
        if prev_h and prev_h > 0:
            gap_pct = round((gap_l - prev_h) / prev_h * 100, 4)

        # 边界：平开无缺口（L[t] == H[t-1]）
        if not gap_up and gap_l == prev_h:
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                gap_l=gap_l, prev_h=prev_h, gap_up=False, gap_pct=gap_pct,
                data_quality="valid",
                position_result=self._compute_position(data, gap_date),
                note="平开无缺口（L[t] == H[t-1]），跳空缺口条件不满足",
            )

        if not gap_up:
            return self._build_result(
                marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
                marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
                is_signal=False, ace_pillar_type=None,
                gap_l=gap_l, prev_h=prev_h, gap_up=False, gap_pct=gap_pct,
                data_quality="valid",
                position_result=self._compute_position(data, gap_date),
                note="无向上跳空缺口（L[t] <= H[t-1]），元帅柱条件不满足",
            )

        # === 判定2：王牌柱确认（跳空当日基柱后三日形成将军柱 OR 黄金柱）===
        # 复用将军柱和黄金柱的 detect 方法，确认日为 T+3日
        general_result = self._general_signal.detect(data, date)
        golden_result = self._golden_signal.detect(data, date)

        is_general = general_result.get("is_signal", False)
        is_golden = golden_result.get("is_signal", False)
        ace_pillar = is_general or is_golden

        if is_general:
            ace_pillar_type = "general_volume"
        elif is_golden:
            ace_pillar_type = "golden_volume"
        else:
            ace_pillar_type = None

        # === 判定3：缺口回补核查（强化，可选）===
        gap_not_filled = False
        if all(l is not None for l in [day1_l, day2_l, day3_l]) and prev_h is not None:
            gap_not_filled = (day1_l > prev_h) and (day2_l > prev_h) and (day3_l > prev_h)

        # === 总判定 ===
        is_signal = gap_up and ace_pillar

        # 极端缩量检测（后三日中）
        extreme_shrink = False
        if gap_v and gap_v > 0:
            for v in [day1_v, day2_v, day3_v]:
                if v is not None and v < gap_v * self.EXTREME_SHRINK_RATIO:
                    extreme_shrink = True
                    break

        # 跳空幅度边界标注
        gap_note_parts = []
        if gap_pct is not None and gap_pct < self.GAP_SUSPICIOUS_PCT:
            gap_note_parts.append(f"跳空幅度过小（{gap_pct}%<1%），疑似跳空，需人工复核")
        if gap_pct is not None and gap_pct > self.GAP_TOO_HIGH_PCT:
            gap_note_parts.append(f"跳空幅度过大（{gap_pct}%>5%），原著提示'跳得太高没有意义'，需人工复核")
        if not gap_not_filled and is_signal:
            gap_note_parts.append("缺口后三日内已回补，按'跳空补空'原则授衔仍可成立，但可靠性降低")

        position_result = self._compute_position(data, gap_date)

        note_parts = []
        if not ace_pillar:
            note_parts.append("跳空当日基柱后三日未形成王牌柱（将军柱/黄金柱均不成立），不授衔")
        note_parts.extend(gap_note_parts)
        if extreme_shrink and is_signal:
            note_parts.append("后三日中存在极端缩量（V < V[t] × 0.1），需人工复核")

        return self._build_result(
            marshal_idx=marshal_idx, gap_idx=gap_idx, confirm_idx=confirm_idx,
            marshal_date=marshal_date, gap_date=gap_date, confirm_date=confirm_date,
            is_signal=is_signal, ace_pillar_type=ace_pillar_type,
            gap_l=gap_l, prev_h=prev_h, gap_up=gap_up, gap_pct=gap_pct,
            day1_l=day1_l, day2_l=day2_l, day3_l=day3_l, gap_not_filled=gap_not_filled,
            marshal_v=prev_v, marshal_c=prev_c, marshal_o=prev_o,
            extreme_shrink=extreme_shrink,
            data_quality="valid",
            position_result=position_result,
            note="；".join(note_parts) if note_parts else None,
        )

    def _get_nature(self, position: str) -> str:
        """元帅柱位置-性质映射【原著未明确，为整理者分析，非权威来源】"""
        if position == "low":
            return "行情起点信号（底部第一根元帅柱为行情启动标志）（原著未明确，为整理者分析，非权威来源）"
        elif position == "high":
            return "跳空补空警示（高位跳空需防'跳得太高没有意义'，警惕诱多）（原著未明确，为整理者分析，非权威来源）"
        elif position == "mid":
            return "趋势加速信号（跳空补空中继）（原著未明确，为整理者分析，非权威来源）"
        return "无法判定性质"

    def _build_result(
        self, marshal_idx: int = -1, gap_idx: int = -1, confirm_idx: int = -1,
        marshal_date: Optional[str] = None, gap_date: Optional[str] = None,
        confirm_date: Optional[str] = None,
        is_signal: bool = False, ace_pillar_type: Optional[str] = None,
        gap_l: Optional[float] = None, prev_h: Optional[float] = None,
        gap_up: bool = False, gap_pct: Optional[float] = None,
        day1_l: Optional[float] = None, day2_l: Optional[float] = None,
        day3_l: Optional[float] = None, gap_not_filled: bool = False,
        marshal_v: Optional[float] = None, marshal_c: Optional[float] = None,
        marshal_o: Optional[float] = None, extreme_shrink: bool = False,
        data_quality: str = "valid", position_result: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        position = position_result.get("position", "unknown") if position_result else "unknown"
        nature = self._get_nature(position)

        result: Dict[str, Any] = {
            "signal_id": self.signal_id,
            "signal_name": self.signal_name,
            "marshal_date": marshal_date,
            "gap_date": gap_date,
            "confirmation_date": confirm_date,
            "is_signal": is_signal,
            "ace_pillar_type": ace_pillar_type,
            "position": position,
            "nature": nature,
            "values": {
                "gap_l_t": gap_l,
                "prev_h": prev_h,
                "gap_up": gap_up,
                "gap_pct": gap_pct,
                "day1_l": day1_l,
                "day2_l": day2_l,
                "day3_l": day3_l,
                "gap_not_filled": gap_not_filled,
                "marshal_v": marshal_v,
                "marshal_c": marshal_c,
                "marshal_o": marshal_o,
            },
            "zero_zone_top": prev_h,
            "data_quality": data_quality,
            "position_detail": position_result,
        }
        if extreme_shrink:
            result["extreme_shrink"] = True
            result["needs_human_review"] = True
        if note:
            result["note"] = note
        return result
