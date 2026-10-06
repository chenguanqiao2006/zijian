"""通道线（channel_line）测试用例"""
import pytest
from src.price_lines.channel_line import ChannelLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    return {
        "open": [base_price] * n, "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n, "close": [base_price] * n,
        "volume": [base_vol] * n, "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestChannelLine:
    def test_upward_channel(self):
        """上升通道：两个真底确定下轨"""
        data = _make_data(30)
        # 第一个真底
        data["low"][8] = 10.00; data["close"][8] = 10.20; data["open"][8] = 10.50
        data["volume"][8] = 200.0
        for i in range(9, 30): data["low"][i] = 10.50
        for i in range(8): data["low"][i] = 11.00
        # 第二个真底（低点抬高）
        data["low"][20] = 11.00; data["close"][20] = 11.20; data["open"][20] = 11.50
        data["volume"][20] = 250.0
        for i in range(21, 30): data["low"][i] = 11.50

        detector = ChannelLine()
        result = detector.detect(data, date="2026-09-30")
        if result["is_valid"]:
            assert result["channel_type"] == "upward"
            assert result["slope"] > 0  # 上升通道斜率为正
            assert "channel_width" in result

    def test_insufficient_data(self):
        data = _make_data(5)
        detector = ChannelLine()
        result = detector.detect(data, date="2026-09-05")
        assert result["is_valid"] is False

    def test_output_fields(self):
        data = _make_data(30)
        data["low"][8] = 10.00; data["volume"][8] = 200.0
        for i in range(9, 30): data["low"][i] = 10.50
        for i in range(8): data["low"][i] = 11.00
        data["low"][20] = 11.00; data["volume"][20] = 250.0
        for i in range(21, 30): data["low"][i] = 11.50
        detector = ChannelLine()
        result = detector.detect(data, date="2026-09-30")
        if result["is_valid"]:
            assert "lower_intercept" in result
            assert "upper_intercept" in result
            assert "mid_intercept" in result
            assert "position" in result
            assert "nature" in result

    def test_signal_id(self):
        data = _make_data(30)
        detector = ChannelLine()
        result = detector.detect(data, date="2026-09-30")
        assert result["signal_id"] == "channel_line"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
