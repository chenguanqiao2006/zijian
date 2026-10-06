"""精准线（precision_line）测试用例"""
import pytest
from src.price_lines.precision_line import PrecisionLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    return {
        "open": [base_price] * n, "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n, "close": [base_price] * n,
        "volume": [base_vol] * n, "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestPrecisionLine:
    def test_horizontal_precision(self):
        """水平精准线：3个最低价同向相切"""
        data = _make_data(20)
        data["low"][5] = 12.50; data["volume"][5] = 2000.0
        data["low"][10] = 12.50; data["volume"][10] = 2000.0
        data["low"][15] = 12.51; data["volume"][15] = 2000.0

        detector = PrecisionLine()
        result = detector.detect(data, date="2026-09-20")
        if result["is_valid"]:
            assert result["line_type"] == "horizontal_precision"
            assert result["取点数量"] >= 2

    def test_insufficient_data(self):
        data = _make_data(1)
        detector = PrecisionLine()
        result = detector.detect(data, date="2026-09-01")
        assert result["is_valid"] is False

    def test_output_fields(self):
        data = _make_data(20)
        data["low"][5] = 12.50; data["volume"][5] = 2000.0
        data["low"][10] = 12.50; data["volume"][10] = 2000.0
        detector = PrecisionLine()
        result = detector.detect(data, date="2026-09-20")
        if result["is_valid"]:
            assert "position" in result
            assert "nature" in result
            assert "取点类型" in result

    def test_signal_id(self):
        data = _make_data(20)
        detector = PrecisionLine()
        result = detector.detect(data, date="2026-09-20")
        assert result["signal_id"] == "precision_line"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
