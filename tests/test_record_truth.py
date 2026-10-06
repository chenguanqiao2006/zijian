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


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
