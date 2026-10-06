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

依赖：
    - requests（必需，腾讯/东财源）
    - akshare（可选，新浪源；未安装时新浪源自动跳过）
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # src/
from data.paths import kline_path, min1_path, universe_path, validate_code, self_check as paths_self_check
from data import validator as data_validator
from data import status as data_status

CST = timezone(timedelta(hours=8))
UA = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://quote.eastmoney.com/',
}
TIMEOUT = 15
MAX_WORKERS = 5

# 自选池（默认9只 + 上证指数基准）
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

def daily_from_tencent(code, datalen=120):
    """腾讯前复权日线。"""
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'
           f'param={code},day,,,{datalen},qfq')
    j = requests.get(url, headers=UA, timeout=TIMEOUT).json()
    node = (j.get('data') or {}).get(code) or {}
    rows = node.get('qfqday') or node.get('day') or []
    out = []
    for r in rows:  # 腾讯顺序: 日期,开,收,高,低,量
        if len(r) >= 6:
            out.append(_bar(r[0], r[1], r[3], r[4], r[2], r[5]))
    return out


def daily_from_sina(code, datalen=120):
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


def daily_from_eastmoney(code, datalen=120):
    """东财前复权日线。"""
    mkt = '1' if code.startswith('sh') else '0'
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?'
           f'secid={mkt}.{code[2:]}&fields1=f1,f2,f3,f4,f5,f6'
           f'&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1'
           f'&end=20500101&lmt={datalen}')
    j = requests.get(url, headers=UA, timeout=TIMEOUT).json()
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

def fetch_daily(code, datalen=120):
    """日线多源降级：腾讯→新浪→东财，返回 (源名, bars)。"""
    for name, fn in DAILY_SOURCES:
        try:
            bars = fn(code, datalen)
            if bars:
                return name, bars
        except Exception as e:
            print(f'    [{name}] {code} 日线失败: {type(e).__name__}: {e}')
    return None, None


def fetch_min1(code):
    """1分钟多源降级：新浪→腾讯→东财，返回 (源名, bars)。"""
    for name, fn in MIN1_SOURCES:
        try:
            bars = fn(code)
            if bars:
                return name, bars
        except Exception as e:
            print(f'    [{name}] {code} 1分钟失败: {type(e).__name__}: {e}')
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
            print(f'[INFO] 沪深300 成分股已缓存: {len(out)} 只')
        return out
    except Exception as e:
        print(f'[WARN] 沪深300 拉取失败（1分钟范围将只用自选）: {e}')
        return []


def get_1min_universe():
    """1分钟股票池：自选 + 沪深300（北交所已剔除）。"""
    codes = [c for c in HOLDINGS if not is_bj(c)]
    for c in load_hushen300():
        if c not in codes:
            codes.append(c)
    return codes


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
    """校验数据并更新拉取状态（统一入口）。"""
    try:
        dicts = _bars_to_dicts(bars)
        if data_type == "min1":
            is_valid, issues, stats = data_validator.validate_min1(dicts, code)
            trading_days = stats.get("trading_days")
        else:
            is_valid, issues, stats = data_validator.validate_daily(dicts, code)
            trading_days = None
        data_status.update_stock_status(
            code, data_type, source,
            bar_count=stats.get("bar_count", len(bars)),
            trading_days=trading_days,
            date_range=stats.get("date_range", [None, None]),
            is_valid=is_valid, issues=issues,
        )
        return is_valid, issues, stats
    except Exception as e:
        # 校验失败不影响数据保存，只记录
        print(f'    [WARN] {code} {data_type} 校验异常: {type(e).__name__}: {e}')
        return True, [], {"bar_count": len(bars)}


def daily_worker(code, datalen, full=False):
    time.sleep(0.15)  # 轻微限速
    src, bars = fetch_daily(code, datalen)
    if not bars:
        return False, None
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
    _validate_and_record(code, "daily", src, merged)
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


def run_threaded(codes, worker):
    ok, failed, sources = 0, [], {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(worker, c): c for c in codes}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                r, src = fut.result()
            except Exception as e:
                print(f'    {code} 异常: {type(e).__name__}: {e}')
                r, src = False, None
            if r:
                ok += 1
                sources[src] = sources.get(src, 0) + 1
            else:
                failed.append(code)
    return ok, failed, sources


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description='行情拉取（日线+1分钟）· 四源降级版')
    ap.add_argument('--full', action='store_true', help='强制全量重建日线（覆盖式）')
    ap.add_argument('--days', type=int, default=120, help='日线拉取根数（默认120）')
    ap.add_argument('--codes', nargs='*', help='只拉指定股票代码（如 sh600519 sz000688）')
    ap.add_argument('--self-check', action='store_true', help='仅运行路径宪法自检')
    args = ap.parse_args()

    # 路径宪法自检（前置校验）
    if not paths_self_check():
        print('[ERROR] 路径宪法自检失败，终止运行')
        return 1
    if args.self_check:
        return 0

    now = beijing_now()
    trading = in_trading_hours(now)
    print(f'[INFO] 北京时间 {now:%Y-%m-%d %H:%M}  交易时段={trading}')

    # 确定股票池
    if args.codes:
        codes = [validate_code(c) for c in args.codes if not is_bj(c)]
    else:
        codes = get_1min_universe()
    print(f'[INFO] 股票池: {len(codes)} 只')

    # --- 日线 ---
    if trading and now.weekday() < 5:
        print('[INFO] 当前处于 A 股交易时段，跳过日线拉取（避免盘中数据不完整）')
    else:
        print(f'[INFO] 日线模式: {"全量重建" if args.full else "增量合并"}（{args.days} 根）')
        ok, failed, sources = run_threaded(codes, lambda c: daily_worker(c, args.days, args.full))
        print(f'[INFO] 日线完成: 成功 {ok}/{len(codes)}，失败 {len(failed)}')
        print(f'[INFO] 日线源分布: {sources}')
        if failed:
            print(f'[INFO] 日线失败清单(前20): {", ".join(failed[:20])}')

    # --- 1分钟 ---
    print('[INFO] 1分钟模式: 新浪(多日) → 腾讯(当日) → 东财(多日) 降级')
    ok, failed, sources = run_threaded(codes, min1_worker)
    print(f'[INFO] 1分钟完成: 成功 {ok}/{len(codes)}，失败 {len(failed)}')
    print(f'[INFO] 1分钟源分布: {sources}')
    if failed:
        print(f'[INFO] 1分钟失败清单(前20): {", ".join(failed[:20])}')

    # --- 拉取状态汇总 ---
    print()
    data_status.print_summary()

    print('[INFO] fetch_quotes.py 全部结束')
    return 0


if __name__ == '__main__':
    sys.exit(main())
