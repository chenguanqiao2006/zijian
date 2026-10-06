"""元帅柱信号测试 - 批次2规格卡2

测试用例对齐 spec_batch2_ace_pillar.md 规格卡2 第8节
边界测试对齐 spec_batch2_ace_pillar.md 规格卡2 第5节
"""

import pytest
from src.signals.marshal_volume import MarshalVolumeSignal


@pytest.fixture
def signal():
    return MarshalVolumeSignal()


def _build_marshal_data(
    hist_v, hist_c, hist_o, hist_h,
    t1_v, t1_c, t1_o, t1_h,
    t_v, t_c, t_o, t_l,
    day1_v, day1_c, day1_l,
    day2_v, day2_c, day2_l,
    day3_v, day3_c, day3_l,
    hhv_250=20.00, llv_250=14.00,
):
    """构造元帅柱测试数据

    数据顺序：历史数据 → T-1日（授衔日）→ T日（跳空日）→ T+1 → T+2 → T+3（确认日）
    """
    volumes = list(hist_v)
    closes = list(hist_c)
    opens = list(hist_o)
    highs = list(hist_h)
    lows = [o - 0.2 for o in hist_o]
    # 确保位置判定窗口内包含 hhv_250 和 llv_250
    if highs:
        highs[0] = hhv_250
    if lows:
        lows[0] = llv_250

    # T-1日（元帅柱候选授衔日）
    volumes.append(t1_v)
    closes.append(t1_c)
    opens.append(t1_o)
    highs.append(t1_h)
    lows.append(t1_o - 0.1)

    # T日（跳空日，基柱日）
    volumes.append(t_v)
    closes.append(t_c)
    opens.append(t_o)
    highs.append(t_c + 0.1)
    lows.append(t_l)

    # T+1日
    volumes.append(day1_v)
    closes.append(day1_c)
    opens.append(day1_c * 0.99)
    highs.append(day1_c * 1.01)
    lows.append(day1_l)

    # T+2日
    volumes.append(day2_v)
    closes.append(day2_c)
    opens.append(day2_c * 0.99)
    highs.append(day2_c * 1.01)
    lows.append(day2_l)

    # T+3日（确认日）
    volumes.append(day3_v)
    closes.append(day3_c)
    opens.append(day3_c * 0.99)
    highs.append(day3_c * 1.01)
    lows.append(day3_l)

    n = len(volumes)
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]

    # 构造250日高低点用于位置判定
    for i in range(250 - n):
        volumes.append(5000)
        closes.append((hhv_250 + llv_250) / 2)
        opens.append((hhv_250 + llv_250) / 2 - 0.1)
        highs.append(hhv_250)
        lows.append(llv_250)
        dates.append(f"2026-02-{i+1:02d}")

    return {
        "volume": volumes, "close": closes, "open": opens,
        "high": highs, "low": lows, "dates": dates,
    }


def _make_standard_history():
    """构造标准历史数据：20天，第5天为阴线（用于阳胜柱判定）"""
    hist_v = [8000, 8100, 8200, 8300, 6000, 8500, 8600, 8700, 8800, 8900,
              9000, 9100, 9200, 9300, 9400, 9500, 9600, 9700, 9800, 9900]
    hist_c = [14.00, 14.05, 14.10, 14.15, 13.80, 14.25, 14.30, 14.35, 14.40, 14.45,
              14.50, 14.55, 14.60, 14.65, 14.70, 14.75, 14.80, 14.85, 14.90, 14.95]
    hist_o = [13.90, 13.95, 14.00, 14.05, 14.20, 14.15, 14.20, 14.25, 14.30, 14.35,
              14.40, 14.45, 14.50, 14.55, 14.60, 14.65, 14.70, 14.75, 14.80, 14.85]
    hist_h = [14.10, 14.15, 14.20, 14.25, 14.30, 14.35, 14.40, 14.45, 14.50, 14.55,
              14.60, 14.65, 14.70, 14.75, 14.80, 14.85, 14.90, 14.95, 15.00, 15.05]
    return hist_v, hist_c, hist_o, hist_h


class TestMarshalVolumeStandard:
    """标准元帅柱判定"""

    def test_case1_standard_hit_general_path(self, signal):
        """测试用例1：标准元帅柱命中（跳空+将军柱确认路径，干净场景）"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=7500, day2_c=15.50, day2_l=15.42,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
            hhv_250=20.00, llv_250=14.00,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is True
        assert result["ace_pillar_type"] == "general_volume"
        assert result["values"]["gap_up"] is True
        assert result["values"]["gap_not_filled"] is True
        assert result["position"] == "mid"
        assert "趋势加速信号" in result["nature"]

    def test_case2_no_gap_flat_open(self, signal):
        """测试用例2：平开无缺口（L[t]==H[t-1]），不命中"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.20, t_o=15.00, t_l=15.00,
            day1_v=9000, day1_c=15.10, day1_l=14.95,
            day2_v=7500, day2_c=15.00, day2_l=14.92,
            day3_v=6000, day3_c=15.05, day3_l=14.98,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is False
        assert result["values"]["gap_up"] is False
        assert "平开无缺口" in (result.get("note") or "")

    def test_case3_gap_but_no_ace_pillar(self, signal):
        """测试用例3：跳空但基柱后三日未形成王牌柱，不命中"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=14.60, day1_l=14.50,
            day2_v=13000, day2_c=14.80, day2_l=14.70,
            day3_v=6000, day3_c=14.70, day3_l=14.60,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is False
        assert result["values"]["gap_up"] is True
        assert result["ace_pillar_type"] is None
        assert "未形成王牌柱" in (result.get("note") or "")

    def test_case4_high_position_gap(self, signal):
        """测试用例4：高位跳空（position=high），验证nature映射到'跳空补空警示'"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=17.80, t1_o=17.50, t1_h=18.00,
            t_v=12000, t_c=18.50, t_o=18.40, t_l=18.60,
            day1_v=9000, day1_c=18.45, day1_l=18.45,
            day2_v=7500, day2_c=18.42, day2_l=18.42,
            day3_v=6000, day3_c=18.48, day3_l=18.48,
            hhv_250=20.00, llv_250=14.00,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is True
        assert result["ace_pillar_type"] == "general_volume"
        assert result["position"] == "high"
        assert "跳空补空警示" in result["nature"]


class TestMarshalVolumeBoundary:
    """边界情况 - 对齐 spec_batch2_ace_pillar.md 规格卡2 第5节"""

    def test_position_and_nature_fields(self, signal):
        """输出包含position和nature字段"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=7500, day2_c=15.50, day2_l=15.42,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
        )
        result = signal.detect(data, date="2026-01-25")
        assert "position" in result
        assert "nature" in result
        assert "zero_zone_top" in result
        assert "marshal_date" in result
        assert "gap_date" in result
        assert "confirmation_date" in result

    def test_json_keys_snake_case(self, signal):
        """所有JSON key为英文snake_case"""
        import re
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=7500, day2_c=15.50, day2_l=15.42,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
        )
        result = signal.detect(data, date="2026-01-25")

        def check_keys(obj, path=""):
            if isinstance(obj, dict):
                for k in obj:
                    assert re.match(r'^[a-z][a-z0-9_]*$', k), f"Non-snake_case key: {path}.{k}"
                    check_keys(obj[k], f"{path}.{k}")

        check_keys(result)

    def test_boundary_marshal_day_suspended(self, signal):
        """边界1：授衔日（T-1日）停牌（V=0），不判定。
        规格卡要求'跳空判定需跳空前一日为有效交易日'。
        """
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        # T-1日（授衔日）V=0（停牌），但H=15.00正常
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=0, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=7500, day2_c=15.50, day2_l=15.42,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is False
        assert result["data_quality"] == "marshal_day_suspended"
        assert "授衔日停牌" in (result.get("note") or "")

    def test_boundary_new_stock(self, signal):
        """边界2：新股上市（gap_idx<9，历史数据不足10日），不判定"""
        # 构造12日数据：历史7日 + T-1日(7) + T日(8) + T+1(9) + T+2(10) + T+3(11)
        # gap_idx=8<9
        volumes = [5000, 5100, 5200, 5300, 4000, 5500, 5600, 6000, 12000, 9000, 7500, 6000]
        closes = [14.00, 14.05, 14.10, 14.15, 13.80, 14.25, 14.30, 14.50, 15.80, 15.60, 15.50, 15.55]
        opens = [13.90, 13.95, 14.00, 14.05, 14.20, 14.15, 14.20, 14.20, 15.40, 15.45, 15.40, 15.45]
        highs = [14.10, 14.15, 14.20, 14.25, 14.30, 14.35, 14.40, 15.00, 15.90, 15.70, 15.60, 15.65]
        lows = [13.70, 13.75, 13.80, 13.85, 13.60, 13.95, 14.00, 14.10, 15.60, 15.45, 15.42, 15.48]
        dates = [f"2026-01-{i+1:02d}" for i in range(12)]
        data = {"volume": volumes, "close": closes, "open": opens, "high": highs, "low": lows, "dates": dates}
        result = signal.detect(data, date="2026-01-12")
        assert result["is_signal"] is False
        assert result["data_quality"] == "new_stock"
        assert "新股上市" in (result.get("note") or "")

    def test_boundary_invalid_data(self, signal):
        """边界3：数据异常（跳空日L为负数），判定失效"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=-1,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=7500, day2_c=15.50, day2_l=15.42,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is False
        assert result["data_quality"] == "invalid_data"
        assert "数据异常" in (result.get("note") or "")

    def test_boundary_gap_too_small(self, signal):
        """边界4：跳空幅度过小（<1%），标注'疑似跳空'"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        # T-1日 H=15.00，T日 L=15.05，跳空幅度=0.33%<1%
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.20, t_o=15.00, t_l=15.05,
            day1_v=9000, day1_c=15.10, day1_l=15.05,
            day2_v=7500, day2_c=15.05, day2_l=15.02,
            day3_v=6000, day3_c=15.10, day3_l=15.05,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is True
        assert result["values"]["gap_pct"] is not None
        assert result["values"]["gap_pct"] < 1.0
        assert "疑似跳空" in (result.get("note") or "")

    def test_boundary_gap_too_high(self, signal):
        """边界5：跳空幅度过大（>5%），标注需人工复核（'跳得太高没有意义'）"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        # T-1日 H=15.00，T日 L=16.00，跳空幅度=6.67%>5%
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=16.20, t_o=15.80, t_l=16.00,
            day1_v=9000, day1_c=16.00, day1_l=15.90,
            day2_v=7500, day2_c=15.90, day2_l=15.85,
            day3_v=6000, day3_c=15.95, day3_l=15.90,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is True
        assert result["values"]["gap_pct"] is not None
        assert result["values"]["gap_pct"] > 5.0
        assert "跳得太高没有意义" in (result.get("note") or "")

    def test_boundary_gap_filled(self, signal):
        """边界6：跳空缺口后三日内回补，授衔仍可成立但标注'缺口已回补'"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        # 标准跳空场景，但T+2日 L=14.95 <= H[t-1]=15.00（缺口回补）
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=7500, day2_c=15.50, day2_l=14.95,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is True
        assert result["values"]["gap_not_filled"] is False
        assert "缺口后三日内已回补" in (result.get("note") or "")

    def test_boundary_extreme_shrink(self, signal):
        """边界7：后三日中存在极端缩量（V < V[t] × 0.1），标注需人工复核"""
        hist_v, hist_c, hist_o, hist_h = _make_standard_history()
        # T+2日 V=500 < 12000×0.1=1200（极端缩量）
        data = _build_marshal_data(
            hist_v, hist_c, hist_o, hist_h,
            t1_v=6000, t1_c=14.50, t1_o=14.20, t1_h=15.00,
            t_v=12000, t_c=15.80, t_o=15.40, t_l=15.60,
            day1_v=9000, day1_c=15.60, day1_l=15.45,
            day2_v=500, day2_c=15.50, day2_l=15.42,
            day3_v=6000, day3_c=15.55, day3_l=15.48,
        )
        result = signal.detect(data, date="2026-01-25")
        assert result["is_signal"] is True
        assert result.get("extreme_shrink") is True
        assert result.get("needs_human_review") is True
        assert "极端缩量" in (result.get("note") or "")

    def test_boundary_position_unknown(self, signal):
        """边界8：位置判定失败（数据不足20日），position='unknown'"""
        # 构造15日数据：历史10日 + T-1日 + T日 + T+1 + T+2 + T+3 = 15日
        # gap_idx=11>=9（元帅柱可判定），但位置判定需20日，不足20日返回unknown
        volumes = [5000, 5100, 5200, 5300, 4000, 5500, 5600, 5700, 5800, 5900, 6000, 12000, 9000, 7500, 6000]
        closes = [14.00, 14.05, 14.10, 14.15, 13.80, 14.25, 14.30, 14.35, 14.40, 14.45, 14.50, 15.80, 15.60, 15.50, 15.55]
        opens = [13.90, 13.95, 14.00, 14.05, 14.20, 14.15, 14.20, 14.25, 14.30, 14.35, 14.20, 15.40, 15.45, 15.40, 15.45]
        highs = [14.10, 14.15, 14.20, 14.25, 14.30, 14.35, 14.40, 14.45, 14.50, 14.55, 15.00, 15.90, 15.70, 15.60, 15.65]
        lows = [13.70, 13.75, 13.80, 13.85, 13.60, 13.95, 14.00, 14.05, 14.10, 14.15, 14.10, 15.60, 15.45, 15.42, 15.48]
        dates = [f"2026-01-{i+1:02d}" for i in range(15)]
        data = {"volume": volumes, "close": closes, "open": opens, "high": highs, "low": lows, "dates": dates}
        result = signal.detect(data, date="2026-01-15")
        assert result["position"] == "unknown"
        assert result["nature"] == "无法判定性质"
