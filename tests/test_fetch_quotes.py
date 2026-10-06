#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_fetch_quotes.py — 数据采集层测试
============================================

覆盖：
    1. 路径宪法自检（10项）
    2. 日线拉取（腾讯源，需联网）
    3. 1分钟拉取（新浪源，多日，需联网）
    4. 数据格式验证（统一 [时间,开,高,低,收,量]）
    5. 北交所过滤
    6. 多源降级链结构验证

注意：标注 [需联网] 的测试用例需要网络连接，在离线环境中会跳过。
"""

import json
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.paths import (
    validate_code, kline_path, min1_path, universe_path,
    ledger_path, kline_dir, min1_dir, ledger_dir, universe_dir,
    self_check,
)
from src.data.fetch_quotes import is_bj


# ---------------------------------------------------------------------------
# 路径宪法测试
# ---------------------------------------------------------------------------

class TestPathsConstitution:
    """路径宪法单元测试（无需联网）。"""

    def test_self_check_passes(self):
        """路径宪法自检10项全绿。"""
        assert self_check() is True

    def test_validate_code_valid(self):
        """合法代码通过校验。"""
        assert validate_code('sh600519') == 'sh600519'
        assert validate_code('sz000688') == 'sz000688'
        assert validate_code('SH600519') == 'sh600519'  # 大写转小写

    def test_validate_code_invalid(self):
        """非法代码抛出 ValueError。"""
        for bad in ('600519', 'sh60051', 'bj600519', '', None, 'sh6005199'):
            with pytest.raises(ValueError):
                validate_code(bad)

    def test_kline_path_structure(self):
        """日线路径结构：data/kline/{market}/{code}.json。"""
        p = kline_path('sh600519')
        assert p.parent.name == 'sh'
        assert p.name == 'sh600519.json'
        assert 'kline' in p.parts

    def test_min1_path_structure(self):
        """1分钟路径结构：data/kline_1min/{market}/{code}.json。"""
        p = min1_path('sz000688')
        assert p.parent.name == 'sz'
        assert p.name == 'sz000688.json'
        assert 'kline_1min' in p.parts

    def test_daily_min1_isomorphic(self):
        """日线与1分钟结构完全同构（仅目录名不同）。"""
        for code in ('sh600519', 'sz000688'):
            kp = kline_path(code)
            mp = min1_path(code)
            assert kp.name == mp.name
            assert kp.parent.name == mp.parent.name

    def test_universe_path(self):
        """股票池缓存路径。"""
        p = universe_path()
        assert p.name == 'hushen300.json'
        assert 'universe' in p.parts

    def test_ledger_path_valid(self):
        """账本月分片路径合法。"""
        p = ledger_path('2026-10')
        assert p.name == '2026-10.json'
        assert 'truth_ledger' in p.parts

    def test_ledger_path_invalid(self):
        """非法月份抛出 ValueError。"""
        for bad in ('2026-13', '2026-1', '202610', ''):
            with pytest.raises(ValueError):
                ledger_path(bad)

    def test_is_bj(self):
        """北交所过滤。"""
        assert is_bj('bj430047') is True
        assert is_bj('sh830001') is True  # 83开头
        assert is_bj('sh600519') is False
        assert is_bj('sz000688') is False


# ---------------------------------------------------------------------------
# 数据格式验证工具
# ---------------------------------------------------------------------------

def _validate_bar_format(bar):
    """验证单根K线格式：[时间(str), 开(float), 高(float), 低(float), 收(float), 量(float)]。"""
    assert isinstance(bar, list), f'K线应为list，实际: {type(bar)}'
    assert len(bar) == 6, f'K线应有6个元素，实际: {len(bar)}'
    assert isinstance(bar[0], str), f'时间应为str，实际: {type(bar[0])}'
    for i, name in enumerate(['开', '高', '低', '收', '量'], start=1):
        assert isinstance(bar[i], (int, float)), f'{name}应为数值，实际: {type(bar[i])}'
    # 高>=开,收>=低
    assert bar[2] >= bar[1], f'高应>=开: {bar[2]} < {bar[1]}'
    assert bar[2] >= bar[3], f'高应>=低: {bar[2]} < {bar[3]}'
    assert bar[4] >= bar[3], f'收应>=低: {bar[4]} < {bar[3]}'
    assert bar[5] >= 0, f'量应>=0: {bar[5]}'


# ---------------------------------------------------------------------------
# 日线拉取测试（需联网）
# ---------------------------------------------------------------------------

class TestDailyFetch:
    """日线拉取集成测试（需联网）。"""

    @pytest.mark.network
    def test_tencent_daily_available(self):
        """腾讯日线可用。"""
        from src.data.fetch_quotes import daily_from_tencent
        bars = daily_from_tencent('sh600519', datalen=10)
        assert bars is not None
        assert len(bars) > 0
        assert len(bars) <= 10

    @pytest.mark.network
    def test_daily_format(self):
        """日线数据格式正确。"""
        from src.data.fetch_quotes import daily_from_tencent
        bars = daily_from_tencent('sh600519', datalen=5)
        assert bars
        for bar in bars:
            _validate_bar_format(bar)

    @pytest.mark.network
    def test_daily_date_format(self):
        """日线时间格式为 YYYY-MM-DD。"""
        from src.data.fetch_quotes import daily_from_tencent
        bars = daily_from_tencent('sh600519', datalen=5)
        assert bars
        for bar in bars:
            assert len(bar[0]) == 10, f'日期应为10字符: {bar[0]}'
            assert bar[0][4] == '-' and bar[0][7] == '-', f'日期格式应为YYYY-MM-DD: {bar[0]}'

    @pytest.mark.network
    def test_daily_fallback_chain(self):
        """日线降级链结构：腾讯→新浪→东财。"""
        from src.data.fetch_quotes import DAILY_SOURCES
        names = [n for n, _ in DAILY_SOURCES]
        assert names == ['腾讯', '新浪', '东财']


# ---------------------------------------------------------------------------
# 1分钟拉取测试（需联网）
# ---------------------------------------------------------------------------

class TestMin1Fetch:
    """1分钟拉取集成测试（需联网）。"""

    @pytest.mark.network
    def test_sina_min1_available(self):
        """新浪1分钟可用（多日）。"""
        from src.data.fetch_quotes import min1_from_sina
        bars = min1_from_sina('sh600519')
        assert bars is not None
        assert len(bars) > 0

    @pytest.mark.network
    def test_sina_min1_multi_day(self):
        """新浪1分钟覆盖多个交易日（核心痛点验证）。"""
        from src.data.fetch_quotes import min1_from_sina
        bars = min1_from_sina('sh600519')
        assert bars
        days = set(b[0][:10] for b in bars)
        assert len(days) >= 2, f'新浪1分钟应覆盖至少2个交易日，实际: {len(days)}'

    @pytest.mark.network
    def test_min1_format(self):
        """1分钟数据格式正确。"""
        from src.data.fetch_quotes import min1_from_sina
        bars = min1_from_sina('sh600519')
        assert bars
        for bar in bars[:50]:  # 抽验前50根
            _validate_bar_format(bar)

    @pytest.mark.network
    def test_min1_datetime_format(self):
        """1分钟时间格式为 YYYY-MM-DD HH:MM。"""
        from src.data.fetch_quotes import min1_from_sina
        bars = min1_from_sina('sh600519')
        assert bars
        for bar in bars[:10]:
            t = bar[0]
            assert len(t) == 16, f'时间应为16字符(YYYY-MM-DD HH:MM)，实际: {len(t)}: {t}'
            assert t[10] == ' ', f'日期时间间应有空格: {t}'
            assert t[13] == ':', f'时分间应有冒号: {t}'

    @pytest.mark.network
    def test_min1_fallback_chain(self):
        """1分钟降级链结构：新浪(多日)→腾讯(当日)→东财(多日)。"""
        from src.data.fetch_quotes import MIN1_SOURCES
        names = [n for n, _ in MIN1_SOURCES]
        assert names == ['新浪', '腾讯', '东财']

    @pytest.mark.network
    def test_tencent_min1_available(self):
        """腾讯分时可用（仅当日）。"""
        from src.data.fetch_quotes import min1_from_tencent
        bars = min1_from_tencent('sh600519')
        # 腾讯分时在非交易时段可能返回最近交易日数据
        # 只要不抛异常即可
        assert bars is not None


# ---------------------------------------------------------------------------
# 多源降级集成测试（需联网）
# ---------------------------------------------------------------------------

class TestFetchFallback:
    """多源降级集成测试（需联网）。"""

    @pytest.mark.network
    def test_fetch_daily_returns_source(self):
        """fetch_daily 返回 (源名, bars)。"""
        from src.data.fetch_quotes import fetch_daily
        src, bars = fetch_daily('sh600519', datalen=5)
        assert src is not None
        assert bars is not None
        assert len(bars) > 0
        assert src in ('腾讯', '新浪', '东财')

    @pytest.mark.network
    def test_fetch_min1_returns_source(self):
        """fetch_min1 返回 (源名, bars)。"""
        from src.data.fetch_quotes import fetch_min1
        src, bars = fetch_min1('sh600519')
        assert src is not None
        assert bars is not None
        assert len(bars) > 0
        assert src in ('新浪', '腾讯', '东财')


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
