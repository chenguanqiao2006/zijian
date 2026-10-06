#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_record_truth.py — 真假量柱账本分析器测试
====================================================

覆盖：
    1. 核心指标计算（CV / corr / tail_ratio / flatness）
    2. v2.3 新信号（flat_vol_ratio / tail_gain / zero_vol_mins）
    3. 涨跌停/一字板检测
    4. 判定逻辑（真金白银 / 疑似量化 / 量化对倒）
    5. 数据解析（兼容字符串/数组/字典三种格式）
    6. filter_session（连续竞价时段过滤）
    7. LedgerCache（账本读写+验证）
    8. 北交所过滤
    9. 端到端（Mock 数据 → analyze_day → 判定结果）
"""

import json
import math
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.record_truth import (
    is_bj, limit_pct_for, min_bars_for,
    extract_bars_payload, normalize_bar, extract_date,
    filter_session, load_and_group_days,
    safe_corr, session_volume_profile, flatness_score, build_feature_snapshot,
    compute_flat_vol_ratio, compute_tail_gain,
    compute_big_order_stats, compute_pattern_stats,
    _pct_rank, compute_vwap_hold_ratio, compute_weave_score, compute_pm_reversal,
    load_market_volume,
    compute_morning_afternoon_vol_ratio, compute_volume_peak_concentration,
    compute_price_volume_divergence, compute_wave_features,
    compute_close_in_amplitude, compute_vwap_deviation,
    compute_realized_volatility, compute_up_down_minute_ratio, compute_gap_filled,
    compute_return_skewness, compute_return_kurtosis, compute_downside_vol_ratio,
    compute_vwap_cross_count, compute_price_path_efficiency,
    compute_max_consecutive, compute_volume_price_quadrants,
    compute_volume_profile,
    compute_vwap_slope, compute_vwap_std_band,
    compute_open_close_5min,
    detect_limit_status, compute_quant_pct, analyze_day,
    LedgerCache,
)


# ---------------------------------------------------------------------------
# 辅助：构造 Mock 1分钟K线
# ---------------------------------------------------------------------------

def make_bars(n=240, price=100.0, vol=1000.0, start_time='2026-09-30 09:30'):
    """构造 n 根均匀的1分钟K线（价格恒定、量能恒定）。"""
    bars = []
    h, m = 9, 30
    for i in range(n):
        time_str = f'2026-09-30 {h:02d}:{m:02d}'
        bars.append({
            'time': time_str,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'volume': vol,
        })
        m += 1
        if m == 60:
            m = 0
            h += 1
        if h == 12 and m > 0:
            h, m = 13, 0
        if h == 15 and m > 0:
            break
    return bars


# ---------------------------------------------------------------------------
# 北交所过滤
# ---------------------------------------------------------------------------

class TestIsBJ:
    def test_bj_prefix(self):
        assert is_bj('bj430047') is True

    def test_sh_normal(self):
        assert is_bj('sh600519') is False

    def test_sz_normal(self):
        assert is_bj('sz000688') is False

    def test_83_prefix(self):
        assert is_bj('sh830001') is True

    def test_empty(self):
        assert is_bj('') is False


# ---------------------------------------------------------------------------
# 涨跌停规则
# ---------------------------------------------------------------------------

class TestLimitPct:
    def test_main_board(self):
        assert limit_pct_for('sh600519') == 0.098

    def test_gem(self):
        assert limit_pct_for('sz300750') == 0.198

    def test_star(self):
        assert limit_pct_for('sh688981') == 0.198

    def test_min_bars(self):
        assert min_bars_for('sh600519') == 230


# ---------------------------------------------------------------------------
# 数据解析
# ---------------------------------------------------------------------------

class TestDataParsing:
    def test_extract_list(self):
        payload = [['2026-09-30 09:30', 100, 101, 99, 100.5, 1000]]
        assert extract_bars_payload(payload) == payload

    def test_extract_dict_bars(self):
        obj = {'bars': [['2026-09-30', 100, 101, 99, 100.5, 1000]]}
        assert extract_bars_payload(obj) == obj['bars']

    def test_extract_dict_klines(self):
        obj = {'data': {'klines': ['2026-09-30,100,101,99,100.5,1000']}}
        result = extract_bars_payload(obj)
        assert result == ['2026-09-30,100,101,99,100.5,1000']

    def test_normalize_array(self):
        bar = normalize_bar(['2026-09-30 09:30', 100, 101, 99, 100.5, 1000])
        assert bar['open'] == 100
        assert bar['high'] == 101
        assert bar['volume'] == 1000

    def test_normalize_string(self):
        bar = normalize_bar('2026-09-30 09:30,100,101,99,100.5,1000')
        assert bar['close'] == 100.5

    def test_normalize_dict(self):
        bar = normalize_bar({'time': '2026-09-30', 'open': 100, 'high': 101,
                              'low': 99, 'close': 100.5, 'volume': 1000})
        assert bar['time'] == '2026-09-30'

    def test_extract_date_standard(self):
        assert extract_date('2026-09-30 09:30') == '2026-09-30'

    def test_extract_date_slash(self):
        assert extract_date('2026/09/30') == '2026-09-30'

    def test_extract_date_none(self):
        assert extract_date(None) is None


# ---------------------------------------------------------------------------
# filter_session
# ---------------------------------------------------------------------------

class TestFilterSession:
    def test_keeps_trading_hours(self):
        bars = [
            {'time': '2026-09-30 09:30', 'volume': 100},
            {'time': '2026-09-30 10:00', 'volume': 100},
            {'time': '2026-09-30 11:30', 'volume': 100},
            {'time': '2026-09-30 13:00', 'volume': 100},
            {'time': '2026-09-30 15:00', 'volume': 100},
        ]
        result = filter_session(bars)
        assert len(result) == 5

    def test_filters_lunch_break(self):
        bars = [
            {'time': '2026-09-30 11:30', 'volume': 100},
            {'time': '2026-09-30 12:00', 'volume': 100},  # 午休
            {'time': '2026-09-30 12:30', 'volume': 100},  # 午休
            {'time': '2026-09-30 13:00', 'volume': 100},
        ]
        result = filter_session(bars)
        assert len(result) == 2

    def test_cuts_tail_zero_vol(self):
        bars = [
            {'time': '2026-09-30 14:55', 'volume': 100},
            {'time': '2026-09-30 14:56', 'volume': 0},
            {'time': '2026-09-30 14:57', 'volume': 0},
            {'time': '2026-09-30 14:58', 'volume': 0},
        ]
        result = filter_session(bars)
        assert len(result) == 1
        assert result[0]['time'] == '2026-09-30 14:55'


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------

class TestIndicators:
    def test_safe_corr_perfect(self):
        # 完全正相关
        r = safe_corr([1, 2, 3], [1, 2, 3])
        assert abs(r - 1.0) < 0.001

    def test_safe_corr_negative(self):
        r = safe_corr([1, 2, 3], [3, 2, 1])
        assert abs(r + 1.0) < 0.001

    def test_safe_corr_none_too_few(self):
        assert safe_corr([1], [1]) is None

    def test_session_volume_profile(self):
        # 均匀分布：6个时段根数分别为30/60/30/60/30/30，占比各为 根数/240
        vols = [100] * 240
        profile = session_volume_profile(vols)
        assert profile is not None
        assert len(profile) == 6
        expected = [30/240, 60/240, 30/240, 60/240, 30/240, 30/240]
        for p, e in zip(profile, expected):
            assert abs(p - e) < 0.001
        assert abs(sum(profile) - 1.0) < 0.001

    def test_flatness_score_uniform(self):
        # 完全均匀 → flatness=0
        profile = [1.0 / 6] * 6
        assert flatness_score(profile) == 0

    def test_build_feature_snapshot(self):
        vols = [100] * 240
        snap = build_feature_snapshot(vols)
        assert snap is not None
        assert len(snap) == 24
        for s in snap:
            assert abs(s - 1.0 / 24) < 0.001


# ---------------------------------------------------------------------------
# v2.3 新信号
# ---------------------------------------------------------------------------

class TestV23Signals:
    def test_flat_vol_ratio_no_flat(self):
        # 价格波动大，无平价放量
        bars = [{'open': 100, 'close': 101} for _ in range(10)]
        vols = [2000] * 10  # 放量但价格不平
        ratio = compute_flat_vol_ratio(bars, vols, 1000)
        assert ratio == 0

    def test_flat_vol_ratio_with_flat(self):
        # 价格平 + 放量
        bars = [{'open': 100.00, 'close': 100.00} for _ in range(5)]
        vols = [3000] * 5  # 3倍均量
        ratio = compute_flat_vol_ratio(bars, vols, 1000)
        assert ratio == 1.0

    def test_tail_gain_positive(self):
        bars = make_bars(n=31, price=100.0)
        bars[-1]['close'] = 102.0  # 尾盘涨2%
        gain = compute_tail_gain(bars)
        assert gain is not None
        assert abs(gain - 0.02) < 0.001

    def test_tail_gain_too_few_bars(self):
        bars = make_bars(n=10)
        assert compute_tail_gain(bars) is None

    def test_zero_vol_mins(self):
        bars = make_bars(n=10, vol=1000)
        vols = [1000, 0, 1000, 0, 1000, 1000, 0, 1000, 1000, 1000]
        zero_count = sum(1 for v in vols if v <= 0)
        assert zero_count == 3


# ---------------------------------------------------------------------------
# v2.4 新信号：大单拆分 + 主力净流入
# ---------------------------------------------------------------------------

class TestV24Signals:
    def test_big_order_stats_basic(self):
        # 基本功能：构造有阳线/阴线/大单的场景
        bars = []
        vols = []
        for i in range(10):
            if i % 2 == 0:  # 阳线
                bars.append({'open': 100, 'close': 101, 'high': 101, 'low': 100})
                vols.append(5000)  # 放量
            else:  # 阴线
                bars.append({'open': 101, 'close': 100, 'high': 101, 'low': 100})
                vols.append(5000)  # 放量
        stats = compute_big_order_stats(bars, vols, 1000)  # 均量1000，3倍=3000
        assert stats is not None
        assert stats['big_order_minutes'] == 10  # 全部是大单
        assert stats['big_order_ratio'] == 1.0
        # 5阳5阴，净流入=0
        assert abs(stats['main_net_inflow']) < 1
        assert abs(stats['order_flow_imbalance']) < 0.01

    def test_big_order_stats_all_yang(self):
        # 全部阳线 → 净流入为正
        bars = [{'open': 100, 'close': 101, 'high': 101, 'low': 100} for _ in range(10)]
        vols = [2000] * 10
        stats = compute_big_order_stats(bars, vols, 1000)
        assert stats is not None
        assert stats['main_net_inflow'] > 0
        assert stats['main_net_inflow_pct'] > 0
        assert stats['order_flow_imbalance'] > 0

    def test_big_order_stats_all_yin(self):
        # 全部阴线 → 净流出为负
        bars = [{'open': 101, 'close': 100, 'high': 101, 'low': 100} for _ in range(10)]
        vols = [2000] * 10
        stats = compute_big_order_stats(bars, vols, 1000)
        assert stats is not None
        assert stats['main_net_inflow'] < 0
        assert stats['order_flow_imbalance'] < 0

    def test_big_order_stats_flat_bar(self):
        # 平盘（close==open）→ 买卖平分
        bars = [{'open': 100, 'close': 100, 'high': 100, 'low': 100} for _ in range(10)]
        vols = [2000] * 10
        stats = compute_big_order_stats(bars, vols, 1000)
        assert stats is not None
        # 平盘买卖平分，净流入=0
        assert abs(stats['main_net_inflow']) < 1
        assert abs(stats['order_flow_imbalance']) < 0.01

    def test_big_order_stats_no_big(self):
        # 没有大单（量 < 均量×3）
        bars = [{'open': 100, 'close': 101, 'high': 101, 'low': 100} for _ in range(10)]
        vols = [1000] * 10  # 等于均量，不超过3倍
        stats = compute_big_order_stats(bars, vols, 1000)
        assert stats is not None
        assert stats['big_order_minutes'] == 0
        assert stats['big_order_ratio'] == 0
        assert stats['big_order_net_inflow'] == 0  # 无大单，大单净流入=0

    def test_big_order_stats_zero_vol(self):
        # 零成交量 → 返回None
        bars = [{'open': 100, 'close': 101, 'high': 101, 'low': 100} for _ in range(10)]
        vols = [0] * 10
        stats = compute_big_order_stats(bars, vols, 0)
        assert stats is None

    def test_analyze_day_v24_fields(self):
        # analyze_day 返回值包含 v2.4 字段
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        # v2.4 六个字段都存在
        for field in ('big_order_minutes', 'big_order_ratio', 'main_net_inflow',
                      'main_net_inflow_pct', 'big_order_net_inflow', 'order_flow_imbalance'):
            assert field in entry, f'缺少字段: {field}'
        # 值不为 None
        assert entry['big_order_minutes'] is not None
        assert entry['main_net_inflow'] is not None
        assert entry['order_flow_imbalance'] is not None

    def test_order_flow_imbalance_range(self):
        # order_flow_imbalance 应在 [-1, 1] 范围内
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 3 - 1) * 0.05
            b['high'] = max(b['open'], b['close']) + 0.02
            b['low'] = min(b['open'], b['close']) - 0.02
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        ofi = entry['order_flow_imbalance']
        assert -1.0 <= ofi <= 1.0


# ---------------------------------------------------------------------------
# v2.5 新信号：分时形态识别
# ---------------------------------------------------------------------------

class TestV25Signals:
    def test_pattern_stats_basic(self):
        # 基本功能：构造简单K线
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert 'amplitude' in stats
        assert 'pattern' in stats
        assert 'high_time_idx' in stats
        assert 'low_time_idx' in stats

    def test_pattern_sideways(self):
        # 横盘：振幅极小
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for b in bars:
            b['high'] = 100.05
            b['low'] = 99.95
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['pattern'] == 'sideways'
        assert stats['amplitude'] < 1.0

    def test_pattern_v_shape(self):
        # V型：上午最低（明确在上午中段），下午最高，振幅大
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i < 60:  # 前60分钟下跌
                b['close'] = 100 - i * 0.04
            elif i < 120:  # 60-120分钟低位横盘
                b['close'] = 97.6
            else:  # 下午上涨
                b['close'] = 97.6 + (i - 120) * 0.04
            b['low'] = b['close'] - 0.05
            b['high'] = b['close'] + 0.05
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['pattern'] == 'v_shape'
        assert stats['low_time_idx'] < 120
        assert stats['high_time_idx'] >= 120

    def test_pattern_inverted_v_shape(self):
        # 倒V型：上午最高（明确在上午中段），下午最低，振幅大
        # 注意：尾盘横盘不跌，避免触发 tail_dive（优先级更高）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i < 60:  # 前60分钟上涨
                b['close'] = 100 + i * 0.04
            elif i < 120:  # 60-120分钟高位横盘
                b['close'] = 102.4
            elif i < 210:  # 下午前段下跌
                b['close'] = 102.4 - (i - 120) * 0.04
            else:  # 尾盘横盘（不跌，避免触发tail_dive）
                b['close'] = 98.8
            b['low'] = b['close'] - 0.05
            b['high'] = b['close'] + 0.05
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['pattern'] == 'inverted_v_shape'
        assert stats['high_time_idx'] < 120
        assert stats['low_time_idx'] >= 120

    def test_pattern_morning_pullback(self):
        # 早盘冲高回落：开盘即最高，然后回落（振幅<2%避免触发倒V型）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i == 0:
                b['high'] = 101.5
                b['close'] = 101.2
            else:
                b['close'] = 100.5 - i * 0.002
            b['low'] = b['close'] - 0.05
            b['high'] = max(b['high'], b['close'] + 0.05)
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['pattern'] == 'morning_pullback'
        assert stats['high_time_idx'] < 30

    def test_pattern_one_side_up(self):
        # 单边上涨：上午弱，下午强，收盘接近最高
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i < 120:  # 上午微跌
                b['close'] = 100 - i * 0.002
            else:  # 下午大涨
                b['close'] = 99.76 + (i - 120) * 0.01
            b['high'] = b['close'] + 0.05
            b['low'] = b['close'] - 0.05
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['pattern'] == 'one_side_up'
        assert stats['morning_return'] < stats['afternoon_return']

    def test_amplitude_calculation(self):
        # 振幅计算正确
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        bars[0]['high'] = 105.0
        bars[5]['low'] = 95.0
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert abs(stats['amplitude'] - 10.0) < 0.1  # (105-95)/100*100 = 10%

    def test_open_gap_pct(self):
        # 开盘缺口计算
        bars = make_bars(n=10, price=102.0, vol=1000.0)  # 开盘102
        stats = compute_pattern_stats(bars, 100.0)  # 前收100
        assert stats is not None
        assert abs(stats['open_gap_pct'] - 2.0) < 0.1  # (102/100-1)*100 = 2%

    def test_high_low_time_idx(self):
        # 最高/最低价位置正确
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        bars[3]['high'] = 110.0  # 最高在索引3
        bars[7]['low'] = 90.0    # 最低在索引7
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['high_time_idx'] == 3
        assert stats['low_time_idx'] == 7

    def test_analyze_day_v25_fields(self):
        # analyze_day 返回值包含 v2.5 字段
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        for field in ('amplitude', 'morning_return', 'afternoon_return',
                      'open_gap_pct', 'high_time_idx', 'low_time_idx', 'pattern'):
            assert field in entry, f'缺少字段: {field}'
        assert entry['pattern'] is not None

    def test_pattern_values_valid(self):
        # pattern 值必须是9种合法值之一
        valid_patterns = {
            'sideways', 'tail_rally', 'tail_dive', 'v_shape',
            'inverted_v_shape', 'morning_pullback', 'one_side_up',
            'one_side_down', 'no_clear_pattern',
        }
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 7 - 3) * 0.1
            b['high'] = max(b['open'], b['close']) + 0.05
            b['low'] = min(b['open'], b['close']) - 0.05
        stats = compute_pattern_stats(bars, 100.0)
        assert stats is not None
        assert stats['pattern'] in valid_patterns


# ---------------------------------------------------------------------------
# 涨跌停检测
# ---------------------------------------------------------------------------

class TestLimitStatus:
    def test_one_word_board(self):
        bars = [{'open': 10, 'high': 10, 'low': 10, 'close': 10}]
        result = detect_limit_status(bars, 9.09, 0.098)
        assert result == 'one_word'

    def test_limit_up(self):
        bars = [{'open': 10, 'high': 11, 'low': 10, 'close': 11}]
        result = detect_limit_status(bars, 10.0, 0.098)
        assert result == 'limit_up'

    def test_limit_down(self):
        bars = [{'open': 9, 'high': 9, 'low': 8.5, 'close': 9}]
        result = detect_limit_status(bars, 10.0, 0.098)
        assert result == 'limit_down'

    def test_no_limit(self):
        bars = [{'open': 10, 'high': 10.5, 'low': 9.8, 'close': 10.2}]
        result = detect_limit_status(bars, 10.0, 0.098)
        assert result is None


# ---------------------------------------------------------------------------
# 判定逻辑
# ---------------------------------------------------------------------------

class TestVerdict:
    def test_real_money(self):
        # 构造0命中：cv高(量能波动大) + corr高(量价正相关) + 尾盘不集中 + 分布不均
        bars = []
        for i in range(240):
            # 量能大幅波动（奇数根放量，偶数根缩量）→ cv高
            vol = 5000 if i % 2 == 0 else 100
            # 价格与量能正相关 → corr高
            price = 100 + (vol / 5000.0) * 0.5
            hh = 9 + (i * 60 + 570) // 3600  # 交易时段小时
            mm = (i * 60 + 570) % 3600 // 60
            if hh >= 12 and mm > 0:
                hh, mm = 13, (mm - 60) if mm >= 60 else mm
            bars.append({
                'time': f'2026-09-30 {hh:02d}:{mm:02d}',
                'open': price, 'high': price + 0.05, 'low': price - 0.05,
                'close': price + 0.02, 'volume': vol,
            })
        entry = analyze_day(bars, 'sh600519', 99.0)
        assert entry is not None
        # 0命中 → 真金白银
        assert entry['is_real'] is True
        assert entry['verdict'] == '真金白银'

    def test_quant_manipulation(self):
        # 构造≥2命中：cv低(均匀) + 尾盘集中 + 分布均匀
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        # 价格小幅波动（避免一字板），但价格变化与量能无关
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 7) * 0.01
            b['high'] = b['close'] + 0.02
            b['low'] = b['close'] - 0.02
        # 尾盘30根大幅放量 → tail_ratio命中
        for i in range(210, 240):
            bars[i]['volume'] = 8000
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        # cv低(命中) + tail_ratio高(命中) → 至少2命中 → 量化对倒
        assert entry['is_real'] is False
        assert entry['verdict'] == '量化对倒'

    def test_limit_exempt(self):
        # 一字板（至少2根，high==low）→ 豁免
        bars = [
            {'time': '2026-09-30 09:30', 'open': 10, 'high': 10, 'low': 10,
             'close': 10, 'volume': 1000},
            {'time': '2026-09-30 09:31', 'open': 10, 'high': 10, 'low': 10,
             'close': 10, 'volume': 2000},
        ]
        entry = analyze_day(bars, 'sh600519', 9.09)
        assert entry is not None
        assert entry['limit_status'] == 'one_word'
        assert '豁免' in entry['verdict']

    def test_v23_fields_present(self):
        # 验证 v2.3 新字段都存在（价格有波动，避免一字板）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        assert 'flat_vol_ratio' in entry
        assert 'tail_gain' in entry
        assert 'zero_vol_mins' in entry
        assert 'vprofile_24' in entry
        assert entry['flat_vol_ratio'] is not None
        assert entry['tail_gain'] is not None


# ---------------------------------------------------------------------------
# LedgerCache
# ---------------------------------------------------------------------------

class TestLedgerCache:
    def test_put_and_has(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = LedgerCache(Path(tmp))
            entry = {'verdict': '真金白银', 'is_real': True}
            ledger.put('2026-09', 'sh600519', '2026-09-30', entry)
            assert ledger.has('2026-09', 'sh600519', '2026-09-30')
            assert not ledger.has('2026-09', 'sh600519', '2026-09-29')

    def test_flush_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = LedgerCache(Path(tmp))
            entry = {'verdict': '真金白银', 'is_real': True}
            ledger.put('2026-09', 'sh600519', '2026-09-30', entry)
            ledger.flush()
            assert ledger.verify([('2026-09', 'sh600519', '2026-09-30')])
            assert not ledger.verify([('2026-09', 'sh600519', '2026-09-29')])

    def test_flush_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = LedgerCache(Path(tmp))
            ledger.put('2026-09', 'sh600519', '2026-09-30', {'v': 1})
            ledger.flush()
            assert (Path(tmp) / '2026-09.json').exists()


# ---------------------------------------------------------------------------
# compute_quant_pct
# ---------------------------------------------------------------------------

class TestQuantPct:
    def test_all_low(self):
        # 所有指标都低 → 量化程度高
        pct = compute_quant_pct(0.3, 0.1, 0.5, 0.1)
        assert pct >= 50

    def test_all_high(self):
        # 所有指标都高 → 量化程度低
        pct = compute_quant_pct(1.5, 0.8, 0.1, 0.5)
        assert pct <= 30


# ---------------------------------------------------------------------------
# v2.6 新信号：双轨判定 + 行为指纹 + 指数剔除
# ---------------------------------------------------------------------------

class TestV26DualTrack:
    def test_absolute_threshold_fallback(self):
        # 无历史数据 → 用绝对阈值兜底，verdict_basis="绝对阈值"
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0, history_data=None)
        assert entry is not None
        assert entry['verdict_basis'] == '绝对阈值'

    def test_relative_threshold_with_history(self):
        # 有≥5天历史 → 用相对分位，verdict_basis="相对分位"
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        history = {
            'cv': [1.0, 1.1, 1.2, 1.3, 1.4],
            'corr': [0.1, 0.2, 0.3, 0.4, 0.5],
            'tail_ratio': [0.1, 0.12, 0.14, 0.16, 0.18],
        }
        entry = analyze_day(bars, 'sh600519', 100.0, history_data=history)
        assert entry is not None
        assert entry['verdict_basis'] == '相对分位'

    def test_insufficient_history_fallback(self):
        # 历史<5天 → 仍用绝对阈值兜底
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        history = {
            'cv': [1.0, 1.1],
            'corr': [0.1, 0.2],
            'tail_ratio': [0.1, 0.12],
        }
        entry = analyze_day(bars, 'sh600519', 100.0, history_data=history)
        assert entry is not None
        assert entry['verdict_basis'] == '绝对阈值'

    def test_calibrated_cv_threshold(self):
        # 校准后 CV≤0.95：构造低CV数据（量均匀）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['volume'] = 1000.0
            b['close'] = 100 + (i % 3) * 0.01
            b['high'] = b['close'] + 0.02
            b['low'] = b['close'] - 0.02
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        # CV≈0 ≤ 0.95，应命中CV指标
        assert entry['cv'] <= 0.95


class TestV26PctRank:
    def test_pct_rank_basic(self):
        # 基本分位计算
        assert _pct_rank(5, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == 0.45

    def test_pct_rank_min(self):
        # 最小值 → 分位0
        assert _pct_rank(1, [1, 2, 3, 4, 5]) == 0.1

    def test_pct_rank_max(self):
        # 最大值 → 分位接近1
        assert _pct_rank(5, [1, 2, 3, 4, 5]) == 0.9

    def test_pct_rank_empty(self):
        # 空数组 → None
        assert _pct_rank(5, []) is None

    def test_pct_rank_none_value(self):
        # None值 → None
        assert _pct_rank(None, [1, 2, 3]) is None


class TestV26BehaviorFingerprints:
    def test_vwap_hold_ratio_basic(self):
        # 基本功能：价格在VWAP上方的占比
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.1  # 持续上涨，一直在VWAP上方
        ratio = compute_vwap_hold_ratio(bars)
        assert ratio is not None
        assert 0 <= ratio <= 1
        assert ratio > 0.5  # 持续上涨应大部分在VWAP上方

    def test_vwap_hold_ratio_all_below(self):
        # 持续下跌 → 大部分在VWAP下方
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 - i * 0.1
        ratio = compute_vwap_hold_ratio(bars)
        assert ratio is not None
        assert ratio < 0.5

    def test_vwap_hold_ratio_empty(self):
        # 空数据 → None
        assert compute_vwap_hold_ratio([]) is None

    def test_weave_score_basic(self):
        # 基本功能：价格在VWAP±1.5%内的占比
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for b in bars:
            b['close'] = 100.0  # 价格不动，完全在带宽内
        score = compute_weave_score(bars)
        assert score is not None
        assert 0 <= score <= 1
        assert score == 1.0  # 价格完全不动，织布机评分=1

    def test_weave_score_volatile(self):
        # 价格大幅波动 → 织布机评分低
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 2) * 5.0  # 大幅波动
        score = compute_weave_score(bars)
        assert score is not None
        assert score < 1.0

    def test_pm_reversal_morning_up_afternoon_down(self):
        # 上午涨、下午跌 → 午后反转=1
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i < 120:  # 上午涨
                b['close'] = 100 + i * 0.01
            else:  # 下午跌
                b['close'] = 101.2 - (i - 120) * 0.01
            b['open'] = b['close']
        reversal = compute_pm_reversal(bars)
        assert reversal == 1

    def test_pm_reversal_both_up(self):
        # 上午涨、下午也涨 → 无反转=0
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.005
            b['open'] = b['close']
        reversal = compute_pm_reversal(bars)
        assert reversal == 0

    def test_pm_reversal_small_move(self):
        # 波动太小 → None
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for b in bars:
            b['close'] = 100.0
            b['open'] = 100.0
        reversal = compute_pm_reversal(bars)
        assert reversal is None

    def test_analyze_day_v26_fields(self):
        # analyze_day 返回值包含 v2.6 字段
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        for field in ('vwap_hold_ratio', 'weave_score', 'pm_reversal', 'verdict_basis'):
            assert field in entry, f'缺少字段: {field}'


class TestV26IndexFilter:
    def test_index_codes_constant(self):
        # 指数代码集合包含三大指数
        from src.analysis.record_truth import INDEX_CODES
        assert 'sh000001' in INDEX_CODES
        assert 'sz399001' in INDEX_CODES
        assert 'sz399006' in INDEX_CODES

    def test_calibrated_thresholds_constants(self):
        # 校准阈值常量
        from src.analysis.record_truth import CV_ABS_QUANT, TAIL_ABS_QUANT, CORR_ABS_QUANT
        assert CV_ABS_QUANT == 0.95
        assert TAIL_ABS_QUANT == 0.22
        assert CORR_ABS_QUANT == 0.30


# ---------------------------------------------------------------------------
# v2.7 新信号：大盘量比
# ---------------------------------------------------------------------------

class TestV27MarketVolRatio:
    def test_analyze_day_with_market_vol_ratio(self):
        # analyze_day 接收 market_vol_ratio 参数并返回该字段
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0, market_vol_ratio=1.25)
        assert entry is not None
        assert entry['market_vol_ratio'] == 1.25

    def test_analyze_day_without_market_vol_ratio(self):
        # 不传 market_vol_ratio 时为 None
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        assert entry['market_vol_ratio'] is None

    def test_load_market_volume_missing_file(self, tmp_path):
        # 指数日线文件不存在时返回空 dict
        result = load_market_volume(tmp_path)
        assert result == {}

    def test_load_market_volume_with_data(self, tmp_path):
        # 构造模拟指数日线数据，验证量比计算
        import json
        sh_dir = tmp_path / "sh"
        sh_dir.mkdir()
        # 构造10天数据，前5天量=100，第6天量=150（量比=150/100=1.5）
        klines = []
        for i in range(10):
            date = f'2026-09-{i+1:02d}'
            vol = 150 if i == 5 else 100
            klines.append([date, 100, 100, 100, 100, float(vol)])
        with open(sh_dir / "sh000001.json", 'w') as f:
            json.dump(klines, f)

        result = load_market_volume(tmp_path)
        assert len(result) > 0
        # 第6天（2026-09-06）量比 = 150 / 100 = 1.5
        assert result.get('2026-09-06') == 1.5

    def test_market_vol_ratio_lookback_constant(self):
        # 大盘量比回看天数常量
        from src.analysis.record_truth import MARKET_VOL_LOOKBACK
        assert MARKET_VOL_LOOKBACK == 5

    def test_market_vol_ratio_high_vs_low(self):
        # 大盘放量 vs 缩量的边界值
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        # 放量
        entry_high = analyze_day(bars, 'sh600519', 100.0, market_vol_ratio=1.5)
        assert entry_high['market_vol_ratio'] > 1.0
        # 缩量
        entry_low = analyze_day(bars, 'sh600519', 100.0, market_vol_ratio=0.7)
        assert entry_low['market_vol_ratio'] < 1.0


# ---------------------------------------------------------------------------
# v2.8 新信号：榨干1分钟数据——6个新字段
# ---------------------------------------------------------------------------

class TestV28ExtractEveryDrop:
    def test_morning_afternoon_vol_ratio_basic(self):
        # 上午放量：上午量 > 下午量
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        volumes = [2000.0] * 120 + [1000.0] * 120  # 上午量是下午2倍
        for i, b in enumerate(bars):
            b['volume'] = volumes[i]
        ratio = compute_morning_afternoon_vol_ratio(bars, volumes)
        assert ratio is not None
        assert ratio > 1.0  # 上午放量

    def test_morning_afternoon_vol_ratio_afternoon_heavy(self):
        # 下午放量：下午量 > 上午量
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        volumes = [1000.0] * 120 + [2000.0] * 120
        for i, b in enumerate(bars):
            b['volume'] = volumes[i]
        ratio = compute_morning_afternoon_vol_ratio(bars, volumes)
        assert ratio is not None
        assert ratio < 1.0  # 下午放量

    def test_volume_peak_concentration_basic(self):
        # 量峰集中度：量最大的3分钟占比
        volumes = [100.0] * 100 + [1000.0, 1000.0, 1000.0]  # 3个巨量分钟
        conc = compute_volume_peak_concentration(volumes)
        assert conc is not None
        total = sum(volumes)
        expected = 3000.0 / total
        assert abs(conc - expected) < 0.01

    def test_volume_peak_concentration_uniform(self):
        # 量均匀时集中度低
        volumes = [100.0] * 100
        conc = compute_volume_peak_concentration(volumes)
        assert conc is not None
        assert conc == 0.03  # 3/100 = 3%

    def test_price_volume_divergence_no_divergence(self):
        # 无背离：价新高时量也放大
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.01  # 持续上涨
            b['high'] = b['close'] + 0.02
            b['low'] = b['close'] - 0.02
            if i == 99:  # 最后一天价最高，量也放大
                volumes[99] = 5000.0
                b['volume'] = 5000.0
        divergence = compute_price_volume_divergence(bars, volumes)
        assert divergence == 'no_divergence'

    def test_price_volume_divergence_top(self):
        # 顶背离：价新高但量不放大
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.01  # 持续上涨
            b['high'] = b['close'] + 0.02
            b['low'] = b['close'] - 0.02
            if i == 99:  # 最后一天价最高，但量不放大（仍为1000）
                pass
        divergence = compute_price_volume_divergence(bars, volumes)
        # 价创新高(99)，但量(1000)没有超过过去30分钟均量(1000)，应顶背离
        assert divergence == 'top_divergence'

    def test_wave_features_basic(self):
        # 量波特征基本功能
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        volumes = [1000.0] * 240
        vol_mean = 1000.0
        features = compute_wave_features(bars, volumes, vol_mean)
        assert features is not None
        assert 'wave_morning' in features
        assert 'wave_close' in features
        assert 'wave_pulses' in features
        # 量均匀时，早盘30分钟占比 = 30/240 = 0.125
        assert abs(features['wave_morning'] - 0.125) < 0.01
        assert features['wave_pulses'] == 0  # 量均匀，无脉冲

    def test_wave_features_pulses(self):
        # 脉冲数：量 > 均量×2 的分钟数
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        volumes = [1000.0] * 240
        volumes[0] = 3000.0   # 脉冲
        volumes[100] = 2500.0  # 脉冲
        vol_mean = sum(volumes) / len(volumes)
        features = compute_wave_features(bars, volumes, vol_mean)
        assert features is not None
        assert features['wave_pulses'] >= 2

    def test_analyze_day_v28_fields(self):
        # analyze_day 返回值包含 v2.8 字段
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        for field in ('morning_afternoon_vol_ratio', 'volume_peak_concentration',
                      'price_volume_divergence', 'wave_morning', 'wave_close', 'wave_pulses'):
            assert field in entry, f'缺少字段: {field}'


# ---------------------------------------------------------------------------
# v2.9 新信号：继续深挖——5个新字段
# ---------------------------------------------------------------------------

class TestV29Deeper:
    def test_close_in_amplitude_at_high(self):
        # 收在全天最高 → 接近1
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + i  # 持续上涨
            b['high'] = b['close']  # 最高=收盘（最后一根收在全天最高）
            b['low'] = 100
        cia = compute_close_in_amplitude(bars)
        assert cia is not None
        assert cia > 0.9

    def test_close_in_amplitude_at_low(self):
        # 收在全天最低 → 接近0
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 110 - i  # 持续下跌
            b['high'] = 110
            b['low'] = b['close']  # 最低=收盘（最后一根收在全天最低）
        cia = compute_close_in_amplitude(bars)
        assert cia is not None
        assert cia < 0.1

    def test_vwap_deviation_positive(self):
        # 收盘在VWAP上方 → 正值
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        volumes = [1000.0] * 10
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.5  # 持续上涨
        dev = compute_vwap_deviation(bars, volumes)
        assert dev is not None
        assert dev > 0

    def test_vwap_deviation_negative(self):
        # 收盘在VWAP下方 → 负值
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        volumes = [1000.0] * 10
        for i, b in enumerate(bars):
            b['close'] = 105 - i * 0.5  # 持续下跌
        dev = compute_vwap_deviation(bars, volumes)
        assert dev is not None
        assert dev < 0

    def test_realized_volatility_basic(self):
        # 已实现波动率基本功能
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 3 - 1) * 0.1
        rv = compute_realized_volatility(bars)
        assert rv is not None
        assert rv > 0

    def test_realized_volatility_low(self):
        # 价格几乎不动 → 波动率低
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        for b in bars:
            b['close'] = 100.0
        rv = compute_realized_volatility(bars)
        assert rv is not None
        assert rv == 0.0

    def test_up_down_minute_ratio_more_up(self):
        # 阳线分钟多 → 比值>1
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i % 3 != 0:  # 7根阳线，3根阴线
                b['close'] = b['open'] + 0.1
            else:
                b['close'] = b['open'] - 0.1
        ratio = compute_up_down_minute_ratio(bars)
        assert ratio is not None
        assert ratio > 1.0

    def test_gap_filled_up_gap(self):
        # 向上跳空，日内最低价≤前收 → 回补
        bars = make_bars(n=10, price=102.0, vol=1000.0)  # 开盘102，前收100
        bars[0]['open'] = 102.0
        for b in bars:
            b['high'] = max(b['open'], b['close']) + 0.5
            b['low'] = 99.0  # 日内最低99 ≤ 前收100，回补
        filled = compute_gap_filled(bars, 100.0)
        assert filled is True

    def test_gap_filled_no_gap(self):
        # 开盘=前收 → 无缺口，返回None
        bars = make_bars(n=10, price=100.0, vol=1000.0)
        bars[0]['open'] = 100.0
        filled = compute_gap_filled(bars, 100.0)
        assert filled is None

    def test_analyze_day_v29_fields(self):
        # analyze_day 返回值包含 v2.9 字段
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        for field in ('close_in_amplitude', 'vwap_deviation', 'realized_volatility',
                      'up_down_minute_ratio', 'gap_filled'):
            assert field in entry, f'缺少字段: {field}'


# ---------------------------------------------------------------------------
# v3.0 新信号：里程碑版本——国泰君安验证因子+趋势纯度+量价四象限
# ---------------------------------------------------------------------------

class TestV30Milestone:
    def test_return_skewness_positive(self):
        # 正偏：大涨分钟多（右尾厚）
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i % 10 == 0 and i > 0:
                b['close'] = b['close'] + 2.0  # 偶尔大涨
            else:
                b['close'] = b['close'] - 0.05  # 平时小跌
        skew = compute_return_skewness(bars)
        assert skew is not None
        assert skew > 0  # 正偏

    def test_return_skewness_negative(self):
        # 负偏：大跌分钟多（左尾厚）—— 用绝对价格构造
        bars = make_bars(n=50, price=100.0, vol=1000.0)
        # 构造：大部分分钟小涨，偶尔极端大跌
        prices = [100.0]
        for i in range(1, 50):
            if i % 10 == 0:
                prices.append(prices[-1] - 3.0)  # 极端大跌
            else:
                prices.append(prices[-1] + 0.05)  # 小涨
        for i, b in enumerate(bars):
            b['close'] = prices[i]
        skew = compute_return_skewness(bars)
        assert skew is not None
        assert skew < 0  # 负偏

    def test_return_kurtosis_high(self):
        # 高峰度：尖峰厚尾——大部分分钟极小波动（围绕均值），偶尔极端波动
        bars = make_bars(n=50, price=100.0, vol=1000.0)
        # 构造收益率：45个极小波动(±0.001交替) + 5个极端波动(±0.05)
        returns = []
        for i in range(50):
            if i % 10 == 0:
                returns.append(0.05)   # 极端大涨
            elif i % 10 == 5:
                returns.append(-0.05)  # 极端大跌
            else:
                returns.append(0.001 if i % 2 == 0 else -0.001)  # 极小波动
        # 转换为价格序列
        prices = [100.0]
        for r in returns:
            prices.append(prices[-1] * (1 + r))
        for i, b in enumerate(bars):
            b['close'] = prices[i]
        kurt = compute_return_kurtosis(bars)
        assert kurt is not None
        assert kurt > 3  # 尖峰厚尾

    def test_downside_vol_ratio(self):
        # 下行波动率占比基本功能
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 3 - 1) * 0.5
        dvr = compute_downside_vol_ratio(bars)
        assert dvr is not None
        assert 0 <= dvr <= 1.5  # 合理范围

    def test_vwap_cross_count_trend_day(self):
        # 趋势日：价格持续在VWAP一侧，穿越次数少
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.1  # 持续上涨
            b['volume'] = volumes[i]
        cross = compute_vwap_cross_count(bars, volumes)
        assert cross is not None
        assert cross <= 5  # 趋势日穿越少

    def test_vwap_cross_count_range_day(self):
        # 震荡日：价格围绕VWAP震荡，穿越次数多
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 10 - 5) * 0.2  # 围绕100震荡
            b['volume'] = volumes[i]
        cross = compute_vwap_cross_count(bars, volumes)
        assert cross is not None
        assert cross >= 3  # 震荡日穿越多

    def test_price_path_efficiency_high(self):
        # 高效率：价格直线运动
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.1  # 直线上涨
        eff = compute_price_path_efficiency(bars)
        assert eff is not None
        assert eff > 0.8  # 高效率

    def test_price_path_efficiency_low(self):
        # 低效率：价格剧烈震荡后回到原点
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 4 - 1.5) * 1.0  # 剧烈震荡
        eff = compute_price_path_efficiency(bars)
        assert eff is not None
        assert eff < 0.3  # 低效率

    def test_max_consecutive_up(self):
        # 最大连续上涨——构造干净的连续上涨段（前后平盘，不下跌）
        bars = make_bars(n=20, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            if i < 5:
                b['close'] = 100.0  # 平盘
            elif 5 <= i <= 13:  # 第5到13根，连续9根上涨
                b['close'] = 100.0 + (i - 4) * 0.1  # i=5→100.1, i=13→100.9
            else:
                b['close'] = 100.9  # 平盘（保持在最高位100.9，不下跌）
        max_up, max_down = compute_max_consecutive(bars)
        assert max_up >= 8  # 至少连续8分钟上涨
        assert max_down == 0  # 没有下跌分钟

    def test_volume_price_quadrants(self):
        # 量价四象限基本功能
        bars = make_bars(n=20, price=100.0, vol=1000.0)
        volumes = [1000.0] * 20
        for i in range(1, 20):
            if i % 4 == 1:  # 量增价涨
                volumes[i] = 1500.0
                bars[i]['close'] = 101.0
            elif i % 4 == 2:  # 量缩价涨
                volumes[i] = 500.0
                bars[i]['close'] = 102.0
            elif i % 4 == 3:  # 量增价跌
                volumes[i] = 1500.0
                bars[i]['close'] = 101.0
            else:  # 量缩价跌
                volumes[i] = 500.0
                bars[i]['close'] = 100.0
        vupu, vdpu, vupd, vdpd = compute_volume_price_quadrants(bars, volumes)
        total = vupu + vdpu + vupd + vdpd
        assert total > 0
        assert vupu > 0 and vdpu > 0 and vupd > 0 and vdpd > 0

    def test_analyze_day_v30_fields(self):
        # analyze_day 返回值包含 v3.0 字段（12个）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        v30_fields = (
            'return_skewness', 'return_kurtosis', 'downside_vol_ratio',
            'vwap_cross_count', 'price_path_efficiency',
            'max_consecutive_up', 'max_consecutive_down',
            'vol_up_price_up_minutes', 'vol_down_price_up_minutes',
            'vol_up_price_down_minutes', 'vol_down_price_down_minutes',
        )
        for field in v30_fields:
            assert field in entry, f'缺少字段: {field}'


# ---------------------------------------------------------------------------
# v3.1 新信号：Volume Profile——从价格维度看量分布
# ---------------------------------------------------------------------------

class TestV31VolumeProfile:
    def test_volume_profile_basic(self):
        # 基本功能：返回字典包含8个字段
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 10 - 5) * 0.5
            b['high'] = b['close'] + 1.0
            b['low'] = b['close'] - 1.0
        vp = compute_volume_profile(bars, volumes)
        assert vp is not None
        for field in ('poc_price', 'value_area_high', 'value_area_low',
                      'value_area_width', 'close_in_value_area',
                      'poc_volume_ratio', 'high_volume_nodes', 'low_volume_nodes'):
            assert field in vp, f'缺少字段: {field}'

    def test_volume_profile_poc_in_range(self):
        # POC价格在全天价格范围内
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 10 - 5) * 0.5
            b['high'] = b['close'] + 1.0
            b['low'] = b['close'] - 1.0
        vp = compute_volume_profile(bars, volumes)
        assert vp is not None
        day_high = max(b['high'] for b in bars)
        day_low = min(b['low'] for b in bars)
        assert day_low <= vp['poc_price'] <= day_high

    def test_volume_profile_value_area(self):
        # 价值区间：VAH >= VAL，宽度>0
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 10 - 5) * 0.5
            b['high'] = b['close'] + 1.0
            b['low'] = b['close'] - 1.0
        vp = compute_volume_profile(bars, volumes)
        assert vp is not None
        assert vp['value_area_high'] >= vp['value_area_low']
        assert vp['value_area_width'] > 0

    def test_volume_profile_concentrated(self):
        # 量能集中在单一价位：POC量占比高
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [100.0] * 100
        # 让50根bar的收盘价都在100附近，且量很大
        for i in range(50):
            bars[i]['close'] = 100.0
            bars[i]['high'] = 100.5
            bars[i]['low'] = 99.5
            volumes[i] = 5000.0  # 大量
        for i in range(50, 100):
            bars[i]['close'] = 105.0 + (i - 50) * 0.1
            bars[i]['high'] = bars[i]['close'] + 0.5
            bars[i]['low'] = bars[i]['close'] - 0.5
        vp = compute_volume_profile(bars, volumes)
        assert vp is not None
        assert vp['poc_volume_ratio'] > 0.2  # POC量占比>20%（集中）

    def test_volume_profile_wide_range(self):
        # 价格波动大：价值区间宽度大
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 20 - 10) * 2.0  # 大幅波动
            b['high'] = b['close'] + 2.0
            b['low'] = b['close'] - 2.0
        vp = compute_volume_profile(bars, volumes)
        assert vp is not None
        assert vp['value_area_width'] > 5  # 宽度大

    def test_volume_profile_insufficient_data(self):
        # 数据不足：返回None
        bars = make_bars(n=5, price=100.0, vol=1000.0)
        volumes = [1000.0] * 5
        vp = compute_volume_profile(bars, volumes)
        assert vp is None

    def test_analyze_day_v31_fields(self):
        # analyze_day 返回值包含 v3.1 字段（8个）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        v31_fields = (
            'poc_price', 'value_area_high', 'value_area_low', 'value_area_width',
            'close_in_value_area', 'poc_volume_ratio',
            'high_volume_nodes', 'low_volume_nodes',
        )
        for field in v31_fields:
            assert field in entry, f'缺少字段: {field}'


# ---------------------------------------------------------------------------
# v3.2 新信号：VWAP深入应用——斜率+标准差带
# ---------------------------------------------------------------------------

class TestV32VWAPDeep:
    def test_vwap_slope_up(self):
        # VWAP斜率为正（上行趋势）：价格持续上涨
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + i * 0.1  # 持续上涨
            b['volume'] = volumes[i]
        slope, direction = compute_vwap_slope(bars, volumes)
        assert slope is not None
        assert slope > 0  # 正斜率
        assert direction == 'up'

    def test_vwap_slope_down(self):
        # VWAP斜率为负（下行趋势）：价格持续下跌
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 110 - i * 0.1  # 持续下跌
            b['volume'] = volumes[i]
        slope, direction = compute_vwap_slope(bars, volumes)
        assert slope is not None
        assert slope < 0  # 负斜率
        assert direction == 'down'

    def test_vwap_slope_flat(self):
        # VWAP斜率接近0（震荡）：价格围绕均值波动
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 4 - 1.5) * 0.01  # 极小波动
            b['volume'] = volumes[i]
        slope, direction = compute_vwap_slope(bars, volumes)
        assert slope is not None
        assert direction == 'flat'

    def test_vwap_std_basic(self):
        # VWAP标准差带基本功能
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 10 - 5) * 0.5
            b['volume'] = volumes[i]
        vstd, zscore, band = compute_vwap_std_band(bars, volumes)
        assert vstd is not None
        assert vstd > 0
        assert zscore is not None
        assert band is not None

    def test_vwap_std_high_volatility(self):
        # 高波动：VWAP标准差大
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 4 - 1.5) * 5.0  # 大幅波动
            b['volume'] = volumes[i]
        vstd, _, _ = compute_vwap_std_band(bars, volumes)
        assert vstd is not None
        assert vstd > 1.0  # 标准差大

    def test_vwap_zscore_extreme(self):
        # 极端z-score：收盘极端偏离VWAP
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        # 前99分钟在100附近震荡，最后1分钟暴涨
        for i in range(99):
            bars[i]['close'] = 100 + (i % 4 - 1.5) * 0.1
            bars[i]['volume'] = volumes[i]
        bars[99]['close'] = 110.0  # 最后暴涨10%
        bars[99]['volume'] = 5000.0
        vstd, zscore, band = compute_vwap_std_band(bars, volumes)
        assert zscore is not None
        assert zscore > 1.0  # 正的极端z-score

    def test_analyze_day_v32_fields(self):
        # analyze_day 返回值包含 v3.2 字段（5个）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        v32_fields = (
            'vwap_slope', 'vwap_slope_direction', 'vwap_std',
            'price_vwap_zscore', 'vwap_band_position',
        )
        for field in v32_fields:
            assert field in entry, f'缺少字段: {field}'


# ---------------------------------------------------------------------------
# v3.3 新信号：开盘5分钟/尾盘5分钟独立特征——时段博弈
# ---------------------------------------------------------------------------

class TestV33OpenClose5min:
    def test_open_5min_return_positive(self):
        # 开盘5分钟上涨
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        bars[0]['open'] = 100.0
        for i in range(5):
            bars[i]['close'] = 100 + (i + 1) * 0.5  # 前5分钟持续上涨
            bars[i]['volume'] = volumes[i]
        for i in range(5, 100):
            bars[i]['close'] = 102.5
            bars[i]['volume'] = volumes[i]
        result = compute_open_close_5min(bars, volumes)
        assert result is not None
        assert result['open_5min_return'] > 0

    def test_close_5min_pull(self):
        # 尾盘拉升
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i in range(95):
            bars[i]['close'] = 100.0
            bars[i]['volume'] = volumes[i]
        for i in range(95, 100):
            bars[i]['close'] = 100 + (i - 94) * 0.5  # 最后5分钟持续上涨
            bars[i]['volume'] = volumes[i]
        result = compute_open_close_5min(bars, volumes)
        assert result is not None
        assert result['close_5min_return'] > 0
        assert result['close_5min_pull_or_push'] == 'pull'

    def test_close_5min_push(self):
        # 尾盘打压
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        for i in range(95):
            bars[i]['close'] = 100.0
            bars[i]['volume'] = volumes[i]
        for i in range(95, 100):
            bars[i]['close'] = 100 - (i - 94) * 0.5  # 最后5分钟持续下跌
            bars[i]['volume'] = volumes[i]
        result = compute_open_close_5min(bars, volumes)
        assert result is not None
        assert result['close_5min_return'] < 0
        assert result['close_5min_pull_or_push'] == 'push'

    def test_open_5min_volume_ratio(self):
        # 开盘5分钟量占比：早盘放量时占比高
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [100.0] * 100
        for i in range(5):
            volumes[i] = 5000.0  # 前5分钟巨量
            bars[i]['volume'] = volumes[i]
        for i in range(5, 100):
            bars[i]['volume'] = volumes[i]
        result = compute_open_close_5min(bars, volumes)
        assert result is not None
        assert result['open_5min_volume_ratio'] > 0.2  # 早盘量占比>20%

    def test_open_close_return_diff_high_open_low_close(self):
        # 冲高回落：开盘涨，尾盘跌 → 涨跌差为正
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [1000.0] * 100
        bars[0]['open'] = 100.0
        for i in range(5):
            bars[i]['close'] = 100 + (i + 1) * 0.5  # 开盘上涨
            bars[i]['volume'] = volumes[i]
        for i in range(5, 95):
            bars[i]['close'] = 102.5
            bars[i]['volume'] = volumes[i]
        for i in range(95, 100):
            bars[i]['close'] = 102.5 - (i - 94) * 0.5  # 尾盘下跌
            bars[i]['volume'] = volumes[i]
        result = compute_open_close_5min(bars, volumes)
        assert result is not None
        assert result['open_close_return_diff'] > 0  # 冲高回落

    def test_open_close_volume_ratio(self):
        # 开盘/尾盘量比：早盘放量时比值大
        bars = make_bars(n=100, price=100.0, vol=1000.0)
        volumes = [100.0] * 100
        for i in range(5):
            volumes[i] = 5000.0  # 前5分钟巨量
            bars[i]['volume'] = volumes[i]
        for i in range(95, 100):
            volumes[i] = 100.0  # 尾盘正常量
            bars[i]['volume'] = volumes[i]
        for i in range(5, 95):
            bars[i]['volume'] = volumes[i]
        result = compute_open_close_5min(bars, volumes)
        assert result is not None
        assert result['open_close_volume_ratio'] > 5  # 开盘量是尾盘的5倍以上

    def test_analyze_day_v33_fields(self):
        # analyze_day 返回值包含 v3.3 字段（7个）
        bars = make_bars(n=240, price=100.0, vol=1000.0)
        for i, b in enumerate(bars):
            b['close'] = 100 + (i % 5) * 0.02
            b['high'] = b['close'] + 0.03
            b['low'] = b['close'] - 0.03
        entry = analyze_day(bars, 'sh600519', 100.0)
        assert entry is not None
        v33_fields = (
            'open_5min_return', 'open_5min_volume_ratio',
            'close_5min_return', 'close_5min_volume_ratio',
            'close_5min_pull_or_push', 'open_close_return_diff',
            'open_close_volume_ratio',
        )
        for field in v33_fields:
            assert field in entry, f'缺少字段: {field}'


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
