#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/status.py — 拉取状态跟踪器
====================================

记录每只股票的拉取状态，让你一眼看到"茅台积累了多少天1分钟数据"。

状态文件位置：data/fetch_status.json

状态内容：
- 最后拉取时间
- 数据源（sina/tencent/eastmoney）
- 数据条数
- 覆盖交易日数（1分钟特有）
- 日期范围
- 校验是否通过
- 问题列表
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import BASE, validate_code


STATUS_FILE = BASE / "data" / "fetch_status.json"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_status() -> Dict[str, Any]:
    """加载状态文件，不存在则返回空结构。"""
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_run": None, "stocks": {}}


def save_status(status: Dict[str, Any]) -> None:
    """保存状态文件。"""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def update_stock_status(code: str, data_type: str, source: Optional[str],
                         bar_count: int, trading_days: Optional[int],
                         date_range: List[Optional[str]],
                         is_valid: bool, issues: List[str]) -> None:
    """更新单只股票的拉取状态。

    Args:
        code: 股票代码（如 sh600519）
        data_type: "daily" 或 "min1"
        source: 数据源（sina/tencent/eastmoney）
        bar_count: 数据条数
        trading_days: 覆盖交易日数（1分钟特有，日线传None）
        date_range: [最早日期, 最晚日期]
        is_valid: 校验是否通过
        issues: 问题列表
    """
    code = validate_code(code)
    status = load_status()
    status["last_run"] = _now_str()

    if code not in status["stocks"]:
        status["stocks"][code] = {}

    status["stocks"][code][data_type] = {
        "last_fetch": _now_str(),
        "source": source,
        "bar_count": bar_count,
        "trading_days": trading_days,
        "date_range": date_range,
        "is_valid": is_valid,
        "issues": issues[:10],  # 最多保留10个问题
    }

    save_status(status)


def get_stock_status(code: str) -> Optional[Dict[str, Any]]:
    """获取单只股票的状态。"""
    code = validate_code(code)
    status = load_status()
    return status["stocks"].get(code)


def get_summary() -> Dict[str, Any]:
    """获取状态汇总。"""
    status = load_status()
    stocks = status.get("stocks", {})

    min1_stocks = [c for c, s in stocks.items() if "min1" in s]
    daily_stocks = [c for c, s in stocks.items() if "daily" in s]

    # 1分钟数据天数统计
    min1_days_list = []
    for c in min1_stocks:
        days = stocks[c]["min1"].get("trading_days", 0)
        if days:
            min1_days_list.append(days)

    summary = {
        "last_run": status.get("last_run"),
        "total_stocks": len(stocks),
        "daily_stocks": len(daily_stocks),
        "min1_stocks": len(min1_stocks),
        "min1_avg_days": round(sum(min1_days_list) / len(min1_days_list), 1) if min1_days_list else 0,
        "min1_max_days": max(min1_days_list) if min1_days_list else 0,
        "min1_min_days": min(min1_days_list) if min1_days_list else 0,
    }
    return summary


def print_summary() -> None:
    """打印状态汇总（人类可读）。"""
    summary = get_summary()
    status = load_status()
    stocks = status.get("stocks", {})

    print("=" * 60)
    print("📊 数据拉取状态汇总")
    print("=" * 60)
    print(f"  最后运行: {summary['last_run'] or '从未运行'}")
    print(f"  股票总数: {summary['total_stocks']}")
    print(f"  日线覆盖: {summary['daily_stocks']} 只")
    print(f"  1分钟覆盖: {summary['min1_stocks']} 只")
    if summary["min1_stocks"] > 0:
        print(f"  1分钟天数: 平均{summary['min1_avg_days']}天 / "
              f"最多{summary['min1_max_days']}天 / "
              f"最少{summary['min1_min_days']}天")
    print()

    # 逐只股票详情（1分钟）
    min1_stocks = [(c, s) for c, s in stocks.items() if "min1" in s]
    if min1_stocks:
        print("📋 1分钟数据详情:")
        print(f"  {'代码':<12} {'天数':>6} {'条数':>8} {'日期范围':<24} {'源':<10} {'状态':<6}")
        print("  " + "-" * 70)
        for code, s in sorted(min1_stocks):
            m = s["min1"]
            days = m.get("trading_days", 0) or 0
            bars = m.get("bar_count", 0)
            dr = m.get("date_range", ["?", "?"])
            src = m.get("source", "?") or "?"
            valid = "✅" if m.get("is_valid") else "❌"
            print(f"  {code:<12} {days:>6} {bars:>8} {dr[0] or '?':<11}~{dr[1] or '?':<11} {src:<10} {valid:<6}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    print_summary()
