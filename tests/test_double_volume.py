"""倍量柱信号测试 - 规格卡3

测试用例对齐 spec_batch1_basic_volume.md 规格卡3 第8节
"""

import pytest
from src.signals.double_volume import DoubleVolumeSignal


@pytest.fixture
def signal():
    return DoubleVolumeSignal()


def _make_data(volumes, closes, highs=None, lows=None, dates=None):
    n = len(volumes)
    return {
        "volume": volumes,
        "close": closes,
        "high": highs if highs else [c * 1.05 for c in closes],
        "low": lows if lows else [c * 0.95 for c in closes],
        "dates": dates if dates else [f"2026-01-{i+1:02d}" for i in range(n)],
    }


class TestDoubleVolumeStandard:
    """标准倍量柱判定"""

    def test_standard_hit(self, signal):
        """测试用例1：标准倍量柱命中"""
        volumes = [5000, 10000]
        closes = [10.00, 10.50]
        data = _make_data(volumes, closes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["values"]["volume_ratio"] == 2.0
        assert result["values"]["c_t"] == 10.50
        assert result["values"]["c_t_1"] == 10.00
def test_volume_ok_but_price_not_ok(self, signal):
        """测试用例2：量能达标但价格不达标（放量下跌）"""
        volumes = [5000, 10000]
        closes = [10.00, 9.80]
        data = _make_data(volumes, closes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert "放量下跌" in (result.get("note") or "")

    def test_volume_not_ok(self, signal):
        """测试用例3：量能不达标（1.8倍<1.9倍）"""
        volumes = [5000, 9000]
        closes = [10.00, 10.50]
        data = _make_data(volumes, closes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["values"]["volume_ratio"] == 1.8

    def test_exact_threshold_1_9(self, signal):
        """恰好1.9倍阈值命中"""
        volumes = [5000, 9500]
        closes = [10.00, 10.50]
        data = _make_data(volumes, closes)
        result = signal.detect(data)
        assert result["is_signal"] is True
        assert result["values"]["volume_ratio"] == 1.9


class TestDoubleVolumeBoundary:
"""边界情况"""

    def test_new_stock_first_day(self, signal):
        """新股上市首日不判定"""
        data = _make_data([5000], [10.00], dates=["2026-01-01"])
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "new_stock_first_day"

    def test_suspended_prev_day(self, signal):
        """V[t-1]==0（停牌后首日）不判定"""
        volumes = [0, 10000]
        closes = [10.00, 10.50]
        data = _make_data(volumes, closes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "suspended_prev_day"

    def test_invalid_volume(self, signal):
        """数据异常不判定"""
        volumes = [5000, -1]
        closes = [10.00, 10.50]
        data = _make_data(volumes, closes)
        result = signal.detect(data)
        assert result["is_signal"] is False
        assert result["data_quality"] == "invalid_data"

    def test_position_and_nature_fields(self, signal):
        """输出包含position和nature字段"""
        volumes = [5000, 10000]
        closes = [10.00, 10.50]
        highs = [20.00, 20.50]
        lows = [5.00, 5.50]
        data = _make_data(volumes, closes, highs, lows)
        result = signal.detect(data)
        assert "position" in result
        assert "nature" in result