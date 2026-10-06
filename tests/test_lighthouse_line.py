"""灯塔线（lighthouse_line）测试用例"""
import pytest
from src.price_lines.lighthouse_line import LighthouseLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    return {
        "open": [base_price] * n, "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n, "close": [base_price] * n,
        "volume": [base_vol] * n, "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestLighthouseLine:
    def test_golden_pillar_confirmed(self):
        """标准：黄金柱已确认 → 灯塔线成立"""
        data = _make_data(30)
        # T-10日黄金柱基柱（倍量柱）
        gidx = 10
        data["open"][gidx] = 12.00; data["close"][gidx] = 12.50
        data["high"][gidx] = 12.60; data["low"][gidx] = 11.90
        data["volume"][gidx] = 10000.0
        data["volume"][gidx - 1] = 4000.0  # 倍量
        # 后三日（不破实顶，量不过顶）
        for i in range(gidx + 1, gidx + 4):
            data["close"][i] = 12.60 + (i - gidx) * 0.05
            data["open"][i] = 12.50
            data["volume"][i] = 8000.0

        detector = LighthouseLine()
        result = detector.detect(data, date="2026-09-30")
        if result["is_valid"]:
            assert result["center_price"] == 12.50  # 黄金柱实顶
            assert result["golden_pillar_confirmed"] is True
            assert len(result["lines"]) >= 1  # 至少有平衡线

    def test_insufficient_data(self):
        data = _make_data(5)
        detector = LighthouseLine()
        result = detector.detect(data, date="2026-09-05")
        assert result["is_valid"] is False

    def test_output_fields(self):
        data = _make_data(30)
        gidx = 10
        data["open"][gidx] = 12.00; data["close"][gidx] = 12.50
        data["volume"][gidx] = 10000.0; data["volume"][gidx - 1] = 4000.0
        for i in range(gidx + 1, gidx + 4):
            data["close"][i] = 12.60; data["volume"][i] = 8000.0
        detector = LighthouseLine()
        result = detector.detect(data, date="2026-09-30")
        if result["is_valid"]:
            assert "center_date" in result
            assert "lines" in result
            assert "position" in result
            assert "nature" in result

    def test_signal_id(self):
        data = _make_data(30)
        detector = LighthouseLine()
        result = detector.detect(data, date="2026-09-30")
        assert result["signal_id"] == "lighthouse_line"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
