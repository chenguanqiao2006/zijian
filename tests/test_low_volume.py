"""低量柱信号测试 - 规格卡2

测试用例对齐 spec_batch1_basic_volume.md 规格卡2 第8节
"""

import pytest
from src.signals.low_volume import LowVolumeSignal


@pytest.fixture
def signal():
    return LowVolumeSignal()


def _make_data(volumes, closes=None, highs=None, lows=None, dates=None):
    n = len(volumes)
    return {
        "volume": volumes,
        "close": closes if closes else [10.0] * n,
        "high": highs if highs else [10.5] * n,
        "low": lows if lows else [9.5] * n,
        "dates": dates if dates else [f"2026-01-{i+1:02d}" for i in range(n)],
    }


class TestLowVolumeCriterionA:
    """标准A：V[t] == LLV(V, 10)"""

    def test_standard_a_hit(self, signal):
        """测试用例1：标准A命中"""
        volumes = [60, 55, 58, 52, 50, 53, 48, 51, 49, 45]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["match_criteria"] == "A"
        assert result["values"]["v_t"] == 45
        assert result["values"]["llv_10"] == 45
        assert result["values"]["extreme_shrink"] is False

    def test_standard_a_not_hit(self, signal):
        """标准A未命中（当日不是近10日最低）"""
        volumes = [60, 55, 58, 52, 50, 53, 48, 51, 49, 50]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["match_criteria"] == "none"


class TestLowVolumeCriterionB:
    """标准B：连续5日递减且V[t]==LLV(V,10)"""

    def test_standard_b_hit(self, signal):
        """测试用例2：标准B命中（连续5日递减）"""
        volumes = [100, 90, 80, 70, 60, 80, 70, 60, 50, 40]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert "B" in result["match_criteria"]
        assert result["values"]["shrink_days"] == 5


class TestLowVolumeExtremeShrink:
    """极端缩量边界"""

    def test_extreme_shrink_triggers_review(self, signal):
        """测试用例3：极端缩量触发人工复核"""
        volumes = [10000, 9000, 8000, 7000, 6000, 5000, 4000, 3000, 10000, 800]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["values"]["extreme_shrink"] is True
        assert result["values"]["needs_human_review"] is True
        assert "极端缩量" in (result.get("note") or "")


class TestLowVolumeBoundary:
    """边界情况"""

    def test_new_stock_first_day(self, signal):
        """新股上市首日不判定"""
        data = _make_data([50], dates=["2026-01-01"])
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "new_stock_first_day"

    def test_suspended_day_vt_zero(self, signal):
        """全天停牌（V[t]==0）不判定"""
        volumes = [60, 55, 58, 52, 50, 53, 48, 51, 49, 0]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "suspended_day"

    def test_invalid_volume(self, signal):
        """数据异常（负数）不判定"""
        volumes = [60, 55, 58, 52, 50, 53, 48, 51, 49, -1]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "invalid_volume"

    def test_position_and_nature_fields(self, signal):
        """输出包含position和nature字段"""
        volumes = [60, 55, 58, 52, 50, 53, 48, 51, 49, 45]
        closes = [10.0] * 10
        highs = [20.0] * 10
        lows = [5.0] * 10
        data = _make_data(volumes, closes, highs, lows)
        result = signal.detect(data)
        assert "position" in result
        assert "nature" in result
        assert result["position"] in ["low", "mid", "high", "unknown"]
