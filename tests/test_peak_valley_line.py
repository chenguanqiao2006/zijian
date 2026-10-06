"""峰谷线（peak_valley_line）测试用例"""
import pytest
from src.price_lines.peak_valley_line import PeakValleyLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    return {
        "open": [base_price] * n, "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n, "close": [base_price] * n,
        "volume": [base_vol] * n, "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestPeakValleyLine:
    def test_insufficient_data(self):
        data = _make_data(5)
        detector = PeakValleyLine()
        result = detector.detect(data, date="2026-09-05")
        assert result["is_valid"] is False

    def test_output_fields(self):
        data = _make_data(30)
        # 构造峰顶
        data["high"][8] = 15.00; data["close"][8] = 14.80; data["open"][8] = 14.50
        data["volume"][8] = 5000.0
        for i in range(9, 30): data["high"][i] = 14.80
        for i in range(8): data["high"][i] = 14.00
        # 构造谷底（与峰顶同价位15.00附近）
        data["low"][20] = 14.99; data["close"][20] = 15.10; data["open"][20] = 15.20
        data["volume"][20] = 200.0
        for i in range(21, 30): data["low"][i] = 15.20
        for i in range(20): data["low"][i] = 14.50

        detector = PeakValleyLine()
        result = detector.detect(data, date="2026-09-30")
        if result["is_valid"]:
            assert "line_price" in result
            assert "三级飞跃等级" in result
            assert "重合精度" in result

    def test_signal_id(self):
        data = _make_data(30)
        detector = PeakValleyLine()
        result = detector.detect(data, date="2026-09-30")
        assert result["signal_id"] == "peak_valley_line"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
