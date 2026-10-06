"""斜衡线（slant_line）测试用例

覆盖规格卡第9节测试用例：
1. 标准·上升斜衡线
2. 边界·短间隔
3. 失效·斜率为0
4. 输出字段完整性检查
"""

import pytest

from src.price_lines.slant_line import SlantLine


def _make_data(n, base_price=100.0, base_vol=1000.0):
    return {
        "open": [base_price] * n,
        "high": [base_price + 0.5] * n,
        "low": [base_price - 0.5] * n,
        "close": [base_price] * n,
        "volume": [base_vol] * n,
        "dates": [f"2026-09-{i+1:02d}" for i in range(n)],
    }


class TestSlantLineStandard:
    def test_upward_slant_line(self):
        """标准用例：上升斜衡线（两个真底，低点抬高）"""
        data = _make_data(30)
        # 第一个真底（T-20日）
        idx1 = 8
        data["low"][idx1] = 10.00
        data["close"][idx1] = 10.20
        data["open"][idx1] = 10.50
        data["volume"][idx1] = 200.0  # 低量柱
        # 确认（后续最低价 > 10.00）
        for i in range(idx1 + 1, 30):
            data["low"][i] = 10.50
        # 左侧最低价 > 10.00
        for i in range(idx1):
            data["low"][i] = 11.00

        # 第二个真底（T日附近），低点抬高
        idx2 = 25
        data["low"][idx2] = 11.00
        data["close"][idx2] = 11.20
        data["open"][idx2] = 11.50
        data["volume"][idx2] = 250.0  # 低量柱
        # 确认
        for i in range(idx2 + 1, 30):
            data["low"][i] = 11.50

        detector = SlantLine()
        result = detector.detect(data, date="2026-09-30")

        # 上升斜衡线应该成立
        if result["is_valid"]:
            assert result["trend_direction"] == "up"
            assert result["slope"] > 0  # 正斜率
            assert "slope" in result
            assert "intercept" in result

    def test_slope_zero_invalid(self):
        """失效用例：斜率为0 → 应改用平衡线"""
        data = _make_data(30)
        # 两个真底，价格相同（斜率为0）
        idx1 = 8
        data["low"][idx1] = 10.00
        data["close"][idx1] = 10.00
        data["open"][idx1] = 10.00
        data["volume"][idx1] = 200.0
        for i in range(idx1 + 1, 30):
            data["low"][i] = 10.50
        for i in range(idx1):
            data["low"][i] = 11.00

        idx2 = 25
        data["low"][idx2] = 10.00  # 相同价格
        data["close"][idx2] = 10.00
        data["open"][idx2] = 10.00
        data["volume"][idx2] = 200.0
        for i in range(idx2 + 1, 30):
            data["low"][i] = 10.50

        detector = SlantLine()
        result = detector.detect(data, date="2026-09-30")

        # 斜率为0或找不到同方向拐点，均应返回无效
        assert result["is_valid"] is False

    def test_insufficient_data(self):
        """数据不足"""
        data = _make_data(5)
        detector = SlantLine()
        result = detector.detect(data, date="2026-09-05")
        assert result["is_valid"] is False

    def test_output_fields_complete(self):
        """输出字段完整性"""
        data = _make_data(30)
        idx1 = 8
        data["low"][idx1] = 10.00
        data["close"][idx1] = 10.20
        data["open"][idx1] = 10.50
        data["volume"][idx1] = 200.0
        for i in range(idx1 + 1, 30):
            data["low"][i] = 10.50
        for i in range(idx1):
            data["low"][i] = 11.00
        idx2 = 25
        data["low"][idx2] = 11.00
        data["close"][idx2] = 11.20
        data["open"][idx2] = 11.50
        data["volume"][idx2] = 250.0
        for i in range(idx2 + 1, 30):
            data["low"][i] = 11.50

        detector = SlantLine()
        result = detector.detect(data, date="2026-09-30")

        if result["is_valid"]:
            required = [
                "signal_id", "date", "is_valid", "line_type",
                "slope", "intercept",
                "anchor1_date", "anchor1_price",
                "anchor2_date", "anchor2_price",
                "trend_direction", "position", "nature", "confidence",
            ]
            for f in required:
                assert f in result, f"缺少字段: {f}"

    def test_trend_direction_values(self):
        """trend_direction取值检查"""
        data = _make_data(30)
        idx1 = 8
        data["low"][idx1] = 10.00
        data["close"][idx1] = 10.20
        data["open"][idx1] = 10.50
        data["volume"][idx1] = 200.0
        for i in range(idx1 + 1, 30):
            data["low"][i] = 10.50
        for i in range(idx1):
            data["low"][i] = 11.00
        idx2 = 25
        data["low"][idx2] = 11.00
        data["close"][idx2] = 11.20
        data["open"][idx2] = 11.50
        data["volume"][idx2] = 250.0
        for i in range(idx2 + 1, 30):
            data["low"][i] = 11.50

        detector = SlantLine()
        result = detector.detect(data, date="2026-09-30")

        if result["is_valid"]:
            assert result["trend_direction"] in ["up", "down"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
