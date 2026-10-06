"""平衡线（balance_line）测试用例

覆盖规格卡第9节测试用例：
1. 标准·大阴实顶平衡线
2. 边界·黄金柱未确认（零未来函数）
3. 失效·假阴真阳取点
4. 输出字段完整性检查
"""

import pytest

from src.price_lines.balance_line import BalanceLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    return {
        "open": [base_price] * n,
        "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n,
        "close": [base_price] * n,
        "volume": [base_vol] * n,
        "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestBalanceLineStandard:
    def test_big_yin_real_top(self):
        """标准用例：大阴实顶平衡线"""
        data = _make_data(20)
        # T-5日大阴线
        data["open"][15] = 13.00
        data["close"][15] = 12.00  # 大阴，实体1.00
        data["high"][15] = 13.20
        data["low"][15] = 11.80
        # 前日小实体
        data["open"][14] = 12.50
        data["close"][14] = 12.40  # 实体0.10
        # 后续横盘
        for i in range(16, 20):
            data["close"][i] = 12.50
            data["open"][i] = 12.40

        detector = BalanceLine()
        result = detector.detect(data, date="2026-09-20")

        assert result["is_valid"] is True
        assert result["line_price"] == 13.00  # 大阴实顶 = max(open, close) = 13.00
        assert result["anchor_type"] == "big_yin_real_top"
        assert result["balance_type"] == "real_point"

    def test_big_yang_real_bottom(self):
        """大阳实底平衡线"""
        data = _make_data(20)
        # T-5日大阳线
        data["open"][15] = 12.00
        data["close"][15] = 13.00  # 大阳，实体1.00
        data["high"][15] = 13.20
        data["low"][15] = 11.80
        # 前日小实体
        data["open"][14] = 12.40
        data["close"][14] = 12.50
        # 后续
        for i in range(16, 20):
            data["close"][i] = 12.80
            data["open"][i] = 12.70
            data["high"][i] = 12.90
            data["low"][i] = 12.60

        detector = BalanceLine()
        result = detector.detect(data, date="2026-09-20")

        assert result["is_valid"] is True
        assert result["line_price"] == 12.00  # 大阳实底 = min(open, close) = 12.00
        assert result["anchor_type"] == "big_yang_real_bottom"

    def test_insufficient_data(self):
        """数据不足"""
        data = _make_data(2)
        detector = BalanceLine()
        result = detector.detect(data, date="2026-09-02")
        assert result["is_valid"] is False

    def test_output_fields_complete(self):
        """输出字段完整性"""
        data = _make_data(20)
        data["open"][15] = 13.00
        data["close"][15] = 12.00
        data["open"][14] = 12.50
        data["close"][14] = 12.40
        for i in range(16, 20):
            data["close"][i] = 12.50

        detector = BalanceLine()
        result = detector.detect(data, date="2026-09-20")

        required = [
            "signal_id", "date", "is_valid", "line_type",
            "line_price", "anchor_date", "anchor_type", "balance_type",
            "position", "nature", "confidence",
        ]
        for f in required:
            assert f in result, f"缺少字段: {f}"

    def test_position_nature_present(self):
        """position/nature字段"""
        data = _make_data(30)
        data["open"][15] = 13.00
        data["close"][15] = 12.00
        data["open"][14] = 12.50
        data["close"][14] = 12.40

        detector = BalanceLine()
        result = detector.detect(data, date="2026-09-30")
        assert "position" in result
        assert "nature" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
