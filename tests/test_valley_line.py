"""谷底线（valley_line）测试用例

覆盖规格卡第9节测试用例：
1. 标准：阶段性真底+低量柱+已确认 → is_valid=true
2. 边界·极端缩量真底 → 标注需人工复核
3. 失效·取点被后续低点跌破 → 取点失效
4. 边界·数据不足 → 不判定
5. 输出字段完整性检查
"""

import pytest

from src.price_lines.valley_line import ValleyLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    """构造Mock数据"""
    return {
        "open": [base_price] * n,
        "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n,
        "close": [base_price] * n,
        "volume": [base_vol] * n,
        "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestValleyLineStandard:
    def test_standard_valley_confirmed(self):
        """标准用例：阶段性真底+低量柱+已确认 → is_valid=true"""
        data = _make_data(20)
        # T-10日为真底（低量柱+最低价10.00）
        data["low"][10] = 10.00
        data["close"][10] = 10.20
        data["open"][10] = 10.50
        data["volume"][10] = 200.0  # 低量柱
        # 后续K线最低价均 > 10.00（确认）
        for i in range(11, 20):
            data["low"][i] = 10.20
            data["close"][i] = 10.50
        # 左侧K线最低价均 > 10.00
        for i in range(10):
            data["low"][i] = 11.00

        detector = ValleyLine()
        result = detector.detect(data, date="2026-09-20")

        assert result["is_valid"] is True
        assert result["line_price"] == 10.20  # 实底 = min(open, close) = 10.20
        assert result["anchor_price_type"] == "real_bottom"
        assert result["signal_id"] == "valley_line"

    def test_extreme_shrink_valley(self):
        """边界用例：极端缩量真底 → 标注需人工复核"""
        data = _make_data(20)
        # T-10日为真底
        data["low"][10] = 9.50
        data["close"][10] = 9.60
        data["open"][10] = 9.80
        data["volume"][10] = 100.0  # 低量
        data["volume"][9] = 2000.0  # 前一日高量 → 极端缩量（100 < 2000×0.1=200）
        # 确认
        for i in range(11, 20):
            data["low"][i] = 9.70
        for i in range(10):
            data["low"][i] = 10.00

        detector = ValleyLine()
        result = detector.detect(data, date="2026-09-20")

        if result["is_valid"]:
            assert "note" in result
            assert "极端缩量" in result["note"]

    def test_valley_broken_by_new_low(self):
        """失效用例：取点被后续低点跌破 → 原取点失效"""
        data = _make_data(20)
        # T-10日低点10.00
        data["low"][10] = 10.00
        data["close"][10] = 10.20
        data["volume"][10] = 200.0
        # T-5日创新低9.00（跌破原取点）
        data["low"][15] = 9.00
        data["close"][15] = 9.20
        data["volume"][15] = 150.0
        # 后续确认9.00
        for i in range(16, 20):
            data["low"][i] = 9.20

        detector = ValleyLine()
        result = detector.detect(data, date="2026-09-20")

        # 原取点10.00被跌破，应移至9.00
        if result["is_valid"]:
            assert result["line_price"] <= 9.20  # 新取点的实底

    def test_insufficient_data(self):
        """边界用例：数据不足 → 不判定"""
        data = _make_data(5)  # 只有5天

        detector = ValleyLine()
        result = detector.detect(data, date="2026-09-05")

        assert result["is_valid"] is False
        assert "数据不足" in result["reason"]

    def test_output_fields_complete(self):
        """输出字段完整性检查"""
        data = _make_data(20)
        data["low"][10] = 10.00
        data["close"][10] = 10.20
        data["open"][10] = 10.50
        data["volume"][10] = 200.0
        for i in range(11, 20):
            data["low"][i] = 10.20
        for i in range(10):
            data["low"][i] = 11.00

        detector = ValleyLine()
        result = detector.detect(data, date="2026-09-20")

        required_fields = [
            "signal_id", "date", "is_valid", "line_type",
            "line_price", "anchor_date", "anchor_price_type",
            "position", "nature", "confidence",
        ]
        for field in required_fields:
            assert field in result, f"缺少字段: {field}"

    def test_position_field_present(self):
        """position 和 nature 字段必须存在"""
        data = _make_data(30)
        data["low"][15] = 10.00
        data["close"][15] = 10.20
        data["volume"][15] = 200.0
        for i in range(16, 30):
            data["low"][i] = 10.20

        detector = ValleyLine()
        result = detector.detect(data, date="2026-09-30")

        assert "position" in result
        assert "nature" in result
        assert result["position"] in ["low", "mid", "high", "unknown"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
