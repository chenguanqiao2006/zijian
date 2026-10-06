#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/analysis/record_truth.py — 真假量柱账本分析器 v2.7（zijian 移植版）
==========================================================================

职责链：
    读取 data/kline_1min/ 下的 1 分钟 K 线
      → 四指标投票（CV / 量价相关性 / 尾盘占比 / 分时均匀度）
      → 判定「真金白银 / 疑似量化 / 量化对倒」（涨跌停日豁免）
      → 写入按月分片账本 data/analysis/truth_ledger/YYYY-MM.json
      → 验证落盘成功后删除原始 1 分钟数据（先删后提交，仓库不膨胀）

v2.2 相对 v2.1 的变更：
    [新增] filter_session 兜底过滤 —— 每日 K 线只保留连续竞价时段
           （09:30-11:30 / 13:00-15:00），并裁掉尾部连续零量行。

v2.3 相对 v2.2 的变更（三大新增信号，只记录、暂不入投票）：
    [新增] flat_vol_ratio  平价放量占比 —— bar内 |收-开| ≤ 1个tick(0.01元)
           且量 ≥ 2×当日分钟均量 的分钟数 / 有成交分钟数。
           「价不动、量在动」是对倒成交最直接的指纹。
    [新增] tail_gain       尾盘30分钟涨幅 —— (末根close/尾窗前一根close)-1。
           正值+量增=真拉升；≈0+量增=对倒护盘嫌疑。
    [新增] zero_vol_mins   零成交分钟数（尾部幽灵行已由 filter_session 裁剪，
           此处统计的是盘中真实的零成交）。
    设计原则：与 v1/v2 历史账目保持判定口径一致 —— 三个新字段只存不投，
    不影响 verdict / quant_pct / 四指标投票；待 2026-11-01 阈值体检
    给出新字段的真实分布后，再决定是否纳入投票体系。

v2.4 相对 v2.3 的变更（六大新增信号，只记录、暂不入投票）：
    [新增] big_order_minutes     大单分钟数 —— 量 > 当日均量×3 的分钟数。
    [新增] big_order_ratio       大单分钟占比 —— 大单分钟数 / 有成交分钟数。
    [新增] main_net_inflow       主力净流入估算（手）—— 阳线分钟量 - 阴线分钟量。
           基于1分钟OHLCV的粗略估算（无逐笔数据时的近似算法）：
           阳线分钟视为主动买入，阴线分钟视为主动卖出，平盘分钟平分。
    [新增] main_net_inflow_pct   主力净流入占比 —— 净流入 / 总成交量。
    [新增] big_order_net_inflow  大单净流入（手）—— 放量阳线量 - 放量阴线量。
           只统计"大单分钟"（量>均量×3）的买卖方向，过滤散户噪声。
    [新增] order_flow_imbalance  订单流失衡 —— (阳量-阴量)/(阳量+阴量)，范围[-1,1]。
           +1=全天买入主导，-1=全天卖出主导，0=买卖均衡。
    设计原则：与 v2.3 一致 —— 六个新字段只存不投，不影响 verdict / quant_pct；
    待积累足够数据后做阈值体检，再决定是否纳入投票或独立输出。

v2.5 相对 v2.4 的变更（分时形态识别，只记录、暂不入投票）：
    [新增] amplitude           全天振幅（%）= (最高-最低)/前收 × 100。
    [新增] morning_return      上午涨跌幅 = (11:30收盘/开盘)-1。
    [新增] afternoon_return    下午涨跌幅 = (收盘/13:00开盘)-1。
    [新增] open_gap_pct        开盘缺口（%）= (开盘/前收-1) × 100。
    [新增] high_time_idx       全天最高价出现的分钟索引（0-239，0=09:30）。
    [新增] low_time_idx        全天最低价出现的分钟索引（0-239）。
    [新增] pattern             分时形态标签（9种互斥，按优先级判定）：
           sideways            横盘（振幅<1%）
           tail_rally          尾盘拉升（尾盘涨>1%且为全天最强时段）
           tail_dive           尾盘跳水（尾盘跌>1%）
           v_shape             V型反转（上午最低+下午最高+振幅>2%）
           inverted_v_shape    倒V型（上午最高+下午最低+振幅>2%）
           morning_pullback    早盘冲高回落（最高在前30分钟+回落>1%）
           one_side_up         单边上涨（收盘接近最高+上午弱下午强）
           one_side_down       单边下跌（收盘接近最低+上午强下午弱）
           no_clear_pattern    无明显形态
    设计原则：与 v2.3/v2.4 一致 —— 只存不投，先积累数据再做阈值体检。

v2.6 相对 v2.5 的变更（移植 yaox2004-web/one v3.0 核心能力）：
    [重大改进] 双轨判定 —— 有≥5天历史时用相对分位（和自己过去20天比），
               历史不足时用绝对阈值兜底。解决不同股票量性差异问题。
    [重大改进] 校准阈值 —— CV≤0.5→0.95，尾盘≥0.3→0.22（原阈值严重脱靶，
               ~90%误判"疑似量化"，校准基于2026-09账本实测分布）。
    [新增] vwap_hold_ratio  VWAP持有比例 —— 价格在VWAP上方的时间占比，
           反映主力护盘强度（人线 vs 天线）。
    [新增] weave_score       织布机评分 —— 价格在VWAP±1.5%内的时间占比，
           量化对倒的直接特征（价格不动、量在动）。
    [新增] pm_reversal       午后反转 —— 上午/下午方向相反=1，相同=0，
           波动太小=None。
    [新增] 指数不入账本 —— sh000001/sz399001/sz399006 跳过，避免稀释统计。
    [新增] verdict_basis     判定依据字段 —— "相对分位"或"绝对阈值"，
           便于回测时按口径过滤。
    设计原则：判定逻辑（verdict/is_real/quant_pct）采用双轨+校准阈值，
    与 v2.5 不兼容（阈值变更）；新增行为指纹字段只记录不入投票。

v2.7 相对 v2.6 的变更（大盘量比，移植 yaox v3.0）：
    [新增] market_vol_ratio  大盘量比 —— 上证指数当日成交量 / 过去5日平均成交量。
           >1=大盘放量，<1=大盘缩量。用于区分"个股放量是跟随大盘还是独立行情"。
           数据来源：data/kline/sh/sh000001.json（上证指数日线，需提前拉取）。
           若指数日线数据缺失，该字段为 None，不影响其他判定。
    设计原则：只记录不入投票，先积累数据再做阈值体检。

zijian 移植版改动：
    - 路径统一经 src/data/paths.py（目录宪法），不再硬编码
    - 从 scripts/ 移到 src/analysis/，支持模块导入 + 脚本运行
    - 核心分析逻辑与 aaa 版 v2.3 完全一致，判定口径不变
    - v2.4 为 zijian 版新增（aaa 库尚未升级到 v2.4）

用法：
    python -m src.analysis.record_truth               # 正常运行
    python -m src.analysis.record_truth --dry-run     # 只分析、不写账本、不删源文件
    python -m src.analysis.record_truth --no-delete   # 写账本、但保留源文件

纯标准库，无第三方依赖。
"""

import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 路径统一经目录宪法（src/data/paths.py）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # src/
from data.paths import min1_dir, kline_dir, ledger_dir, validate_code

CST = timezone(timedelta(hours=8))
MIN_FULL_DAY_BARS = 230

# --- 判定阈值（集中一处，调参只改这里） ---
THRESH = {
    'cv':        0.5,
    'corr':      0.3,
    'tail':      0.3,
    'flatness':  0.25,
}

SESSION_SPLITS = [
    ('开盘30分',   0,  30),
    ('上午前段',  30,  90),
    ('午前',      90, 120),
    ('午后',     120, 180),
    ('尾盘前',   180, 210),
    ('尾盘30分', 210, 240),
]

# --- v2.3 新信号参数 ---
TICK_SIZE = 0.011        # 平价判定：|收-开| ≤ 约1个tick（A股统一0.01元，留浮点余量）
HEAVY_VOL_MULT = 2.0     # 放量判定：分钟量 ≥ 2 × 当日分钟均量

# --- v2.4 新信号参数 ---
BIG_ORDER_VOL_MULT = 3.0  # 大单分钟判定：分钟量 > 当日均量 × 3（过滤散户噪声）

# --- v2.5 新信号参数：分时形态识别 ---
SIDEWAYS_AMP = 1.0        # 横盘振幅阈值（%），低于此值判为横盘
TAIL_RALLY_PCT = 1.0      # 尾盘拉升阈值（%），尾盘涨幅超过此值
V_SHAPE_AMP = 2.0         # V型/倒V型振幅阈值（%）
MORNING_PULLBACK_PCT = 1.0  # 早盘冲高回落阈值（%），从最高回落超过此值
CLOSE_NEAR_HIGH = 0.99    # 单边上涨：收盘价 >= 最高价 × 此值
CLOSE_NEAR_LOW = 1.01     # 单边下跌：收盘价 <= 最低价 × 此值

# --- v2.6 新参数：双轨判定 + 校准阈值（移植 yaox v3.0） ---
# 校准后的绝对阈值（基于2026-09账本实测分布，原阈值严重脱靶）
CV_ABS_QUANT = 0.95       # CV ≤ 0.95（原 0.5，~90%误判"疑似量化"）
TAIL_ABS_QUANT = 0.22     # 尾盘占比 ≥ 0.22（原 0.3）
CORR_ABS_QUANT = 0.30     # 量价相关 < 0.30（保持不变）
# 相对分位判定参数
HISTORY_LOOKBACK = 20     # 历史回看天数
MIN_HISTORY_FOR_RELATIVE = 5  # 最少历史天数，低于此值用绝对阈值兜底
CV_RANK_LOW = 0.20        # CV 分位 ≤ 20% 视为异常低
TAIL_RANK_HIGH = 0.80     # 尾盘分位 ≥ 80% 视为异常高

# --- v2.6 新参数：行为指纹（移植 yaox v3.0） ---
WEAVE_BAND = 0.015        # 织布机判定带宽：|close/vwap-1| < 1.5%
PM_MIN_MOVE = 0.001       # 午后反转判定的最小波动（0.1%）

# --- v2.6 指数不入账本 ---
INDEX_CODES = {"sh000001", "sz399001", "sz399006"}

# --- v2.7 大盘量比参数 ---
MARKET_VOL_LOOKBACK = 5  # 大盘量比的回看天数（过去5日平均成交量）


# ---------------------------------------------------------------------------
# 北交所过滤（兜底；主过滤在 fetch_quotes.py）
# ---------------------------------------------------------------------------

def is_bj(code: str) -> bool:
    c = (code or '').lower().replace('.bj', '').strip()
    if not c:
        return False
    if c.startswith('bj'):
        return True
    digits = c[2:] if (len(c) > 2 and c[:2] in ('sh', 'sz')) else c
    return digits.startswith(('920', '83', '87', '43'))


# ---------------------------------------------------------------------------
# 涨跌停规则（无北交所分支）
# ---------------------------------------------------------------------------

def limit_pct_for(code: str) -> float:
    if code.startswith(('sz30', 'sh68')):
        return 0.198       # 创业板 / 科创板 ±20%
    return 0.098           # 主板 ±10%


def min_bars_for(code: str) -> int:
    return MIN_FULL_DAY_BARS


# ---------------------------------------------------------------------------
# 数据解析层：兼容字符串 / 数组 / 字典三种 K 线格式
# ---------------------------------------------------------------------------

def extract_bars_payload(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ('data', 'bars', 'klines', 'kline'):
            v = obj.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for k2 in ('klines', 'data', 'bars'):
                    v2 = v.get(k2)
                    if isinstance(v2, list):
                        return v2
    return None


def _looks_like_time(x) -> bool:
    if isinstance(x, (int, float)):
        return x > 10_000
    s = str(x).strip()
    if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', s):
        return True
    if s.isdigit() and len(s) >= 8:
        return True
    return False


def normalize_bar(item):
    try:
        if isinstance(item, dict):
            g = lambda *ks: next((item[k] for k in ks if item.get(k) is not None), None)
            return {
                'time':   g('time', 't', 'datetime', 'dt', 'date'),
                'open':   float(g('open', 'o', 0)),
                'high':   float(g('high', 'h', 0)),
                'low':    float(g('low', 'l', 0)),
                'close':  float(g('close', 'c', 0)),
                'volume': float(g('volume', 'vol', 'v', 0)),
            }
        if isinstance(item, str):
            parts = [p.strip() for p in item.split(',')]
            if len(parts) >= 6 and _looks_like_time(parts[0]):
                return {
                    'time':   parts[0],
                    'open':   float(parts[1]),
                    'high':   float(parts[2]),
                    'low':    float(parts[3]),
                    'close':  float(parts[4]),
                    'volume': float(parts[5]),
                }
            return None
        if isinstance(item, (list, tuple)) and len(item) >= 6:
            if _looks_like_time(item[0]):
                return {
                    'time':   item[0],
                    'open':   float(item[1]),
                    'high':   float(item[2]),
                    'low':    float(item[3]),
                    'close':  float(item[4]),
                    'volume': float(item[5]),
                }
            return None
    except (ValueError, TypeError):
        return None
    return None


def extract_date(t):
    if t is None:
        return None
    if isinstance(t, (int, float)):
        ts = t / 1000 if t > 1e12 else t
        try:
            return datetime.fromtimestamp(ts, tz=CST).strftime('%Y-%m-%d')
        except (OverflowError, OSError, ValueError):
            return None
    s = str(t).strip()
    if s.isdigit() and len(s) >= 8:
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    m = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    return None


# ---------------------------------------------------------------------------
# 幽灵K线兜底过滤（v2.2 引入）
# ---------------------------------------------------------------------------

def filter_session(bars):
    """只保留连续竞价时段（09:30-11:30 / 13:00-15:00），
    并裁掉尾部连续零量行（最多 30 根，防止误伤真实缩量尾盘）。"""
    def in_session(t):
        m = re.search(r'(\d{1,2}):(\d{2})', str(t))
        if not m:
            return True                 # 无时间信息的行保守保留
        v = int(m.group(1)) * 60 + int(m.group(2))
        return (570 <= v <= 690) or (780 <= v <= 900)

    def _vol(b):
        try:
            return float(b.get('volume') or 0)
        except (TypeError, ValueError):
            return 0.0

    kept = [b for b in bars if in_session(b['time'])]
    cut = 0
    while kept and cut < 30 and _vol(kept[-1]) <= 0:
        kept.pop()
        cut += 1
    return kept


def load_and_group_days(path: Path):
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f'[WARN] {path.name} JSON 解析失败: {e}')
        return None
    payload = extract_bars_payload(obj)
    if not payload:
        print(f'[WARN] {path.name} 未识别到 K 线数据，跳过')
        return None
    bars = [b for b in (normalize_bar(x) for x in payload) if b]
    if not bars:
        print(f'[WARN] {path.name} K 线全部无法解析，跳过')
        return None
    bars.sort(key=lambda b: str(b['time']))
    days = {}
    for b in bars:
        d = extract_date(b['time'])
        if d:
            days.setdefault(d, []).append(b)
    if not days:
        print(f'[WARN] {path.name} 时间字段无日期信息，跳过')
    else:
        for d in days:
            days[d] = filter_session(days[d])   # 每天先过滤再分析
    return days


def resolve_code(path: Path) -> str:
    stem = path.stem
    if stem.lower().startswith(('sh', 'sz', 'bj')):
        return stem.lower()
    parent = path.parent.name.lower()
    if parent in ('sh', 'sz', 'bj'):
        return parent + stem
    return stem.lower()


# ---------------------------------------------------------------------------
# prev_close 加载（涨跌停检测用）
# ---------------------------------------------------------------------------

def load_prev_close(code: str, target_date: str, _cache={}):
    if code in _cache:
        daily = _cache[code]
    else:
        daily = None
        # 经目录宪法：kline_dir() / {market} / {code}.json
        for cand in (kline_dir() / f'{code[:2]}' / f'{code}.json',
                     kline_dir() / f'{code}.json'):
            if cand.exists():
                try:
                    obj = json.loads(cand.read_text(encoding='utf-8'))
                    payload = extract_bars_payload(obj) or []
                    daily = []
                    for item in payload:
                        if isinstance(item, str):
                            p = [x.strip() for x in item.split(',')]
                        elif isinstance(item, (list, tuple)):
                            p = item
                        else:
                            continue
                        d = extract_date(p[0]) if p else None
                        if d and len(p) >= 5:
                            try:
                                daily.append((d, float(p[4])))
                            except (ValueError, TypeError):
                                pass
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                break
        _cache[code] = daily
    if not daily:
        return None
    before = [c for d, c in daily if d < target_date]
    return before[-1] if before else None


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------

def safe_corr(xs, ys):
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    r = cov / math.sqrt(vx * vy)
    return max(-1.0, min(1.0, r))


def session_volume_profile(volumes):
    total = sum(volumes)
    if total <= 0:
        return None
    n = len(volumes)
    return [sum(volumes[min(a, n):min(b, n)]) / total for _, a, b in SESSION_SPLITS]


def flatness_score(profile):
    if not profile:
        return None
    u = 1.0 / len(profile)
    return sum(abs(p - u) for p in profile)


def build_feature_snapshot(volumes):
    """240 根 1 分钟 → 24 个 10 分钟桶占比（4 位小数，体积友好）。"""
    n = 24
    buckets = [0.0] * n
    for i, v in enumerate(volumes):
        buckets[min(i // 10, n - 1)] += v
    total = sum(buckets)
    if total <= 0:
        return None
    return [round(b / total, 4) for b in buckets]


# ---------------------------------------------------------------------------
# v2.3 新增指标
# ---------------------------------------------------------------------------

def compute_flat_vol_ratio(bars, volumes, mean_vol):
    """平价放量占比：bar 内 |close-open| ≤ 1个tick 且 量 ≥ 2×当日分钟均量
    的分钟数 / 有成交分钟数。对倒（价不动量在动）最直接的指纹。
    注：用绝对 tick 阈值而非相对百分比，因为 A 股所有股票 tick 统一为
    0.01 元，在 tick 空间里各价位的判定标准才一致。"""
    if mean_vol <= 0:
        return None
    active, hits = 0, 0
    for b, v in zip(bars, volumes):
        if v > 0:
            active += 1
            o, c = b['open'], b['close']
            if o > 0 and abs(c - o) <= TICK_SIZE and v >= HEAVY_VOL_MULT * mean_vol:
                hits += 1
    return hits / active if active > 0 else None


def compute_tail_gain(bars):
    """尾盘30分钟涨幅：(末根close / 尾窗前一根close) - 1。
    配合 tail_ratio 使用：量增价升=真拉升；量增价平=对倒护盘嫌疑。"""
    if len(bars) < 31:
        return None
    base = bars[-31]['close']
    if not base:
        return None
    return bars[-1]['close'] / base - 1.0


# ---------------------------------------------------------------------------
# v2.4 新增指标：大单拆分 + 主力净流入
# ---------------------------------------------------------------------------

def compute_big_order_stats(bars, volumes, mean_vol):
    """v2.4 六大指标一次性计算（基于1分钟OHLCV，无逐笔数据时的近似算法）。

    返回字典：
        big_order_minutes     大单分钟数（量 > 均量×BIG_ORDER_VOL_MULT）
        big_order_ratio       大单分钟占比（大单分钟数 / 有成交分钟数）
        main_net_inflow       主力净流入估算（手）= 阳线分钟量 - 阴线分钟量
        main_net_inflow_pct   主力净流入占比 = 净流入 / 总成交量
        big_order_net_inflow  大单净流入（手）= 放量阳线量 - 放量阴线量
        order_flow_imbalance  订单流失衡 = (阳量-阴量)/(阳量+阴量)，范围[-1,1]

    算法说明：
        - 阳线分钟(close>open)：成交量归为主动买入
        - 阴线分钟(close<open)：成交量归为主动卖出
        - 平盘分钟(close==open)：成交量平分为买入和卖出
        - 大单分钟：量 > 当日均量 × BIG_ORDER_VOL_MULT（默认3倍）
        - 这是无逐笔数据时的近似估算，精度低于Level-2数据，但趋势可参考
    """
    if mean_vol <= 0:
        return None

    big_threshold = mean_vol * BIG_ORDER_VOL_MULT
    active_mins = 0          # 有成交分钟数
    big_order_mins = 0       # 大单分钟数
    yang_vol = 0.0           # 阳线分钟总成交量
    yin_vol = 0.0            # 阴线分钟总成交量
    big_yang_vol = 0.0       # 大单阳线分钟总成交量
    big_yin_vol = 0.0        # 大单阴线分钟总成交量

    for b, v in zip(bars, volumes):
        if v <= 0:
            continue
        active_mins += 1
        o, c = b['open'], b['close']
        is_big = v > big_threshold
        if is_big:
            big_order_mins += 1

        if c > o:  # 阳线 → 主动买入
            yang_vol += v
            if is_big:
                big_yang_vol += v
        elif c < o:  # 阴线 → 主动卖出
            yin_vol += v
            if is_big:
                big_yin_vol += v
        else:  # 平盘 → 买卖平分
            yang_vol += v / 2
            yin_vol += v / 2
            if is_big:
                big_yang_vol += v / 2
                big_yin_vol += v / 2

    total_vol = yang_vol + yin_vol
    if total_vol <= 0 or active_mins <= 0:
        return None

    main_net_inflow = yang_vol - yin_vol
    big_order_net_inflow = big_yang_vol - big_yin_vol

    return {
        'big_order_minutes': big_order_mins,
        'big_order_ratio': round(big_order_mins / active_mins, 4),
        'main_net_inflow': round(main_net_inflow, 1),
        'main_net_inflow_pct': round(main_net_inflow / total_vol, 4),
        'big_order_net_inflow': round(big_order_net_inflow, 1),
        'order_flow_imbalance': round(
            (yang_vol - yin_vol) / total_vol, 4) if total_vol > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# v2.5 新增指标：分时形态识别
# ---------------------------------------------------------------------------

def _find_morning_end_idx(bars):
    """找到上午最后一根K线索引（11:30附近，时间<=11:30的最后一根）。"""
    for i in range(len(bars) - 1, -1, -1):
        t = str(bars[i]['time'])
        m = re.search(r'(\d{1,2}):(\d{2})', t)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh < 12 or (hh == 11 and mm <= 30):
                return i
    return len(bars) // 2  # 兜底：取中间


def _find_afternoon_start_idx(bars):
    """找到下午第一根K线索引（13:00附近，时间>=13:00的第一根）。"""
    for i, b in enumerate(bars):
        t = str(b['time'])
        m = re.search(r'(\d{1,2}):(\d{2})', t)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if hh >= 13:
                return i
    return len(bars) // 2  # 兜底：取中间


def compute_pattern_stats(bars, prev_close):
    """v2.5 分时形态识别（基于1分钟时间序列）。

    返回字典：
        amplitude           全天振幅（%）= (最高-最低)/前收 × 100
        morning_return      上午涨跌幅 = (上午末根收盘/开盘)-1
        afternoon_return    下午涨跌幅 = (收盘/下午首根开盘)-1
        open_gap_pct        开盘缺口（%）= (开盘/前收-1) × 100
        high_time_idx       全天最高价出现的分钟索引（0-based）
        low_time_idx        全天最低价出现的分钟索引（0-based）
        pattern             形态标签（9种互斥）
    """
    if not bars or len(bars) < 2:
        return None

    n = len(bars)
    opens = [b['open'] for b in bars]
    closes = [b['close'] for b in bars]
    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]

    day_high = max(highs)
    day_low = min(lows)
    high_idx = highs.index(day_high)
    low_idx = lows.index(day_low)

    # 振幅（基于前收盘价，若无前收则基于开盘价）
    base = prev_close if (prev_close and prev_close > 0) else opens[0]
    amplitude = round((day_high - day_low) / base * 100, 4) if base > 0 else None

    # 开盘缺口
    open_gap_pct = round((opens[0] / base - 1) * 100, 4) if base > 0 else None

    # 上午/下午涨跌幅
    morning_end = _find_morning_end_idx(bars)
    afternoon_start = _find_afternoon_start_idx(bars)

    morning_return = None
    if opens[0] > 0 and morning_end < n:
        morning_return = round(closes[morning_end] / opens[0] - 1, 6)

    afternoon_return = None
    if afternoon_start < n and opens[afternoon_start] > 0:
        afternoon_return = round(closes[-1] / opens[afternoon_start] - 1, 6)

    # --- 形态判定（按优先级，互斥） ---
    pattern = 'no_clear_pattern'

    # 1. 横盘
    if amplitude is not None and amplitude < SIDEWAYS_AMP:
        pattern = 'sideways'

    # 2. 尾盘拉升（需要 tail_gain，由调用方传入或在此计算）
    # 尾盘30分钟涨幅
    elif len(bars) >= 31:
        tail_base = bars[-31]['close']
        tail_gain = (closes[-1] / tail_base - 1) if tail_base > 0 else 0
        if tail_gain > TAIL_RALLY_PCT / 100:
            # 检查尾盘是否为全天最强时段
            session_returns = []
            for _, a, b in SESSION_SPLITS:
                a, b = min(a, n), min(b, n)
                if b > a and opens[a] > 0:
                    session_returns.append(closes[min(b - 1, n - 1)] / opens[a] - 1)
                else:
                    session_returns.append(-999)
            if session_returns and tail_gain >= max(session_returns):
                pattern = 'tail_rally'

        # 3. 尾盘跳水
        if pattern == 'no_clear_pattern' and tail_gain < -TAIL_RALLY_PCT / 100:
            pattern = 'tail_dive'

    # 4. V型反转（上午最低 + 下午最高 + 振幅够大）
    if pattern == 'no_clear_pattern':
        half = n // 2
        if (low_idx < half and high_idx >= half and
                amplitude is not None and amplitude > V_SHAPE_AMP):
            pattern = 'v_shape'
        # 5. 倒V型（上午最高 + 下午最低 + 振幅够大）
        elif (high_idx < half and low_idx >= half and
              amplitude is not None and amplitude > V_SHAPE_AMP):
            pattern = 'inverted_v_shape'

    # 6. 早盘冲高回落（最高在前30分钟 + 从最高回落超过阈值）
    if pattern == 'no_clear_pattern':
        first_30 = min(30, n)
        if (high_idx < first_30 and day_high > 0 and
                (day_high - closes[-1]) / day_high > MORNING_PULLBACK_PCT / 100):
            pattern = 'morning_pullback'

    # 7. 单边上涨（收盘接近最高 + 上午弱下午强）
    if pattern == 'no_clear_pattern':
        if (closes[-1] >= day_high * CLOSE_NEAR_HIGH and
                morning_return is not None and afternoon_return is not None and
                morning_return < afternoon_return):
            pattern = 'one_side_up'
        # 8. 单边下跌（收盘接近最低 + 上午强下午弱）
        elif (closes[-1] <= day_low * CLOSE_NEAR_LOW and
              morning_return is not None and afternoon_return is not None and
              morning_return > afternoon_return):
            pattern = 'one_side_down'

    return {
        'amplitude': amplitude,
        'morning_return': morning_return,
        'afternoon_return': afternoon_return,
        'open_gap_pct': open_gap_pct,
        'high_time_idx': high_idx,
        'low_time_idx': low_idx,
        'pattern': pattern,
    }


# ---------------------------------------------------------------------------
# v2.6 新增：双轨判定辅助函数 + 行为指纹（移植 yaox v3.0）
# ---------------------------------------------------------------------------

def _pct_rank(value, arr):
    """计算 value 在 arr 中的分位（0-1）。返回 None 表示无法计算。"""
    if not arr or value is None:
        return None
    sorted_arr = sorted(arr)
    n = len(sorted_arr)
    # 找到 value 在排序数组中的位置
    count_less = sum(1 for x in sorted_arr if x < value)
    count_equal = sum(1 for x in sorted_arr if x == value)
    # 分位 = (小于的数量 + 等于的一半) / 总数
    return (count_less + count_equal * 0.5) / n


def compute_vwap_hold_ratio(bars):
    """v2.6 VWAP持有比例：价格在VWAP上方的时间占比。
    VWAP = 累计(收盘价×成交量) / 累计成交量（逐分钟滚动计算）。
    返回 0-1 之间的值，1=全天在VWAP上方（主力护盘强），0=全天在下方。
    """
    if not bars or len(bars) < 2:
        return None
    cum_pv = 0.0
    cum_v = 0.0
    above_count = 0
    valid_count = 0
    for b in bars:
        v = b.get('volume', 0)
        c = b.get('close', 0)
        if v is None or v <= 0 or c is None or c <= 0:
            continue
        cum_pv += c * v
        cum_v += v
        if cum_v > 0:
            vwap = cum_pv / cum_v
            valid_count += 1
            if c >= vwap:
                above_count += 1
    if valid_count == 0:
        return None
    return round(above_count / valid_count, 3)


def compute_weave_score(bars):
    """v2.6 织布机评分：价格在VWAP±1.5%内的时间占比。
    量化对倒的直接特征——价格不动、量在动，像织布机一样在均价附近来回。
    返回 0-1 之间的值，越高越像织布机（量化对倒嫌疑大）。
    """
    if not bars or len(bars) < 2:
        return None
    cum_pv = 0.0
    cum_v = 0.0
    in_band_count = 0
    valid_count = 0
    for b in bars:
        v = b.get('volume', 0)
        c = b.get('close', 0)
        if v is None or v <= 0 or c is None or c <= 0:
            continue
        cum_pv += c * v
        cum_v += v
        if cum_v > 0:
            vwap = cum_pv / cum_v
            valid_count += 1
            if abs(c / vwap - 1) < WEAVE_BAND:
                in_band_count += 1
    if valid_count == 0:
        return None
    return round(in_band_count / valid_count, 3)


def compute_pm_reversal(bars):
    """v2.6 午后反转：上午/下午方向相反=1，相同=0，波动太小=None。
    上午 = 09:30-11:30（前120根），下午 = 13:00-15:00（后120根）。
    上午涨跌幅 = (上午末根收盘 / 开盘) - 1
    下午涨跌幅 = (收盘 / 下午首根开盘) - 1
    两者方向相反且波动都 > PM_MIN_MOVE(0.1%) → 1（午后反转）
    两者方向相同且波动都 > PM_MIN_MOVE → 0（无反转）
    任一波动 ≤ PM_MIN_MOVE → None（波动太小无法判断）
    """
    if not bars or len(bars) < 10:
        return None
    n = len(bars)
    # 找上午结束位置（11:30附近）
    morning_end = _find_morning_end_idx(bars)
    # 找下午开始位置（13:00附近）
    afternoon_start = _find_afternoon_start_idx(bars)

    if morning_end <= 0 or afternoon_start >= n - 1:
        return None

    open_price = bars[0].get('open', 0)
    morning_close = bars[morning_end].get('close', 0)
    afternoon_open = bars[afternoon_start].get('open', 0)
    close_price = bars[-1].get('close', 0)

    if open_price <= 0 or afternoon_open <= 0:
        return None

    morning_return = morning_close / open_price - 1
    afternoon_return = close_price / afternoon_open - 1

    if abs(morning_return) > PM_MIN_MOVE and abs(afternoon_return) > PM_MIN_MOVE:
        return 1 if (morning_return * afternoon_return < 0) else 0
    return None


# ---------------------------------------------------------------------------
# 涨跌停 / 一字板检测
# ---------------------------------------------------------------------------

def detect_limit_status(bars, prev_close, limit_pct):
    if not bars:
        return None
    high = max(b['high'] for b in bars)
    low = min(b['low'] for b in bars)
    if high == low:                          # 一字板
        return 'one_word'
    base = prev_close if (prev_close and prev_close > 0) else bars[0]['open']
    if not base or base <= 0:
        return None
    close = bars[-1]['close']
    eps = 0.001
    limit_up = round(base * (1 + limit_pct), 2)
    limit_dn = round(base * (1 - limit_pct), 2)
    if close >= limit_up - eps:
        return 'limit_up'
    if close <= limit_dn + eps:
        return 'limit_down'
    return None


# ---------------------------------------------------------------------------
# 判定层
# ---------------------------------------------------------------------------

def compute_quant_pct(cv, corr, tail_ratio, flatness):
    contribs = [70 if cv < 0.5 else (40 if cv < 1.0 else 10)]
    if corr is not None:
        a = abs(corr)
        contribs.append(60 if a < 0.2 else (30 if a < 0.5 else 10))
    if tail_ratio is not None:
        contribs.append(70 if tail_ratio > 0.4 else (40 if tail_ratio > 0.2 else 10))
    if flatness is not None:
        contribs.append(60 if flatness < 0.15 else (35 if flatness < 0.3 else 10))
    return round(sum(contribs) / len(contribs), 1)


def analyze_day(bars, code, prev_close, history_data=None, market_vol_ratio=None):
    """分析单日1分钟K线，返回账本条目。

    v2.6 变更：
    - 双轨判定：history_data 有≥5天历史时用相对分位，否则用绝对阈值兜底
    - 校准阈值：CV≤0.95（原0.5），尾盘≥0.22（原0.3）
    - 新增行为指纹：vwap_hold_ratio / weave_score / pm_reversal
    - 新增 verdict_basis 字段："相对分位"或"绝对阈值"

    v2.7 变更：
    - 新增 market_vol_ratio 参数：大盘量比（上证指数当日量/过去5日均量）
    - 新增 market_vol_ratio 返回字段

    参数：
        bars: 1分钟K线列表（字典格式，含 open/high/low/close/volume/time）
        code: 股票代码
        prev_close: 前一交易日收盘价
        history_data: 可选，历史数据字典 {'cv': [...], 'corr': [...], 'tail_ratio': [...]}
                      用于相对分位判定；为None时用绝对阈值兜底
        market_vol_ratio: 可选，大盘量比（当日上证指数成交量/过去5日均量）
    """
    volumes = [b['volume'] for b in bars]
    total_vol = sum(volumes)
    if total_vol <= 0 or len(bars) < 2:
        return None

    limit_status = detect_limit_status(bars, prev_close, limit_pct_for(code))
    if limit_status:
        # 豁免条目不参与任何统计，快照是死重量 → 不存
        return {
            'is_real': None,
            'verdict': f'涨跌停豁免({limit_status})',
            'quant_pct': None,
            'limit_status': limit_status,
        }

    closes = [b['close'] for b in bars]

    vol_mean = total_vol / len(volumes)
    vol_std = math.sqrt(sum((v - vol_mean) ** 2 for v in volumes) / len(volumes))
    cv = vol_std / vol_mean

    corr = safe_corr(
        [closes[i] - closes[i - 1] for i in range(1, len(closes))],
        [volumes[i] - volumes[i - 1] for i in range(1, len(volumes))],
    )

    tail_ratio = sum(volumes[-30:]) / total_vol
    flatness = flatness_score(session_volume_profile(volumes))

    # --- v2.3 新增三信号（只记录，不入投票） ---
    flat_vol_ratio = compute_flat_vol_ratio(bars, volumes, vol_mean)
    tail_gain = compute_tail_gain(bars)
    zero_vol_mins = sum(1 for v in volumes if v <= 0)   # 盘中真实零成交（幽灵行已裁剪）

    # --- v2.4 新增六信号（只记录，不入投票）：大单拆分 + 主力净流入 ---
    big_stats = compute_big_order_stats(bars, volumes, vol_mean)

    # --- v2.5 新增：分时形态识别（只记录，不入投票） ---
    pattern_stats = compute_pattern_stats(bars, prev_close)

    # --- v2.6 新增：行为指纹（只记录，不入投票） ---
    vwap_hold_ratio = compute_vwap_hold_ratio(bars)
    weave_score = compute_weave_score(bars)
    pm_reversal = compute_pm_reversal(bars)

    # --- v2.6 双轨判定：相对分位优先，绝对阈值兜底 ---
    use_relative = (history_data is not None and
                    len(history_data.get('cv', [])) >= MIN_HISTORY_FOR_RELATIVE)

    hits = 0
    if use_relative:
        # 相对分位判定：和自己过去20天比
        cv_rank = _pct_rank(cv, history_data.get('cv', []))
        tail_rank = _pct_rank(tail_ratio, history_data.get('tail_ratio', []))
        if cv_rank is not None and cv_rank <= CV_RANK_LOW:
            hits += 1
        if tail_rank is not None and tail_rank >= TAIL_RANK_HIGH:
            hits += 1
        verdict_basis = '相对分位'
    else:
        # 绝对阈值兜底（校准后）
        if cv <= CV_ABS_QUANT:
            hits += 1
        if tail_ratio >= TAIL_ABS_QUANT:
            hits += 1
        verdict_basis = '绝对阈值'
    # 量价相关性（两种判定方式都用绝对阈值，因为无量纲）
    if corr is not None and abs(corr) < CORR_ABS_QUANT:
        hits += 1
    # 分时均匀度（保持原阈值，v2.6未校准）
    if flatness is not None and flatness < THRESH['flatness']:
        hits += 1

    if hits == 0:
        is_real, verdict = True, '真金白银'
    elif hits == 1:
        is_real, verdict = None, '疑似量化'
    else:
        is_real, verdict = False, '量化对倒'

    return {
        'is_real': is_real,
        'verdict': verdict,
        'quant_pct': compute_quant_pct(cv, corr, tail_ratio, flatness),
        'verdict_basis': verdict_basis,  # v2.6 新增：判定依据
        'cv': round(cv, 4),
        'corr': round(corr, 4) if corr is not None else None,
        'tail_ratio': round(tail_ratio, 4),
        'flatness': round(flatness, 4) if flatness is not None else None,
        'flat_vol_ratio': round(flat_vol_ratio, 4) if flat_vol_ratio is not None else None,
        'tail_gain': round(tail_gain, 6) if tail_gain is not None else None,
        'zero_vol_mins': zero_vol_mins,
        # --- v2.4 新增：大单拆分 + 主力净流入 ---
        'big_order_minutes': big_stats['big_order_minutes'] if big_stats else None,
        'big_order_ratio': big_stats['big_order_ratio'] if big_stats else None,
        'main_net_inflow': big_stats['main_net_inflow'] if big_stats else None,
        'main_net_inflow_pct': big_stats['main_net_inflow_pct'] if big_stats else None,
        'big_order_net_inflow': big_stats['big_order_net_inflow'] if big_stats else None,
        'order_flow_imbalance': big_stats['order_flow_imbalance'] if big_stats else None,
        # --- v2.5 新增：分时形态识别 ---
        'amplitude': pattern_stats['amplitude'] if pattern_stats else None,
        'morning_return': pattern_stats['morning_return'] if pattern_stats else None,
        'afternoon_return': pattern_stats['afternoon_return'] if pattern_stats else None,
        'open_gap_pct': pattern_stats['open_gap_pct'] if pattern_stats else None,
        'high_time_idx': pattern_stats['high_time_idx'] if pattern_stats else None,
        'low_time_idx': pattern_stats['low_time_idx'] if pattern_stats else None,
        'pattern': pattern_stats['pattern'] if pattern_stats else None,
        # --- v2.6 新增：行为指纹 ---
        'vwap_hold_ratio': vwap_hold_ratio,
        'weave_score': weave_score,
        'pm_reversal': pm_reversal,
        # --- v2.7 新增：大盘量比 ---
        'market_vol_ratio': market_vol_ratio,
        'limit_status': None,
        'vprofile_24': build_feature_snapshot(volumes),
    }


# ---------------------------------------------------------------------------
# 账本读写层
# ---------------------------------------------------------------------------

class LedgerCache:
    def __init__(self, ledger_dir: Path):
        self.dir = ledger_dir
        self._cache = {}
        self.dirty = set()

    def path_for(self, month: str) -> Path:
        return self.dir / f'{month}.json'

    def load(self, month: str) -> dict:
        if month not in self._cache:
            p = self.path_for(month)
            if p.exists():
                try:
                    self._cache[month] = json.loads(p.read_text(encoding='utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    print(f'[WARN] 账本 {month}.json 损坏，将重建（请人工核查备份）')
                    self._cache[month] = {}
            else:
                self._cache[month] = {}
        return self._cache[month]

    def has(self, month, code, date):
        return date in self.load(month).get(code, {})

    def put(self, month, code, date, entry):
        self.load(month).setdefault(code, {})[date] = entry
        self.dirty.add(month)

    def flush(self):
        # 紧凑 JSON：仓库体积友好（代价是网页上不再逐行可读）
        self.dir.mkdir(parents=True, exist_ok=True)
        for month in sorted(self.dirty):
            p = self.path_for(month)
            tmp = p.with_suffix('.tmp')
            tmp.write_text(
                json.dumps(self._cache[month], ensure_ascii=False,
                           separators=(',', ':')),
                encoding='utf-8',
            )
            tmp.replace(p)
            print(f'[INFO] 账本落盘: {p.name}')

    def verify(self, entries) -> bool:
        for month, code, date in entries:
            try:
                data = json.loads(self.path_for(month).read_text(encoding='utf-8'))
            except Exception:
                return False
            if date not in data.get(code, {}):
                return False
        return True


# ---------------------------------------------------------------------------
# 汇总统计
# ---------------------------------------------------------------------------

def print_summary(stats: dict):
    n = stats['processed']
    if n == 0:
        print('\n本日无新增账目（可能全部已存在或无新数据）。')
        return
    line = '=' * 52
    print(f'\n{line}')
    print(f"本次入账: {n} 条 (股票, 日期)")
    for label, key in (('真金白银', 'real'), ('疑似量化', 'suspect'), ('量化对倒', 'fake')):
        v = stats[key]
        print(f'  {label}  : {v:5d}  ({v / n:6.1%})')
    v = stats['limit_exempt']
    print(f'  涨跌停豁免: {v:5d}  ({v / n:6.1%})')
    print(f'  跳过: 北交所 {stats["skipped_bj"]} | 不完整 {stats["skipped_incomplete"]} | '
          f'已存在 {stats["skipped_exists"]} | 无法解析 {stats["skipped_bad"]}')
    print(f'  文件: 删除 {stats["files_deleted"]} | 保留 {stats["files_kept"]}')
    for name, key in (('cv', 'cv'), ('corr', 'corr'),
                      ('tail_ratio', 'tail'), ('flatness', 'flat')):
        cnt = stats[f'{key}_n']
        if cnt:
            print(f'  指标均值: {name}={stats[f"{key}_sum"] / cnt:.3f}')
    # --- v2.3 新信号均值 ---
    if stats['fv_n']:
        print(f'  指标均值: flat_vol_ratio={stats["fv_sum"] / stats["fv_n"]:.4f}')
    if stats['tg_n']:
        print(f'  指标均值: tail_gain={stats["tg_sum"] / stats["tg_n"]:+.3%}')
    if stats['zv_n']:
        print(f'  指标均值: zero_vol_mins={stats["zv_sum"] / stats["zv_n"]:.1f} 分钟')
    # --- v2.4 新信号均值：大单拆分 + 主力净流入 ---
    if stats['bom_n']:
        print(f'  指标均值: big_order_minutes={stats["bom_sum"] / stats["bom_n"]:.1f} 分钟')
    if stats['bor_n']:
        print(f'  指标均值: big_order_ratio={stats["bor_sum"] / stats["bor_n"]:.2%}')
    if stats['mni_n']:
        print(f'  指标均值: main_net_inflow={stats["mni_sum"] / stats["mni_n"]:+.0f} 手')
    if stats['mnip_n']:
        print(f'  指标均值: main_net_inflow_pct={stats["mnip_sum"] / stats["mnip_n"]:+.2%}')
    if stats['boni_n']:
        print(f'  指标均值: big_order_net_inflow={stats["boni_sum"] / stats["boni_n"]:+.0f} 手')
    if stats['ofi_n']:
        print(f'  指标均值: order_flow_imbalance={stats["ofi_sum"] / stats["ofi_n"]:+.3f}')
    # --- v2.5 新信号均值：分时形态识别 ---
    if stats['amp_n']:
        print(f'  指标均值: amplitude={stats["amp_sum"] / stats["amp_n"]:.2f}%')
    if stats['mr_n']:
        print(f'  指标均值: morning_return={stats["mr_sum"] / stats["mr_n"]:+.3%}')
    if stats['ar_n']:
        print(f'  指标均值: afternoon_return={stats["ar_sum"] / stats["ar_n"]:+.3%}')
    if stats['og_n']:
        print(f'  指标均值: open_gap_pct={stats["og_sum"] / stats["og_n"]:+.3f}%')
    # 形态分布
    pattern_counts = stats.get('pattern_counts', {})
    if pattern_counts:
        print('  形态分布:')
        for pat, cnt in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            print(f'    {pat:25s}: {cnt:5d}  ({cnt / n:6.1%})')
    # --- v2.6 新信号均值：行为指纹 ---
    if stats.get('vhr_n'):
        print(f'  指标均值: vwap_hold_ratio={stats["vhr_sum"] / stats["vhr_n"]:.3f}')
    if stats.get('ws_n'):
        print(f'  指标均值: weave_score={stats["ws_sum"] / stats["ws_n"]:.3f}')
    if stats.get('pmr_n'):
        print(f'  指标均值: pm_reversal={stats["pmr_sum"] / stats["pmr_n"]:.2f} '
              f'(1=午后反转, 0=无反转)')
    # v2.6 判定依据分布
    basis_counts = stats.get('basis_counts', {})
    if basis_counts:
        print('  判定依据:')
        for basis, cnt in sorted(basis_counts.items(), key=lambda x: -x[1]):
            print(f'    {basis:10s}: {cnt:5d}  ({cnt / n:6.1%})')
    # v2.6 指数跳过
    if stats.get('skipped_index'):
        print(f'  指数跳过: {stats["skipped_index"]} 个文件')
    # --- v2.7 大盘量比均值 ---
    if stats.get('mvr_n'):
        print(f'  指标均值: market_vol_ratio={stats["mvr_sum"] / stats["mvr_n"]:.2f} '
              f'(>1放量, <1缩量)')
    print(f'{line}\n')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def process_file(path: Path, ledger: LedgerCache, stats: dict, dry_run: bool,
                 history_store: dict = None, market_vol_store: dict = None) -> list:
    """处理单个1分钟K线文件。

    v2.6 变更：
    - 指数不入账本（INDEX_CODES）
    - 传入 history_store 用于相对分位判定

    v2.7 变更：
    - 传入 market_vol_store 用于大盘量比

    参数：
        history_store: 可选，历史数据存储 {code: [(date, cv, corr, tail_ratio), ...]}
                       按日期升序排列；为None时所有判定用绝对阈值兜底
        market_vol_store: 可选，大盘量比存储 {date: market_vol_ratio}
    """
    code = resolve_code(path)
    if is_bj(code):
        stats['skipped_bj'] += 1
        return []

    # v2.6 指数不入账本
    if code.lower() in INDEX_CODES:
        stats['skipped_index'] = stats.get('skipped_index', 0) + 1
        return []

    days = load_and_group_days(path)
    if not days:
        stats['skipped_bad'] += 1
        return []

    entries = []
    for date in sorted(days):
        month = date[:7]
        bars = days[date]

        if ledger.has(month, code, date):
            stats['skipped_exists'] += 1
            continue
        if len(bars) < min_bars_for(code):
            stats['skipped_incomplete'] += 1
            continue

        prev_close = load_prev_close(code, date)

        # v2.6 提取该股在 target_date 之前的历史数据（最多20天）
        history_data = None
        if history_store and code in history_store:
            hist = history_store[code]
            # 只取日期严格小于当前日期的记录
            prior = [(d, cv, co, tr) for d, cv, co, tr in hist if d < date]
            # 取最近20天
            prior = prior[-HISTORY_LOOKBACK:]
            if prior:
                history_data = {
                    'cv': [x[1] for x in prior],
                    'corr': [x[2] for x in prior],
                    'tail_ratio': [x[3] for x in prior],
                }

        # v2.7 提取当日大盘量比
        mvr = market_vol_store.get(date) if market_vol_store else None

        entry = analyze_day(bars, code, prev_close, history_data=history_data,
                            market_vol_ratio=mvr)
        if entry is None:
            stats['skipped_bad'] += 1
            continue

        if not dry_run:
            ledger.put(month, code, date, entry)
        entries.append((month, code, date))
        stats['processed'] += 1

        if entry['is_real'] is True:
            stats['real'] += 1
        elif entry['is_real'] is False:
            stats['fake'] += 1
        elif entry.get('limit_status'):
            stats['limit_exempt'] += 1
        else:
            stats['suspect'] += 1

        for k, v in (('cv', entry.get('cv')), ('corr', entry.get('corr')),
                     ('tail', entry.get('tail_ratio')), ('flat', entry.get('flatness'))):
            if v is not None:
                stats[f'{k}_sum'] += v
                stats[f'{k}_n'] += 1
        # v2.3 新信号累加
        for k, v in (('fv', entry.get('flat_vol_ratio')),
                     ('tg', entry.get('tail_gain'))):
            if v is not None:
                stats[f'{k}_sum'] += v
                stats[f'{k}_n'] += 1
        zv = entry.get('zero_vol_mins')
        if zv is not None:
            stats['zv_sum'] += zv
            stats['zv_n'] += 1
        # v2.4 新信号累加：大单拆分 + 主力净流入
        for k, v in (('bom', entry.get('big_order_minutes')),
                     ('bor', entry.get('big_order_ratio')),
                     ('mni', entry.get('main_net_inflow')),
                     ('mnip', entry.get('main_net_inflow_pct')),
                     ('boni', entry.get('big_order_net_inflow')),
                     ('ofi', entry.get('order_flow_imbalance'))):
            if v is not None:
                stats[f'{k}_sum'] += v
                stats[f'{k}_n'] += 1
        # v2.5 新信号累加：分时形态识别
        for k, v in (('amp', entry.get('amplitude')),
                     ('mr', entry.get('morning_return')),
                     ('ar', entry.get('afternoon_return')),
                     ('og', entry.get('open_gap_pct'))):
            if v is not None:
                stats[f'{k}_sum'] += v
                stats[f'{k}_n'] += 1
        pat = entry.get('pattern')
        if pat:
            stats['pattern_counts'][pat] = stats['pattern_counts'].get(pat, 0) + 1
        # v2.6 新信号累加：行为指纹
        for k, v in (('vhr', entry.get('vwap_hold_ratio')),
                     ('ws', entry.get('weave_score'))):
            if v is not None:
                stats[f'{k}_sum'] += v
                stats[f'{k}_n'] += 1
        pmr = entry.get('pm_reversal')
        if pmr is not None:
            stats['pmr_sum'] += pmr
            stats['pmr_n'] += 1
        # v2.6 判定依据统计
        vb = entry.get('verdict_basis')
        if vb:
            stats['basis_counts'][vb] = stats['basis_counts'].get(vb, 0) + 1
        # v2.7 大盘量比累加
        mvr = entry.get('market_vol_ratio')
        if mvr is not None:
            stats['mvr_sum'] += mvr
            stats['mvr_n'] += 1

    return entries


def load_market_volume(kline_dir_path: Path = None) -> dict:
    """v2.7 加载上证指数日线，计算每日大盘量比。

    大盘量比 = 当日成交量 / 过去 MARKET_VOL_LOOKBACK(5) 日平均成交量。
    >1=大盘放量，<1=大盘缩量。

    数据来源：data/kline/sh/sh000001.json（上证指数日线）。
    数据格式：[[date, open, close, high, low, volume], ...]

    返回：{date_str: market_vol_ratio}，日期格式 YYYY-MM-DD。
    若指数日线数据缺失或加载失败，返回空 dict。
    """
    if kline_dir_path is None:
        kline_dir_path = kline_dir()  # 经目录宪法
    path = kline_dir_path / "sh" / "sh000001.json"
    if not path.exists():
        print('[大盘量比] 上证指数日线数据缺失，market_vol_ratio 将为空')
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 兼容两种格式：list 或 dict（含 'klines' 键）
        if isinstance(data, dict):
            klines = data.get('klines', data.get('data', []))
        else:
            klines = data
        if not klines:
            print('[大盘量比] 上证指数日线数据为空')
            return {}
        dates, vols = [], []
        for k in klines:
            try:
                dates.append(str(k[0])[:10])  # 日期
                vols.append(float(k[5]))       # 成交量
            except Exception:
                continue
        out = {}
        for i in range(len(dates)):
            prev = vols[max(0, i - MARKET_VOL_LOOKBACK):i]
            if prev and sum(prev) > 0:
                out[dates[i]] = round(vols[i] / (sum(prev) / len(prev)), 2)
        print(f'[大盘量比] 指数量比就绪: {len(out)} 天')
        return out
    except Exception as e:
        print(f'[大盘量比] 加载失败: {e}')
        return {}


def load_history_store(ledger_dir_path: Path) -> dict:
    """v2.6 加载所有已存在的账本，构建历史数据存储。

    返回：{code: [(date, cv, corr, tail_ratio), ...]} 按日期升序排列
    用于相对分位判定：有≥5天历史时用相对分位，否则用绝对阈值兜底。
    """
    store = {}
    if not ledger_dir_path.exists():
        return store
    for ledger_file in sorted(ledger_dir_path.glob('*.json')):
        try:
            with open(ledger_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for code, days in data.items():
            if not isinstance(days, dict):
                continue
            if code not in store:
                store[code] = []
            for date, entry in days.items():
                if not isinstance(entry, dict):
                    continue
                cv = entry.get('cv')
                corr = entry.get('corr')
                tail_ratio = entry.get('tail_ratio')
                if cv is not None and tail_ratio is not None:
                    store[code].append((date, cv, corr, tail_ratio))
    # 按日期排序
    for code in store:
        store[code].sort(key=lambda x: x[0])
    return store


def main():
    ap = argparse.ArgumentParser(description='真假量柱账本 v2.7（zijian 移植版）')
    ap.add_argument('--dry-run', action='store_true', help='只分析，不写账本、不删源文件')
    ap.add_argument('--no-delete', action='store_true', help='写账本，但保留源文件')
    args = ap.parse_args()

    stats = {k: 0 for k in (
        'processed', 'real', 'suspect', 'fake', 'limit_exempt',
        'skipped_bj', 'skipped_incomplete', 'skipped_exists', 'skipped_bad',
        'files_deleted', 'files_kept',
        'cv_sum', 'cv_n', 'corr_sum', 'corr_n', 'tail_sum', 'tail_n', 'flat_sum', 'flat_n',
        'fv_sum', 'fv_n', 'tg_sum', 'tg_n', 'zv_sum', 'zv_n',
        # v2.4 新增：大单拆分 + 主力净流入
        'bom_sum', 'bom_n', 'bor_sum', 'bor_n',
        'mni_sum', 'mni_n', 'mnip_sum', 'mnip_n',
        'boni_sum', 'boni_n', 'ofi_sum', 'ofi_n',
        # v2.5 新增：分时形态识别
        'amp_sum', 'amp_n', 'mr_sum', 'mr_n', 'ar_sum', 'ar_n',
        'og_sum', 'og_n',
        # v2.6 新增：行为指纹
        'vhr_sum', 'vhr_n', 'ws_sum', 'ws_n', 'pmr_sum', 'pmr_n',
        # v2.7 新增：大盘量比
        'mvr_sum', 'mvr_n',
    )}
    stats['pattern_counts'] = {}  # v2.5 形态分布统计
    stats['basis_counts'] = {}    # v2.6 判定依据分布统计

    kline_1min_dir = min1_dir()  # 经目录宪法
    if not kline_1min_dir.exists():
        print(f'[INFO] 目录不存在，无数据可处理: {kline_1min_dir}')
        return 0

    files = sorted(kline_1min_dir.rglob('*.json'))
    print(f'[INFO] 扫描到 {len(files)} 个源文件，模式: '
          f'{"DRY-RUN" if args.dry_run else ("不删除源文件" if args.no_delete else "常规")}')

    ledger_path = ledger_dir()  # 经目录宪法
    ledger = LedgerCache(ledger_path)

    # v2.6 加载历史账本，用于相对分位判定
    history_store = load_history_store(ledger_path)
    hist_codes = len(history_store)
    hist_records = sum(len(v) for v in history_store.values())
    print(f'[INFO] 历史账本: {hist_codes} 只股票, {hist_records} 条记录 '
          f'(≥{MIN_HISTORY_FOR_RELATIVE}天启用相对分位判定)')

    # v2.7 加载大盘量比（上证指数日线）
    market_vol_store = load_market_volume()

    for path in files:
        entries = process_file(path, ledger, stats, args.dry_run,
                               history_store=history_store,
                               market_vol_store=market_vol_store)
        # --dry-run 与 --no-delete 都不进入删除分支
        if not entries or args.dry_run or args.no_delete:
            continue
        ledger.flush()
        if ledger.verify(entries):
            path.unlink()
            stats['files_deleted'] += 1
        else:
            print(f'[安全拦截] {path.name} 账本验证未通过，保留源文件')
            stats['files_kept'] += 1

    ledger.flush()
    print_summary(stats)
    return 0


if __name__ == '__main__':
    sys.exit(main())
