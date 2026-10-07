#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/fetch_quotes.py — 行情拉取（日线 + 1分钟），四源自动降级
====================================================================

数据源降级链：
    日线：腾讯 → 新浪 → 东财
    1分钟：新浪（多日≈10交易日） → 腾讯（仅当日） → 东财（多日ndays=5）

产出（落盘经 paths.py 目录宪法）：
    data/kline/{sh|sz}/{code}.json        日线，统一数组格式：
        ["YYYY-MM-DD", open, high, low, close, volume]
    data/kline_1min/{sh|sz}/{code}.json   1分钟线，统一数组格式：
        ["YYYY-MM-DD HH:MM", open, high, low, close, volume]

设计原则：
    1. 零未来函数：只拉历史数据，不预测
    2. 前复权：所有K线均为前复权（qfq）
    3. 多源降级：主源失败自动切换备用源，任一成功即返回
    4. 统一格式：所有源输出统一为 [时间, 开, 高, 低, 收, 量] 数组
    5. 1分钟为中转数据：record_truth 记账后即删，仓库不膨胀
    6. 结构化日志：同时输出到控制台和 data/logs/fetch_YYYY-MM-DD.log
    7. 自定义股票池：data/watchlist.json，支持 python -m data.watchlist 管理

依赖：
    - requests（必需，腾讯/东财源）
    - akshare（可选，新浪源；未安装时新浪源自动跳过）
"""

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # src/
from data.paths import kline_path, min1_path, universe_path, all_market_path, validate_code, self_check as paths_self_check
from data import validator as data_validator
from data import status as data_status
from data.logger import get_logger
from data.watchlist import Watchlist

log = get_logger()

# 待落盘的拉取状态（run_fetch 结尾一次性批量写入，避免逐只 load/save）
_PENDING_STATUS_UPDATES = []
_STATUS_LOCK = threading.Lock()

CST = timezone(timedelta(hours=8))
UA = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://quote.eastmoney.com/',
}
TIMEOUT = 15
ALL_MARKET_TIMEOUT = 8       # 全市场模式超时（秒），快速失败降级
MAX_WORKERS = 5
ALL_MARKET_WORKERS = 10      # 全市场模式并发（太高会触发数据源限流）

# 自选池（已迁移到 Watchlist，保留此常量仅作默认初始化参考）
# 实际股票池请使用: python -m data.watchlist list/add/remove
HOLDINGS = [
    'sh600584',   # 长电科技
    'sz002156',   # 通富微电
    'sh603283',   # 赛腾股份
    'sz300394',   # 天孚通信
    'sh601138',   # 工业富联
    'sh601231',   # 环旭电子
    'sz300476',   # 胜宏科技
    'sh603516',   # 淳中科技
    'sh000001',   # 上证指数
]


# ---------------------------------------------------------------------------
# 北交所过滤
# ---------------------------------------------------------------------------

def is_bj(code: str) -> bool:
    c = (code or '').lower().strip()
    if c.startswith('bj'):
        return True
    digits = c[2:] if (len(c) > 2 and c[:2] in ('sh', 'sz')) else c
    return digits.startswith(('920', '83', '87', '43'))


# ---------------------------------------------------------------------------
# 时间逻辑
# ---------------------------------------------------------------------------

def beijing_now():
    return datetime.now(CST)


def in_trading_hours(dt):
    m = dt.hour * 60 + dt.minute
    return (9 * 60 + 30) <= m < 15 * 60


# ---------------------------------------------------------------------------
# 统一输出格式工具
# ---------------------------------------------------------------------------

def _bar(time_str, o, h, l, c, v):
    """构造统一格式K线：[时间, 开, 高, 低, 收, 量]。"""
    return [str(time_str), float(o), float(h), float(l), float(c), float(v)]


# ---------------------------------------------------------------------------
# 日线数据源
# ---------------------------------------------------------------------------

def daily_from_tencent(code, datalen=120, timeout=None):
    """腾讯前复权日线。"""
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'
           f'param={code},day,,,{datalen},qfq')
    j = requests.get(url, headers=UA, timeout=timeout or TIMEOUT).json()
    node = (j.get('data') or {}).get(code) or {}
    rows = node.get('qfqday') or node.get('day') or []
    out = []
    for r in rows:  # 腾讯顺序: 日期,开,收,高,低,量
        if len(r) >= 6:
            out.append(_bar(r[0], r[1], r[3], r[4], r[2], r[5]))
    return out


def daily_from_sina(code, datalen=120, timeout=None):
    """新浪日线（akshare stock_zh_a_hist，前复权）。"""
    try:
        import akshare as ak
    except ImportError:
        return []
    # akshare 代码格式: 600519（不带前缀）
    sym = code[2:] if code[:2] in ('sh', 'sz') else code
    df = ak.stock_zh_a_hist(symbol=sym, period='daily',
                             start_date='20200101', end_date='20500101',
                             adjust='qfq')
    if df is None or len(df) == 0:
        return []
    # 取最近 datalen 根
    df = df.tail(datalen)
    out = []
    for _, row in df.iterrows():
        # akshare 列名: 日期,开盘,收盘,最高,最低,成交量
        out.append(_bar(row['日期'], row['开盘'], row['最高'],
                        row['最低'], row['收盘'], row['成交量']))
    return out


def daily_from_eastmoney(code, datalen=120, timeout=None):
    """东财前复权日线。"""
    mkt = '1' if code.startswith('sh') else '0'
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?'
           f'secid={mkt}.{code[2:]}&fields1=f1,f2,f3,f4,f5,f6'
           f'&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1'
           f'&end=20500101&lmt={datalen}')
    j = requests.get(url, headers=UA, timeout=timeout or TIMEOUT).json()
    rows = (j.get('data') or {}).get('klines') or []
    out = []
    for s in rows:  # 东财顺序: 日期,开,收,高,低,量
        p = s.split(',')
        if len(p) >= 6:
            out.append(_bar(p[0], p[1], p[3], p[4], p[2], p[5]))
    return out


DAILY_SOURCES = [
    ('腾讯', daily_from_tencent),
    ('新浪', daily_from_sina),
    ('东财', daily_from_eastmoney),
]

# 全市场模式源顺序：东财优先（push2his 接口在 CI 环境下更稳定）
ALL_MARKET_SOURCES = [
    ('东财', daily_from_eastmoney),
    ('腾讯', daily_from_tencent),
    ('新浪', daily_from_sina),
]

# 日线各源失败计数（跨股票累计，用于汇总日志）
_DAILY_FAIL_COUNTS = {name: 0 for name, _ in DAILY_SOURCES}
_DAILY_FAIL_LOCK = threading.Lock()


def _reset_daily_fail_counts():
    """重置日线源失败计数（每次 run_fetch 开始时调用）。"""
    with _DAILY_FAIL_LOCK:
        for k in _DAILY_FAIL_COUNTS:
            _DAILY_FAIL_COUNTS[k] = 0


def _log_daily_fail_summary():
    """打印一条日线源失败汇总日志（全局累计，只打一次）。"""
    with _DAILY_FAIL_LOCK:
        stats = ", ".join(f"{n}={c}" for n, c in _DAILY_FAIL_COUNTS.items())
    log.info(f"日线源失败统计(本次运行): {stats}")


# ---------------------------------------------------------------------------
# baostock 数据源（免费、无需注册、无限流，全市场首选）
# 注意：baostock 不是线程安全的，必须单线程使用，多线程会导致连接混乱
# ---------------------------------------------------------------------------

def daily_from_baostock(code, datalen=120, timeout=None):
    """baostock 前复权日线（单只，需在单线程环境调用）。"""
    try:
        import baostock as bs
    except ImportError:
        return []
    bs_code = code[:2] + '.' + code[2:]  # sh600519 -> sh.600519
    lg = bs.login()
    if lg.error_code != '0':
        return []
    try:
        rs = bs.query_history_k_data_plus(
            bs_code, 'date,open,high,low,close,volume',
            start_date='2020-01-01', end_date='2050-01-01',
            frequency='d', adjustflag='2')  # 2=前复权
        rows = []
        while rs.error_code == '0' and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()
    if not rows:
        return []
    out = []
    for r in rows[-datalen:]:
        out.append(_bar(r[0], float(r[1]), float(r[2]),
                        float(r[3]), float(r[4]), float(r[5])))
    return out


def fetch_daily_baostock_batch(codes, datalen=120):
    """baostock 单线程批量拉取（全市场模式首选）。

    baostock 无限流但非线程安全，单线程批量拉取约 130ms/只，
    全市场4606只约10分钟，成功率接近100%。

    Returns:
        (success_dict, failed_list): success_dict={code: bars}, failed_list=[code,...]
    """
    try:
        import baostock as bs
    except ImportError:
        log.error('baostock 未安装，全市场批量拉取不可用')
        return {}, list(codes)

    lg = bs.login()
    if lg.error_code != '0':
        log.error(f'baostock 登录失败: {lg.error_msg}')
        return {}, list(codes)

    success = {}
    failed = []
    total = len(codes)
    try:
        for i, code in enumerate(codes):
            bs_code = code[:2] + '.' + code[2:]
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code, 'date,open,high,low,close,volume',
                    start_date='2020-01-01', end_date='2050-01-01',
                    frequency='d', adjustflag='2')
                rows = []
                while rs.error_code == '0' and rs.next():
                    rows.append(rs.get_row_data())
                if rows:
                    bars = []
                    for r in rows[-datalen:]:
                        bars.append(_bar(r[0], float(r[1]), float(r[2]),
                                        float(r[3]), float(r[4]), float(r[5])))
                    success[code] = bars
                else:
                    failed.append(code)
            except Exception:
                failed.append(code)
            if (i + 1) % 500 == 0:
                log.info(f'baostock 批量进度: {i+1}/{total}（成功{len(success)}，失败{len(failed)}）')
    finally:
        bs.logout()

    log.info(f'baostock 批量完成: 成功{len(success)}，失败{len(failed)}')
    return success, failed


# ---------------------------------------------------------------------------
# 1分钟数据源
# ---------------------------------------------------------------------------

def min1_from_sina(code):
    """新浪1分钟（akshare stock_zh_a_minute，多日≈10交易日，前复权）。
    这是1分钟主源——能拉多日数据，解决腾讯仅当日的痛点。"""
    try:
        import akshare as ak
    except ImportError:
        return []
    df = ak.stock_zh_a_minute(symbol=code, period='1', adjust='qfq')
    if df is None or len(df) == 0:
        return []
    out = []
    for _, row in df.iterrows():
        # akshare 列名: day, open, high, low, close, volume, amount
        # day 格式: "2026-09-17 13:53:00" → 统一为 "2026-09-17 13:53"
        t = str(row['day'])[:16]  # 去掉秒
        out.append(_bar(t, row['open'], row['high'],
                        row['low'], row['close'], row['volume']))
    return out


def min1_from_tencent(code):
    """腾讯分时（仅当日，累计量差分为每分钟量）。"""
    url = f'https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}'
    j = requests.get(url, headers=UA, timeout=TIMEOUT).json()
    info = ((j.get('data') or {}).get(code) or {}).get('data') or {}
    dstr = str(info.get('date') or '')
    rows = info.get('data') or []
    if len(dstr) != 8 or not rows:
        return []
    day = f'{dstr[:4]}-{dstr[4:6]}-{dstr[6:8]}'
    out, prev = [], 0
    for r in rows:
        p = r.split()  # '0930 15.00 1234'
        if len(p) < 3 or len(p[0]) != 4:
            continue
        hhmm = p[0]
        # 只保留连续竞价时段
        if not ('0930' <= hhmm <= '1130' or '1300' <= hhmm <= '1500'):
            continue
        try:
            price, cum = float(p[1]), int(float(p[2]))
        except ValueError:
            continue
        # 累计量重置保护
        if cum < prev:
            prev = 0
        vol = max(0, cum - prev)
        prev = cum
        out.append(_bar(f'{day} {hhmm[:2]}:{hhmm[2:]}',
                        price, price, price, price, vol))
    return out


def min1_from_eastmoney(code, datalen=480):
    """东财1分钟（klt=1，多日ndays≈2交易日）。"""
    mkt = '1' if code.startswith('sh') else '0'
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?'
           f'secid={mkt}.{code[2:]}&fields1=f1,f2,f3,f4,f5,f6'
           f'&fields2=f51,f52,f53,f54,f55,f56&klt=1&fqt=1'
           f'&end=20500101&lmt={datalen}')
    j = requests.get(url, headers=UA, timeout=TIMEOUT).json()
    rows = (j.get('data') or {}).get('klines') or []
    out = []
    for s in rows:
        p = s.split(',')
        if len(p) >= 6:
            # 东财1分钟时间格式: "2026-09-30 09:30"
            out.append(_bar(p[0], p[1], p[3], p[4], p[2], p[5]))
    return out


MIN1_SOURCES = [
    ('新浪', min1_from_sina),      # 主源：多日≈10交易日
    ('腾讯', min1_from_tencent),   # 备1：仅当日
    ('东财', min1_from_eastmoney),  # 备2：多日≈2交易日
]


# ---------------------------------------------------------------------------
# 多源降级抓取
# ---------------------------------------------------------------------------

def fetch_daily(code, datalen=120, timeout=None, sources=None):
    """日线多源降级，返回 (源名, bars)。

    失败不逐条打日志，只累计计数（由 run_fetch 结尾统一打一条汇总）。
    """
    timeout = timeout or TIMEOUT
    src_list = sources or DAILY_SOURCES
    for name, fn in src_list:
        try:
            bars = fn(code, datalen, timeout=timeout)
            if bars:
                return name, bars
        except Exception:
            # 全市场场景下失败很常见，不逐条打日志，只累计
            with _DAILY_FAIL_LOCK:
                _DAILY_FAIL_COUNTS[name] = _DAILY_FAIL_COUNTS.get(name, 0) + 1
    return None, None


def fetch_min1(code):
    """1分钟多源降级：新浪→腾讯→东财，返回 (源名, bars)。"""
    for name, fn in MIN1_SOURCES:
        try:
            bars = fn(code)
            if bars:
                return name, bars
        except Exception as e:
            log.warn(f'[{name}] {code} 1分钟失败: {type(e).__name__}: {e}')
    return None, None


# ---------------------------------------------------------------------------
# 合并 / 落盘
# ---------------------------------------------------------------------------

def merge_bars(local, new):
    """合并新旧K线（新数据优先，按时间排序）。"""
    if not local:
        return sorted(new, key=lambda b: b[0])
    m = {b[0]: b for b in local}
    for b in new:
        m[b[0]] = b
    return [m[k] for k in sorted(m)]


def save_json(path: Path, obj):
    """原子写盘（先写临时文件再替换）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')),
                   encoding='utf-8')
    tmp.replace(path)


# ---------------------------------------------------------------------------
# 股票池
# ---------------------------------------------------------------------------

def load_hushen300():
    """加载沪深300成分股（优先读缓存，缓存缺失则从 akshare 拉取）。"""
    cache = universe_path()
    if cache.exists():
        try:
            arr = json.loads(cache.read_text(encoding='utf-8'))
            if isinstance(arr, list) and arr:
                out = [c for c in arr if not is_bj(c)]
                if out:
                    return out
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    try:
        import akshare as ak
        df = ak.index_stock_cons_csindex(symbol='000300')
        col = next((c for c in df.columns
                    if '代码' in str(c) and '指数' not in str(c)), None)
        if col is None:
            raise ValueError(f'未找到成分股代码列，实际列名: {list(df.columns)}')
        out = []
        for x in df[col].tolist():
            s = re.sub(r'[^0-9]', '', str(x))
            if len(s) == 6:
                if s.startswith('6'):
                    out.append('sh' + s)
                elif s.startswith(('0', '3')):
                    out.append('sz' + s)
        out = [c for c in out if not is_bj(c)]
        if out:
            save_json(cache, out)
            log.info(f'沪深300 成分股已缓存: {len(out)} 只')
        return out
    except Exception as e:
        log.warn(f'沪深300 拉取失败（1分钟范围将只用自选）: {e}')
        return []


def get_1min_universe():
    """1分钟股票池：自定义股票池 + 沪深300（北交所已剔除）。

    自定义股票池来源：data/watchlist.json（含 holdings/watch/benchmark 三组）
    管理命令：python -m data.watchlist list/add/remove
    """
    wl = Watchlist()
    codes = [c for c in wl.get_codes() if not is_bj(c)]
    for c in load_hushen300():
        if c not in codes:
            codes.append(c)
    return codes


def load_all_market():
    """加载全市场A股（沪市+深市，坚决排除北交所）。优先读缓存。

    数据源优先级：上交所官网 → 深交所官网 → 东方财富（备用）。
    缓存文件：data/universe/all_market.json
    """
    cache = all_market_path()
    if cache.exists():
        try:
            arr = json.loads(cache.read_text(encoding='utf-8'))
            if isinstance(arr, list) and arr:
                out = [c for c in arr if not is_bj(c)]
                if out:
                    return out
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    codes = set()
    try:
        import akshare as ak

        # 上交所（6开头）
        try:
            df_sh = ak.stock_info_sh_name_code()
            col = next((c for c in df_sh.columns if '代码' in str(c)), None)
            if col:
                for x in df_sh[col].tolist():
                    s = re.sub(r'[^0-9]', '', str(x))
                    if len(s) == 6 and s.startswith('6'):
                        codes.add('sh' + s)
                log.info(f'上交所股票: {len([c for c in codes if c.startswith("sh")])} 只')
        except Exception as e:
            log.warn(f'上交所股票列表拉取失败: {e}')

        # 深交所（0/3开头）
        try:
            df_sz = ak.stock_info_sz_name_code()
            col = next((c for c in df_sz.columns if '代码' in str(c)), None)
            if col:
                for x in df_sz[col].tolist():
                    s = re.sub(r'[^0-9]', '', str(x))
                    if len(s) == 6 and s.startswith(('0', '3')):
                        codes.add('sz' + s)
                log.info(f'深交所股票: {len([c for c in codes if c.startswith("sz")])} 只')
        except Exception as e:
            log.warn(f'深交所股票列表拉取失败: {e}')

        # 备用：东方财富实时行情（如果前两个加起来太少）
        if len(codes) < 2000:
            try:
                df = ak.stock_zh_a_spot_em()
                for _, row in df.iterrows():
                    s = str(row.get('代码', ''))
                    if len(s) == 6:
                        if s.startswith('6'):
                            codes.add('sh' + s)
                        elif s.startswith(('0', '3')):
                            codes.add('sz' + s)
                log.info(f'东方财富补充后: {len(codes)} 只')
            except Exception as e:
                log.warn(f'东方财富股票列表拉取失败: {e}')

    except Exception as e:
        log.error(f'全市场股票列表加载异常: {e}')

    out = sorted(c for c in codes if not is_bj(c))
    if out:
        save_json(cache, out)
        log.info(f'全市场A股已缓存: {len(out)} 只（沪市+深市，不含北交所）')
    else:
        log.error('全市场股票列表为空，请检查网络或数据源')
    return out


# ---------------------------------------------------------------------------
# 工作单元
# ---------------------------------------------------------------------------

def _bars_to_dicts(bars):
    """把 tuple 格式 [time, o, h, l, c, v] 转成 dict 列表供校验器使用。"""
    out = []
    for b in bars:
        if len(b) >= 6:
            out.append({"time": b[0], "open": b[1], "high": b[2],
                        "low": b[3], "close": b[4], "volume": b[5]})
    return out


def _validate_and_record(code, data_type, source, bars):
    """校验数据并累积拉取状态（统一入口，run_fetch 结尾批量落盘）。"""
    try:
        dicts = _bars_to_dicts(bars)
        if data_type == "min1":
            is_valid, issues, stats = data_validator.validate_min1(dicts, code)
            trading_days = stats.get("trading_days")
        else:
            is_valid, issues, stats = data_validator.validate_daily(dicts, code)
            trading_days = None
        update = {
            "code": code,
            "data_type": data_type,
            "source": source,
            "bar_count": stats.get("bar_count", len(bars)),
            "trading_days": trading_days,
            "date_range": stats.get("date_range", [None, None]),
            "is_valid": is_valid,
            "issues": issues,
        }
        with _STATUS_LOCK:
            _PENDING_STATUS_UPDATES.append(update)
        return is_valid, issues, stats
    except Exception as e:
        # 校验失败不影响数据保存，只记录
        log.warn(f'{code} {data_type} 校验异常: {type(e).__name__}: {e}')
        return True, [], {"bar_count": len(bars)}


def save_daily_bars(code, bars, full=False, source='baostock'):
    """保存日线数据到文件并校验更新状态（供批量拉取后复用）。"""
    path = kline_path(code)
    if full:
        merged = sorted(bars, key=lambda b: b[0])
    else:
        local = []
        if path.exists():
            try:
                local = json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                local = []
        merged = merge_bars(local, bars)
    save_json(path, merged)
    _validate_and_record(code, "daily", source, merged)
    return True


def daily_worker(code, datalen, full=False, all_market=False):
    if all_market:
        time.sleep(0.05)  # 全市场模式轻量限速，避免触发数据源限流
    else:
        time.sleep(0.15)  # 普通模式轻微限速
    if all_market:
        src, bars = fetch_daily(code, datalen, timeout=ALL_MARKET_TIMEOUT,
                                sources=ALL_MARKET_SOURCES)
    else:
        src, bars = fetch_daily(code, datalen)
    if not bars:
        return False, None
    save_daily_bars(code, bars, full, src)
    return True, src


def min1_worker(code):
    time.sleep(0.15)
    src, bars = fetch_min1(code)
    if not bars:
        return False, None
    path = min1_path(code)
    local = []
    if path.exists():
        try:
            local = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            local = []
    merged = merge_bars(local, bars)
    save_json(path, merged)
    _validate_and_record(code, "min1", src, merged)
    return True, src


def run_threaded(codes, worker, max_workers=None, progress_every=0):
    """并发执行 worker，返回 (成功数, 失败列表, 源分布)。

    Args:
        progress_every: 每完成 N 只打一次进度日志（0=不打）
    """
    ok, failed, sources = 0, [], {}
    workers = max_workers or MAX_WORKERS
    total = len(codes)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(worker, c): c for c in codes}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                r, src = fut.result()
            except Exception as e:
                log.error(f'{code} 异常: {type(e).__name__}: {e}')
                r, src = False, None
            if r:
                ok += 1
                sources[src] = sources.get(src, 0) + 1
            else:
                failed.append(code)
            done += 1
            if progress_every > 0 and done % progress_every == 0:
                log.info(f'进度: {done}/{total}（成功{ok}，失败{len(failed)}）')
    return ok, failed, sources


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_fetch(args):
    """执行行情拉取（核心逻辑，可被管道调用）。

    Args:
        args: argparse.Namespace，须包含 full/days/codes/self_check/watchlist/no_hs300

    Returns:
        int: 0=成功, 1=失败
    """
    # 路径宪法自检（前置校验）
    if not paths_self_check():
        log.error('路径宪法自检失败，终止运行')
        return 1
    if args.self_check:
        return 0

    # 仅打印股票池
    if args.watchlist:
        Watchlist().print_list()
        return 0

    # 重置日线源失败计数（每次运行独立统计）
    _reset_daily_fail_counts()

    now = beijing_now()
    trading = in_trading_hours(now)
    log.info(f'北京时间 {now:%Y-%m-%d %H:%M}  交易时段={trading}')
    log.info(f'日志文件: {log.log_file}')

    # 确定股票池
    if args.codes:
        codes = [validate_code(c) for c in args.codes if not is_bj(c)]
        log.info(f'指定股票池: {len(codes)} 只')
    elif getattr(args, 'all_market', False):
        codes = load_all_market()
        log.info(f'全市场A股（沪市+深市，不含北交所）: {len(codes)} 只')
    elif args.no_hs300:
        wl = Watchlist()
        codes = [c for c in wl.get_codes() if not is_bj(c)]
        log.info(f'自定义股票池（不含沪深300）: {len(codes)} 只')
    else:
        codes = get_1min_universe()
        log.info(f'股票池: {len(codes)} 只（自定义+沪深300）')

    all_market_mode = getattr(args, 'all_market', False)

    # --- 日线 ---
    if trading and now.weekday() < 5:
        log.info('当前处于 A 股交易时段，跳过日线拉取（避免盘中数据不完整）')
    else:
        log.info(f'日线模式: {"全量重建" if args.full else "增量合并"}（{args.days} 根）')
        if all_market_mode:
            log.info(f'全市场模式: {len(codes)} 只，主源baostock（单线程批量，无限流），失败补源腾讯/东财')
            # 第一轮：baostock 单线程批量拉取（无限流，高成功率，约130ms/只）
            bs_success, bs_failed = fetch_daily_baostock_batch(codes, args.days)
            ok = 0
            sources = {'baostock': len(bs_success)}
            for code, bars in bs_success.items():
                save_daily_bars(code, bars, args.full, source='baostock')
                ok += 1
            failed = bs_failed
            log.info(f'baostock 批量完成: 成功{ok}，失败{len(failed)}')
            # 第二轮：baostock 失败的用多线程腾讯/东财补拉
            if failed:
                log.info(f'补拉 {len(failed)} 只（腾讯/东财，并发{ALL_MARKET_WORKERS}）...')
                retry_ok, retry_failed, retry_sources = run_threaded(
                    failed, lambda c: daily_worker(c, args.days, args.full, all_market=True),
                    max_workers=ALL_MARKET_WORKERS, progress_every=200)
                ok += retry_ok
                failed = retry_failed
                for k, v in retry_sources.items():
                    sources[k] = sources.get(k, 0) + v
                log.info(f'补拉完成: 额外成功{retry_ok}，仍失败{len(failed)}')
        else:
            ok, failed, sources = run_threaded(codes, lambda c: daily_worker(c, args.days, args.full))
        log.info(f'日线完成: 成功 {ok}/{len(codes)}，失败 {len(failed)}')
        log.info(f'日线源分布: {sources}')
        # 日线源失败汇总（全局只打一次，避免刷屏）
        _log_daily_fail_summary()
        if failed:
            log.warn(f'日线失败清单(前20): {", ".join(failed[:20])}')

    # --- 1分钟（全市场模式跳过，数据量太大） ---
    if all_market_mode:
        log.info('全市场模式：跳过1分钟拉取（仅拉日线）')
    else:
        log.info('1分钟模式: 新浪(多日) → 腾讯(当日) → 东财(多日) 降级')
        ok, failed, sources = run_threaded(codes, min1_worker)
        log.info(f'1分钟完成: 成功 {ok}/{len(codes)}，失败 {len(failed)}')
        log.info(f'1分钟源分布: {sources}')
        if failed:
            log.warn(f'1分钟失败清单(前20): {", ".join(failed[:20])}')

    # --- 拉取状态批量落盘（一次性 load/save） ---
    if _PENDING_STATUS_UPDATES:
        data_status.update_stock_status_batch(_PENDING_STATUS_UPDATES)
        _PENDING_STATUS_UPDATES.clear()

    # --- 拉取状态汇总（人类可读，保留 print） ---
    print()
    data_status.print_summary()

    log.info('fetch_quotes.py 全部结束')
    return 0


def main():
    ap = argparse.ArgumentParser(description='行情拉取（日线+1分钟）· 四源降级版')
    ap.add_argument('--full', action='store_true', help='强制全量重建日线（覆盖式）')
    ap.add_argument('--days', type=int, default=120, help='日线拉取根数（默认120）')
    ap.add_argument('--codes', nargs='*', help='只拉指定股票代码（如 sh600519 sz000688）')
    ap.add_argument('--self-check', action='store_true', help='仅运行路径宪法自检')
    ap.add_argument('--watchlist', action='store_true', help='仅打印自定义股票池')
    ap.add_argument('--no-hs300', action='store_true', help='不拉沪深300，只拉自定义股票池')
    ap.add_argument('--all-market', action='store_true', help='全市场A股日线（沪市+深市，不含北交所，仅拉日线）')
    args = ap.parse_args()
    return run_fetch(args)


if __name__ == '__main__':
    sys.exit(main())