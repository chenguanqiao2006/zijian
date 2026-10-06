"""梯量柱信号测试 - 规格卡6

测试用例对齐 spec_batch1_basic_volume.md 规格卡6 第8节
"""

import pytest
from src.signals.ladder_volume import LadderVolumeSignal


@pytest.fixture
def signal():
    return LadderVolumeSignal()


def _make_data(volumes, closes=None, highs=None, lows=None, dates=None):
    n = len(volumes)
    return {
        "volume": volumes,
        "close": closes if closes else [10.0] * n,
        "high": highs if highs else [10.5] * n,
        "low": lows if lows else [9.5] * n,
        "dates": dates if dates else [f"2026-01-{i+1:02d}" for i in range(n)],
    }


class TestLadderVolumeStandard:
    """标准梯量柱判定"""

    def test_standard_3_ladder_hit(self, signal):
        """测试用例1：标准3根梯量命中"""
        volumes = [3000, 4000, 5500]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["values"]["consecutive_count"] >= 3

    def test_only_2_increase_not_hit(self, signal):
        """测试用例2：仅2根递增，不命中"""
        volumes = [5500, 4000, 5000]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert "仅2根递增" in (result.get("note") or "")

    def test_middle_equal_not_hit(self, signal):
        """测试用例3：中间持平，不命中（严格递增）"""
        volumes = [3000, 4000, 4000]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False

    def test_super_long_ladder_warning(self, signal):
        """超长梯量（超过5根）标注变盘预警"""
        volumes = [1000, 2000, 3000, 4000, 5000, 6000]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["values"]["consecutive_count"] >= 5
        assert "超长梯量" in (result.get("note") or "")


class TestLadderVolumeBoundary:
    """边界情况"""

    def test_new_stock_first_day(self, signal):
        """新股上市首日不判定"""
        data = _make_data([5000], dates=["2026-01-01"])
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "new_stock_first_day"

    def test_insufficient_data(self, signal):
        """上市不足3日不判定"""
        volumes = [5000, 6000]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "insufficient_data"

    def test_suspended_in_sequence(self, signal):
        """梯量序列中存在停牌日不判定"""
        volumes = [3000, 0, 5500]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "suspended_in_sequence"

    def test_position_and_nature_fields(self, signal):
        """输出包含position和nature字段"""
        volumes = [3000, 4000, 5500]
        closes = [10.0] * 3
        highs = [20.0] * 3
        lows = [5.0] * 3
        data = _make_data(volumes, closes, highs, lows)
        result = signal.detect(data)
        assert "position" in result
        assert "nature" in result
