#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/run_pipeline.py — 数据管道完整运行入口
==================================================

串联"拉取 → 校验 → 分析 → 账本"全流程，一键运行完整数据管道。

管道流程：
    1. 行情拉取（fetch_quotes）：日线 + 1分钟，四源自动降级
       └─ 拉取后自动校验（validator）+ 更新状态（status）
    2. 真假量柱分析（record_truth）：扫描1分钟数据，生成真假账本
       └─ 账本落盘到 data/analysis/truth_ledger/YYYY-MM.json
       └─ 分析完成后删除1分钟中转数据（可配置保留）

使用方式：
    # 完整管道（拉取+分析，默认只拉自定义股票池）
    python -m data.run_pipeline --no-hs300

    # 只拉取不分析
    python -m data.run_pipeline --skip-analysis --no-hs300

    # 只分析不拉取（使用已有1分钟数据）
    python -m data.run_pipeline --skip-fetch

    # 试运行（只分析不写账本）
    python -m data.run_pipeline --dry-run --no-hs300

    # 指定股票
    python -m data.run_pipeline --codes sh600519 sz000688
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # src/

from data.logger import get_logger
from data.fetch_quotes import run_fetch
from analysis.record_truth import run_analysis

log = get_logger()


def run_pipeline(args) -> int:
    """运行完整数据管道。

    Args:
        args: argparse.Namespace，须包含：
            full/days/codes/self_check/watchlist/no_hs300
            dry_run/no_delete
            skip_fetch/skip_analysis

    Returns:
        int: 0=成功, 1=失败
    """
    pipeline_start = time.time()
    log.info('=' * 60)
    log.info('🚀 数据管道启动')
    log.info('=' * 60)

    fetch_result = 0
    analysis_result = 0

    # --- 第一步：行情拉取 ---
    if not args.skip_fetch:
        log.info('--- 第一步：行情拉取 ---')
        step_start = time.time()
        fetch_result = run_fetch(args)
        step_elapsed = time.time() - step_start
        log.info(f'行情拉取完成，耗时 {step_elapsed:.1f}s，结果码={fetch_result}')
        if fetch_result != 0:
            log.error('行情拉取失败，管道终止')
            return fetch_result
    else:
        log.info('--- 跳过行情拉取（--skip-fetch） ---')

    # --- 第二步：真假量柱分析 ---
    # 全市场模式下只有日线、没有1分钟数据，自动跳过分析
    if getattr(args, 'all_market', False):
        log.info('--- 全市场模式：跳过账本分析（仅拉日线） ---')
    elif not args.skip_analysis:
        log.info('--- 第二步：真假量柱账本分析 ---')
        step_start = time.time()
        analysis_result = run_analysis(args)
        step_elapsed = time.time() - step_start
        log.info(f'账本分析完成，耗时 {step_elapsed:.1f}s，结果码={analysis_result}')
    else:
        log.info('--- 跳过账本分析（--skip-analysis） ---')

    # --- 管道汇总 ---
    total_elapsed = time.time() - pipeline_start
    log.info('=' * 60)
    log.info(f'✅ 数据管道完成，总耗时 {total_elapsed:.1f}s')
    log.info(f'   拉取: {"跳过" if args.skip_fetch else "完成"}')
    log.info(f'   分析: {"跳过" if args.skip_analysis else "完成"}')
    log.info(f'   模式: {"DRY-RUN" if args.dry_run else ("保留源文件" if args.no_delete else "常规")}')
    log.info('=' * 60)

    return 0


def main():
    ap = argparse.ArgumentParser(
        description='数据管道完整运行入口（拉取→校验→分析→账本）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m data.run_pipeline --no-hs300           # 完整管道（自定义股票池）
  python -m data.run_pipeline --codes sh600519      # 只拉指定股票并分析
  python -m data.run_pipeline --skip-analysis        # 只拉取不分析
  python -m data.run_pipeline --skip-fetch --dry-run # 只分析（试运行）
        """)

    # 拉取相关参数（透传给 fetch_quotes）
    ap.add_argument('--full', action='store_true', help='强制全量重建日线（覆盖式）')
    ap.add_argument('--days', type=int, default=120, help='日线拉取根数（默认120）')
    ap.add_argument('--codes', nargs='*', help='只拉指定股票代码（如 sh600519 sz000688）')
    ap.add_argument('--self-check', action='store_true', help='仅运行路径宪法自检')
    ap.add_argument('--watchlist', action='store_true', help='仅打印自定义股票池')
    ap.add_argument('--no-hs300', action='store_true', help='不拉沪深300，只拉自定义股票池')
    ap.add_argument('--all-market', action='store_true', help='全市场A股日线（沪市+深市，不含北交所，仅拉日线，自动跳过分析）')

    # 分析相关参数（透传给 record_truth）
    ap.add_argument('--dry-run', action='store_true', help='只分析，不写账本、不删源文件')
    ap.add_argument('--no-delete', action='store_true', help='写账本，但保留1分钟源文件')

    # 管道控制参数
    ap.add_argument('--skip-fetch', action='store_true', help='跳过行情拉取，直接分析已有1分钟数据')
    ap.add_argument('--skip-analysis', action='store_true', help='跳过账本分析，只拉取数据')

    args = ap.parse_args()
    return run_pipeline(args)


if __name__ == '__main__':
    sys.exit(main())
