"""平量柱信号测试 - 规格卡4

测试用例对齐 spec_batch1_basic_volume.md 规格卡4 第8节
"""

import pytest
from src.signals.flat_volume import FlatVolumeSignal


@pytest.fixture
def signal():
    return FlatVolumeSignal()


def _make_data(volumes, closes=None, highs=None, lows=None, dates=None):
    n = len(volumes)
    return {
        "volume": volumes,
        "close": closes if closes else [10.0] * n,
        "high": highs if highs else [10.5] * n,
        "low": lows if lows else [9.5] * n,
        "dates": dates if dates else [f"2026-01-{i+1:02d}" for i in range(n)],
    }


class TestFlatVolumeStandard:
    """标准平量柱判定"""

    def test_standard_2_flat_hit(self, signal):
        """测试用例1：标准2根平量命中"""
        volumes = [5000, 5050, 4980]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["values"]["consecutive_count"] >= 2
        assert result["values"]["ratio_t_t1"] == pytest.approx(0.986, abs=0.01)

    def test_only_1_flat_not_hit(self, signal):
        """测试用例2：仅1根平量，不命中"""
        volumes = [8000, 5000, 5050]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert "仅1根平量" in (result.get("note") or "")

    def test_exceed_5pct_not_hit(self, signal):
        """测试用例3：超出5%误差，不命中"""
        volumes = [5000, 5050, 5400]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["values"]["ratio_t_t1"] == pytest.approx(1.069, abs=0.01)

    def test_exact_boundary_0_95(self, signal):
        """恰好0.95下限命中"""
        volumes = [5000, 4750, 4512.5]  # 4750/5000=0.95, 4512.5/4750=0.95
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is True


class TestFlatVolumeBoundary:
    """边界情况"""

    def test_new_stock_first_day(self, signal):
        """新股上市首日不判定"""
        data = _make_data([5000], dates=["2026-01-01"])
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "new_stock_first_day"

    def test_insufficient_data(self, signal):
        """上市不足3日不判定"""
        volumes = [5000, 5050]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "insufficient_data"

    def test_suspended_in_sequence(self, signal):
        """平量序列中存在停牌日不判定"""
        volumes = [5000, 0, 4980]
        data = _make_data(volumes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "suspended_in_sequence"

    def test_position_and_nature_fields(self, signal):
        """输出包含position和nature字段"""
        volumes = [5000, 5050, 4980]
        closes = [10.0] * 3
        highs = [20.0] * 3
        lows = [5.0] * 3
        data = _make_data(volumes, closes, highs, lows)
        result = signal.detect(data)
        assert "position" in result
        assert "nature" in result
