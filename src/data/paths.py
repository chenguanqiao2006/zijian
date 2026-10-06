#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/paths.py — 数据目录宪法与路径唯一真身
================================================

本模块是 zijian 数据路径的唯一权威来源——一切脚本禁止手拼数据路径，
必须经本模块构造或校验。

目录宪法（唯一合法形态）：

    data/
    ├── kline/                          # 日线
    │   ├── sh/sh600519.json            # 嵌套：市场子目录 + 带前缀文件名
    │   └── sz/sz000688.json
    ├── kline_1min/                     # 1分钟（中转区 · 分析后即删）
    │   ├── sh/sh600519.json
    │   └── sz/sz000688.json
    ├── universe/
    │   └── hushen300.json              # 股票池缓存
    └── analysis/
        └── truth_ledger/2026-10.json   # 真假账本（月分片）

四条铁规：
    1. code 唯一合法形态 = sh/sz + 6位数字（如 sh600519）；
    2. 市场子目录 = code 前两位，与文件名前缀严格一致；
    3. 日线与 1 分钟结构完全对齐——知其一必知其二；
    4. 扁平形态与无前缀形态均非法——不存在第二约定。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # 项目根（src/data/ 上级的上级）

_CODE_RE = re.compile(r'^(sh|sz)\d{6}$')
_MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
_DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def validate_code(code) -> str:
    """股票代码校验（唯一合法：sh/sz+6位数字；非法 → ValueError）。"""
    s = str(code or '').strip().lower()
    if not _CODE_RE.match(s):
        raise ValueError(
            '非法代码: {!r}（合法形态: sh600519 / sz000688）'.format(code))
    return s


def kline_dir() -> Path:
    """日线根目录 data/kline/。"""
    return BASE / 'data' / 'kline'


def min1_dir() -> Path:
    """1分钟根目录 data/kline_1min/（与日线同构）。"""
    return BASE / 'data' / 'kline_1min'


def ledger_dir() -> Path:
    """真假账本根目录 data/analysis/truth_ledger/。"""
    return BASE / 'data' / 'analysis' / 'truth_ledger'


def universe_dir() -> Path:
    """股票池缓存目录 data/universe/。"""
    return BASE / 'data' / 'universe'


def kline_path(code) -> Path:
    """日线文件路径 data/kline/{market}/{code}.json。"""
    code = validate_code(code)
    return kline_dir() / code[:2] / f'{code}.json'


def min1_path(code) -> Path:
    """1分钟文件路径 data/kline_1min/{market}/{code}.json。"""
    code = validate_code(code)
    return min1_dir() / code[:2] / f'{code}.json'


def universe_path() -> Path:
    """沪深300成分股缓存文件 data/universe/hushen300.json。"""
    return universe_dir() / 'hushen300.json'


def all_market_path() -> Path:
    """全市场A股缓存文件 data/universe/all_market.json（沪市+深市，不含北交所）。"""
    return universe_dir() / 'all_market.json'


def ledger_path(month: str) -> Path:
    """真假账本月分片文件 data/analysis/truth_ledger/{YYYY-MM}.json。"""
    if not _MONTH_RE.match(month or ''):
        raise ValueError(f'非法月份: {month!r}（合法形态: 2026-10）')
    return ledger_dir() / f'{month}.json'


def self_check() -> bool:
    """路径宪法自检（10项）。通过返回 True，失败打印并返回 False。"""
    errors = []

    # 1. BASE 存在
    if not BASE.exists():
        errors.append(f'BASE 不存在: {BASE}')

    # 2. validate_code 合法码
    for c in ('sh600519', 'sz000688', 'SH600519', 'sz300750'):
        try:
            validate_code(c)
        except ValueError as e:
            errors.append(f'合法码被拒: {c} → {e}')

    # 3. validate_code 非法码
    for c in ('600519', 'sh60051', 'bj600519', '', None):
        try:
            validate_code(c)
            errors.append(f'非法码未拒: {c!r}')
        except ValueError:
            pass

    # 4. kline_path 结构
    p = kline_path('sh600519')
    if p.parent.name != 'sh' or p.name != 'sh600519.json':
        errors.append(f'kline_path 结构错误: {p}')

    # 5. min1_path 结构
    p = min1_path('sz000688')
    if p.parent.name != 'sz' or p.name != 'sz000688.json':
        errors.append(f'min1_path 结构错误: {p}')

    # 6. 日线与1分钟同构（仅目录名不同）
    kp = kline_path('sh600519')
    mp = min1_path('sh600519')
    if kp.name != mp.name or kp.parent.name != mp.parent.name:
        errors.append('日线与1分钟结构不同构')

    # 7. universe_path
    if universe_path().name != 'hushen300.json':
        errors.append(f'universe_path 错误: {universe_path()}')

    # 8. ledger_path 合法
    try:
        lp = ledger_path('2026-10')
        if lp.name != '2026-10.json':
            errors.append(f'ledger_path 错误: {lp}')
    except ValueError as e:
        errors.append(f'合法月份被拒: {e}')

    # 9. ledger_path 非法
    try:
        ledger_path('2026-13')
        errors.append('非法月份未拒')
    except ValueError:
        pass

    # 10. 目录可创建
    for d in (kline_dir(), min1_dir(), ledger_dir(), universe_dir()):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            errors.append(f'目录创建失败: {d} → {e}')

    if errors:
        print('[FAIL] 路径宪法自检失败:')
        for e in errors:
            print(f'  - {e}')
        return False
    print('[OK] 路径宪法自检通过（10项全绿）')
    return True


if __name__ == '__main__':
    sys.exit(0 if self_check() else 1)
