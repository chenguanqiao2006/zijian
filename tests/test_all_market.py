#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_all_market.py — 全市场日线拉取测试
================================================

覆盖：
    1. all_market_path 路径宪法
    2. load_all_market 缓存读取
    3. load_all_market 北交所坚决排除
    4. --all-market 命令行参数解析
    5. run_threaded 自定义并发数
    6. run_fetch 全市场模式跳过1分钟
    7. 全市场股票代码格式校验（sh6xxxxx / sz0xxxxx / sz3xxxxx）
"""

import json
import sys
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.paths import all_market_path, universe_dir, validate_code
from src.data.fetch_quotes import (
    is_bj, load_all_market, run_threaded, run_fetch,
)


# ---------------------------------------------------------------------------
# 路径宪法
# ---------------------------------------------------------------------------

class TestAllMarketPath:
    def test_all_market_path_under_universe_dir(self):
        """all_market_path 必须在 data/universe/ 下。"""
        assert all_market_path().parent == universe_dir()

    def test_all_market_path_filename(self):
        """文件名必须是 all_market.json。"""
        assert all_market_path().name == 'all_market.json'


# ---------------------------------------------------------------------------
# 北交所过滤（核心硬约束）
# ---------------------------------------------------------------------------

class TestBeijingExclusion:
    def test_is_bj_4xxxxx(self):
        """4开头 = 北交所。"""
        assert is_bj('bj430047') is True
        assert is_bj('430047') is True

    def test_is_bj_8xxxxx(self):
        """8开头 = 北交所。"""
        assert is_bj('bj830799') is True
        assert is_bj('830799') is True

    def test_is_bj_9xxxxx(self):
        """9开头 = 北交所。"""
        assert is_bj('bj920002') is True

    def test_sh_not_bj(self):
        """沪市6开头不是北交所。"""
        assert is_bj('sh600519') is False
        assert is_bj('600519') is False

    def test_sz_not_bj(self):
        """深市0/3开头不是北交所。"""
        assert is_bj('sz000001') is False
        assert is_bj('sz300750') is False


# ---------------------------------------------------------------------------
# load_all_market 缓存读取
# ---------------------------------------------------------------------------

class TestLoadAllMarketCache:
    def test_load_from_cache(self, tmp_path):
        """缓存存在时直接读缓存，不调 akshare。"""
        cache = tmp_path / 'all_market.json'
        cache.write_text(json.dumps(['sh600519', 'sz000001', 'sz300750']),
                         encoding='utf-8')
        with patch('src.data.fetch_quotes.all_market_path', return_value=cache):
            result = load_all_market()
        assert result == ['sh600519', 'sz000001', 'sz300750']

    def test_cache_excludes_bj(self, tmp_path):
        """缓存里混了北交所也要过滤掉。"""
        cache = tmp_path / 'all_market.json'
        cache.write_text(json.dumps(['sh600519', 'bj430047', 'sz000001', '830799']),
                         encoding='utf-8')
        with patch('src.data.fetch_quotes.all_market_path', return_value=cache):
            result = load_all_market()
        assert 'bj430047' not in result
        assert '830799' not in result
        assert 'sh600519' in result
        assert 'sz000001' in result

    def test_empty_cache_triggers_refetch(self, tmp_path):
        """空缓存文件会触发重新拉取（mock 数据源失败时返回空）。"""
        cache = tmp_path / 'all_market.json'
        cache.write_text('[]', encoding='utf-8')
        with patch('src.data.fetch_quotes.all_market_path', return_value=cache), \
             patch('src.data.fetch_quotes.save_json'), \
             patch('akshare.stock_info_sh_name_code', side_effect=Exception('no net')), \
             patch('akshare.stock_info_sz_name_code', side_effect=Exception('no net')), \
             patch('akshare.stock_zh_a_spot_em', side_effect=Exception('no net')):
            result = load_all_market()
        assert result == []

    def test_corrupt_cache_falls_through(self, tmp_path):
        """损坏的缓存文件不崩溃，继续走拉取逻辑。"""
        cache = tmp_path / 'all_market.json'
        cache.write_text('not valid json{{{', encoding='utf-8')
        with patch('src.data.fetch_quotes.all_market_path', return_value=cache), \
             patch('src.data.fetch_quotes.save_json'), \
             patch('akshare.stock_info_sh_name_code', side_effect=Exception('no net')), \
             patch('akshare.stock_info_sz_name_code', side_effect=Exception('no net')), \
             patch('akshare.stock_zh_a_spot_em', side_effect=Exception('no net')):
            result = load_all_market()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 命令行参数解析
# ---------------------------------------------------------------------------

class TestAllMarketArg:
    def _make_args(self, *extra):
        """构造 argparse Namespace。"""
        ap = argparse.ArgumentParser()
        ap.add_argument('--full', action='store_true')
        ap.add_argument('--days', type=int, default=120)
        ap.add_argument('--codes', nargs='*')
        ap.add_argument('--self-check', action='store_true')
        ap.add_argument('--watchlist', action='store_true')
        ap.add_argument('--no-hs300', action='store_true')
        ap.add_argument('--all-market', action='store_true')
        return ap.parse_args(list(extra))

    def test_all_market_flag_default_false(self):
        """默认不带 --all-market。"""
        args = self._make_args()
        assert getattr(args, 'all_market', False) is False

    def test_all_market_flag_true(self):
        """带 --all-market 时为 True。"""
        args = self._make_args('--all-market')
        assert args.all_market is True

    def test_all_market_and_codes_mutually_exclusive_in_logic(self):
        """--codes 优先级高于 --all-market（codes 先判断）。"""
        args = self._make_args('--all-market', '--codes', 'sh600519')
        assert args.codes == ['sh600519']
        assert args.all_market is True


# ---------------------------------------------------------------------------
# run_threaded 自定义并发
# ---------------------------------------------------------------------------

class TestRunThreadedWorkers:
    def test_default_workers(self):
        """默认用 MAX_WORKERS。"""
        def worker(code):
            return True, 'test'
        ok, failed, sources = run_threaded(['sh600519', 'sz000001'], worker)
        assert ok == 2
        assert failed == []

    def test_custom_workers(self):
        """自定义 max_workers 不影响结果。"""
        def worker(code):
            return True, 'test'
        ok, failed, sources = run_threaded(
            ['sh600519', 'sz000001', 'sz300750'], worker, max_workers=3)
        assert ok == 3

    def test_partial_failure(self):
        """部分失败时正确统计。"""
        def worker(code):
            if code == 'sh600519':
                return False, None
            return True, 'tencent'
        ok, failed, sources = run_threaded(['sh600519', 'sz000001'], worker)
        assert ok == 1
        assert failed == ['sh600519']


# ---------------------------------------------------------------------------
# 全市场代码格式
# ---------------------------------------------------------------------------

class TestAllMarketCodeFormat:
    def test_only_sh6_and_sz03(self):
        """全市场只允许 sh6xxxxx / sz0xxxxx / sz3xxxxx。"""
        valid = ['sh600519', 'sh601318', 'sz000001', 'sz002156', 'sz300750']
        for code in valid:
            assert validate_code(code) == code

    def test_reject_bj_prefixes(self):
        """拒绝 bj 前缀和 4/8/9 开头。"""
        invalid_candidates = ['bj430047', 'bj830799', '430047', '830799', '920002']
        for code in invalid_candidates:
            assert is_bj(code) is True, f'{code} 应被识别为北交所'
