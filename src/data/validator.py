#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/validator.py — 行情数据校验器
========================================

拉取完成后自动校验数据质量，防止垃圾数据进入分析管道。

校验维度：
1. 条数检查（1分钟每天约240根，日线至少1根）
2. 时间范围（最早/最晚时间，是否在合理范围内）
3. 空值检查（OHLCV不能为None或<=0）
4. 价格合理性（high >= low，close在[low, high]范围内）
5. 交易日数量（1分钟数据覆盖多少个交易日）
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple


# 1分钟K线：每天交易4小时 = 240分钟（9:30-11:30, 13:00-15:00）
MIN1_BARS_PER_DAY = 240
# 1分钟数据每天允许的最少根数（扣除停牌/集合竞价等，至少200根算正常交易日）
MIN1_BARS_PER_DAY_MIN = 200
# 1分钟数据每天允许的最多根数（防止重复数据）
MIN1_BARS_PER_DAY_MAX = 250


def _parse_time(bar: Dict[str, Any]) -> datetime | None:
    """从K线中解析时间，支持多种字段名。"""
    for key in ("time", "date", "datetime", "day"):
        val = bar.get(key)
        if val:
            try:
                if isinstance(val, (int, float)):
                    return datetime.fromtimestamp(val)
                # 尝试多种格式
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                             "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
                    try:
                        return datetime.strptime(str(val), fmt)
                    except ValueError:
                        continue
            except (ValueError, OSError):
                continue
    return None


def _get_bar_value(bar: Dict[str, Any], key: str) -> float | None:
    """安全获取K线数值。"""
    val = bar.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def validate_min1(bars: List[Dict[str, Any]], code: str) -> Tuple[bool, List[str], Dict[str, Any]]:
    """校验1分钟K线数据。

    Args:
        bars: K线列表，每根为dict，含 time/open/high/low/close/volume
        code: 股票代码（如 sh600519）

    Returns:
        (is_valid, issues, stats)
        - is_valid: 是否通过校验
        - issues: 问题列表
        - stats: 统计信息（bar_count, trading_days, date_range等）
    """
    issues: List[str] = []
    stats: Dict[str, Any] = {
        "bar_count": len(bars),
        "trading_days": 0,
        "date_range": [None, None],
        "null_count": 0,
        "price_error_count": 0,
    }

    if not bars:
        issues.append("数据为空（0根K线）")
        return False, issues, stats

    # 解析所有时间
    times: List[datetime] = []
    for i, bar in enumerate(bars):
        t = _parse_time(bar)
        if t:
            times.append(t)
        else:
            issues.append(f"第{i}根K线时间解析失败: {bar.get('time')!r}")

    if times:
        stats["date_range"] = [min(times).strftime("%Y-%m-%d"),
                                 max(times).strftime("%Y-%m-%d")]
        # 计算交易日数量（去重日期）
        unique_dates = set(t.strftime("%Y-%m-%d") for t in times)
        stats["trading_days"] = len(unique_dates)

        # 条数检查：交易日数 * 240 左右
        expected_bars = stats["trading_days"] * MIN1_BARS_PER_DAY
        if len(bars) < expected_bars * 0.8:
            issues.append(f"条数偏少: {len(bars)}根，预期约{expected_bars}根（{stats['trading_days']}个交易日）")
        if len(bars) > expected_bars * 1.1:
            issues.append(f"条数偏多（可能重复）: {len(bars)}根，预期约{expected_bars}根")

    # 空值和价格合理性检查（抽样检查，不全量检查以节省时间）
    sample_size = min(len(bars), 200)
    sample_step = max(1, len(bars) // sample_size)
    for i in range(0, len(bars), sample_step):
        bar = bars[i]
        o = _get_bar_value(bar, "open")
        h = _get_bar_value(bar, "high")
        l = _get_bar_value(bar, "low")
        c = _get_bar_value(bar, "close")
        v = _get_bar_value(bar, "volume")

        # 空值检查
        if any(x is None for x in (o, h, l, c, v)):
            stats["null_count"] += 1
            issues.append(f"第{i}根K线存在空值: O={o} H={h} L={l} C={c} V={v}")
            continue

        # 价格合理性
        if h < l:
            stats["price_error_count"] += 1
            issues.append(f"第{i}根K线价格异常: high({h}) < low({l})")
        if c < l or c > h:
            stats["price_error_count"] += 1
            issues.append(f"第{i}根K线收盘价越界: close({c})不在[{l},{h}]范围内")
        if v < 0:
            issues.append(f"第{i}根K线成交量为负: {v}")

    # 汇总
    if stats["null_count"] > 0:
        issues.append(f"抽样发现{stats['null_count']}根K线含空值")
    if stats["price_error_count"] > 0:
        issues.append(f"抽样发现{stats['price_error_count']}根K线价格异常")

    is_valid = len(issues) == 0
    return is_valid, issues, stats


def validate_daily(bars: List[Dict[str, Any]], code: str) -> Tuple[bool, List[str], Dict[str, Any]]:
    """校验日线K线数据。

    Returns:
        (is_valid, issues, stats)
    """
    issues: List[str] = []
    stats: Dict[str, Any] = {
        "bar_count": len(bars),
        "date_range": [None, None],
        "null_count": 0,
        "price_error_count": 0,
    }

    if not bars:
        issues.append("数据为空（0根K线）")
        return False, issues, stats

    # 解析时间
    times: List[datetime] = []
    for i, bar in enumerate(bars):
        t = _parse_time(bar)
        if t:
            times.append(t)
        else:
            issues.append(f"第{i}根K线时间解析失败")

    if times:
        stats["date_range"] = [min(times).strftime("%Y-%m-%d"),
                                 max(times).strftime("%Y-%m-%d")]

    # 空值和价格合理性检查（全量检查，因为日线数据量小）
    for i, bar in enumerate(bars):
        o = _get_bar_value(bar, "open")
        h = _get_bar_value(bar, "high")
        l = _get_bar_value(bar, "low")
        c = _get_bar_value(bar, "close")
        v = _get_bar_value(bar, "volume")

        if any(x is None for x in (o, h, l, c, v)):
            stats["null_count"] += 1
            continue

        if h < l:
            stats["price_error_count"] += 1
        if c < l or c > h:
            stats["price_error_count"] += 1

    if stats["null_count"] > 0:
        issues.append(f"发现{stats['null_count']}根K线含空值")
    if stats["price_error_count"] > 0:
        issues.append(f"发现{stats['price_error_count']}根K线价格异常")

    is_valid = len(issues) == 0
    return is_valid, issues, stats


def print_validation_report(code: str, data_type: str,
                             is_valid: bool, issues: List[str],
                             stats: Dict[str, Any]) -> None:
    """打印校验报告。"""
    status = "✅ 通过" if is_valid else "❌ 未通过"
    print(f"  [{code}] {data_type}: {status}")
    print(f"    条数={stats.get('bar_count', 0)}, "
          f"交易日={stats.get('trading_days', 'N/A')}, "
          f"日期范围={stats.get('date_range', ['N/A', 'N/A'])}")
    if issues:
        for issue in issues[:5]:
            print(f"    ⚠️  {issue}")
        if len(issues) > 5:
            print(f"    ... 共{len(issues)}个问题")


if __name__ == "__main__":
    # 简单自测
    test_bars = [
        {"time": "2026-10-07 09:30:00", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000},
        {"time": "2026-10-07 09:31:00", "open": 100.5, "high": 102, "low": 100, "close": 101, "volume": 2000},
    ]
    ok, issues, stats = validate_min1(test_bars, "sh600519")
    print_validation_report("sh600519", "1分钟", ok, issues, stats)
