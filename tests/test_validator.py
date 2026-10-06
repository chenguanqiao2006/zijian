#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_validator.py — 数据校验器测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data.validator import (
    validate_min1, validate_daily, _parse_time, _get_bar_value,
    MIN1_BARS_PER_DAY,
)


def make_min1_bars(n_days=1, bars_per_day=240, start_date="2026-10-07"):
    """构造模拟1分钟K线数据。"""
    from datetime import datetime, timedelta
    bars = []
    base = datetime.strptime(start_date, "%Y-%m-%d")
    for d in range(n_days):
        day = base + timedelta(days=d)
        for m in range(bars_per_day):
            # 模拟交易时间：9:30-11:30 (120min) + 13:00-15:00 (120min)
            if m < 120:
                t = day.replace(hour=9, minute=30) + timedelta(minutes=m)
            else:
                t = day.replace(hour=13, minute=0) + timedelta(minutes=m - 120)
            bars.append({
                "time": t.strftime("%Y-%m-%d %H:%M:%S"),
                "open": 100 + m * 0.01,
                "high": 101 + m * 0.01,
                "low": 99 + m * 0.01,
                "close": 100.5 + m * 0.01,
                "volume": 1000 + m,
            })
    return bars


class TestParseTime:
    def test_standard_format(self):
        t = _parse_time({"time": "2026-10-07 09:30:00"})
        assert t is not None
        assert t.year == 2026 and t.month == 10 and t.day == 7

    def test_date_only(self):
        t = _parse_time({"date": "2026-10-07"})
        assert t is not None

    def test_invalid(self):
        t = _parse_time({"time": "not-a-date"})
        assert t is None

    def test_missing(self):
        t = _parse_time({})
        assert t is None


class TestGetBarValue:
    def test_normal(self):
        assert _get_bar_value({"open": 100.5}, "open") == 100.5

    def test_none(self):
        assert _get_bar_value({"open": None}, "open") is None

    def test_missing(self):
        assert _get_bar_value({}, "open") is None

    def test_string_number(self):
        assert _get_bar_value({"open": "100.5"}, "open") == 100.5

    def test_invalid_string(self):
        assert _get_bar_value({"open": "abc"}, "open") is None


class TestValidateMin1:
    def test_valid_data(self):
        bars = make_min1_bars(n_days=1, bars_per_day=240)
        is_valid, issues, stats = validate_min1(bars, "sh600519")
        assert is_valid is True
        assert len(issues) == 0
        assert stats["bar_count"] == 240
        assert stats["trading_days"] == 1

    def test_multi_day(self):
        bars = make_min1_bars(n_days=5, bars_per_day=240)
        is_valid, issues, stats = validate_min1(bars, "sh600519")
        assert is_valid is True
        assert stats["trading_days"] == 5
        assert stats["bar_count"] == 1200

    def test_empty_data(self):
        is_valid, issues, stats = validate_min1([], "sh600519")
        assert is_valid is False
        assert "数据为空" in issues[0]

    def test_too_few_bars(self):
        # 1个交易日但只有100根（明显偏少）
        bars = make_min1_bars(n_days=1, bars_per_day=100)
        is_valid, issues, stats = validate_min1(bars, "sh600519")
        assert is_valid is False
        assert any("偏少" in i for i in issues)

    def test_null_values(self):
        bars = make_min1_bars(n_days=1, bars_per_day=240)
        bars[0]["open"] = None
        is_valid, issues, stats = validate_min1(bars, "sh600519")
        assert stats["null_count"] >= 1

    def test_price_error_high_lt_low(self):
        bars = make_min1_bars(n_days=1, bars_per_day=240)
        bars[0]["high"] = 90
        bars[0]["low"] = 100
        is_valid, issues, stats = validate_min1(bars, "sh600519")
        assert stats["price_error_count"] >= 1

    def test_date_range(self):
        bars = make_min1_bars(n_days=3, bars_per_day=240, start_date="2026-10-05")
        is_valid, issues, stats = validate_min1(bars, "sh600519")
        assert stats["date_range"][0] == "2026-10-05"
        assert stats["date_range"][1] == "2026-10-07"


class TestValidateDaily:
    def test_valid_data(self):
        bars = [
            {"time": "2026-10-01", "open": 100, "high": 105, "low": 98, "close": 103, "volume": 10000},
            {"time": "2026-10-02", "open": 103, "high": 108, "low": 102, "close": 107, "volume": 12000},
        ]
        is_valid, issues, stats = validate_daily(bars, "sh600519")
        assert is_valid is True
        assert stats["bar_count"] == 2

    def test_empty(self):
        is_valid, issues, stats = validate_daily([], "sh600519")
        assert is_valid is False

    def test_null(self):
        bars = [
            {"time": "2026-10-01", "open": None, "high": 105, "low": 98, "close": 103, "volume": 10000},
        ]
        is_valid, issues, stats = validate_daily(bars, "sh600519")
        assert stats["null_count"] == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
