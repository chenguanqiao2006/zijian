#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/logger.py — 结构化日志记录器
======================================

同时输出到控制台和文件，按日期轮转，线程安全。

日志文件位置：data/logs/fetch_YYYY-MM-DD.log
保留策略：最近 30 天，自动清理过期日志。

日志级别：
    DEBUG  - 调试细节（默认不输出到控制台）
    INFO   - 正常运行信息
    WARN   - 警告（非致命问题）
    ERROR  - 错误（需要关注）

使用方式：
    from data.logger import get_logger
    log = get_logger()
    log.info("日线拉取完成")
    log.warn("东财源失败，已切换到新浪")
    log.error("股票 sh600519 拉取异常: ...")
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .paths import BASE


# 中国标准时间（UTC+8）
CST = timezone(timedelta(hours=8))

# 日志目录
LOG_DIR = BASE / "data" / "logs"
# 日志保留天数
RETENTION_DAYS = 30
# 日志文件名前缀
LOG_PREFIX = "fetch_"

# 全局锁（保证线程安全）
_lock = threading.Lock()
# 全局单例
_logger: Optional["FetchLogger"] = None


class FetchLogger:
    """结构化日志记录器（控制台 + 文件双输出）。"""

    def __init__(self, name: str = "fetch_quotes", level: int = logging.INFO):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # 清除旧 handler（保证幂等，避免测试间状态污染）
        for h in self._logger.handlers[:]:
            try:
                h.close()
            except Exception:
                pass
            self._logger.removeHandler(h)

        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 格式化器
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # %(asctime)s 默认走 time.localtime()（UTC），改为北京时间
        fmt.converter = lambda ts: datetime.fromtimestamp(ts, CST).timetuple()

        # 控制台 handler（INFO 及以上）
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(fmt)
        self._logger.addHandler(console)

        # 文件 handler（DEBUG 及以上，按日期命名）
        today = datetime.now(CST).strftime("%Y-%m-%d")
        log_file = LOG_DIR / f"{LOG_PREFIX}{today}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        self._logger.addHandler(file_handler)

        self._log_file = log_file
        self._cleanup_old_logs()

    def _cleanup_old_logs(self):
        """清理超过保留天数的旧日志文件。"""
        try:
            cutoff = datetime.now(CST) - timedelta(days=RETENTION_DAYS)
            for f in LOG_DIR.glob(f"{LOG_PREFIX}*.log"):
                # 从文件名提取日期
                m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
                if not m:
                    continue
                try:
                    file_date = datetime.strptime(
                        m.group(1), "%Y-%m-%d").replace(tzinfo=CST)
                    if file_date < cutoff:
                        f.unlink()
                except ValueError:
                    continue
        except OSError:
            pass  # 清理失败不影响主流程

    def debug(self, msg: str):
        with _lock:
            self._logger.debug(msg)

    def info(self, msg: str):
        with _lock:
            self._logger.info(msg)

    def warn(self, msg: str):
        with _lock:
            self._logger.warning(msg)

    def error(self, msg: str):
        with _lock:
            self._logger.error(msg)

    @property
    def log_file(self) -> Path:
        return self._log_file


def get_logger(name: str = "fetch_quotes", level: int = logging.INFO) -> FetchLogger:
    """获取全局日志单例。

    Args:
        name: 日志器名称
        level: 控制台输出级别（默认 INFO）

    Returns:
        FetchLogger 实例
    """
    global _logger
    with _lock:
        if _logger is None:
            _logger = FetchLogger(name, level)
        return _logger


def reset_logger():
    """重置全局日志单例（主要用于测试）。"""
    global _logger
    with _lock:
        if _logger is not None:
            for h in _logger._logger.handlers[:]:
                h.close()
                _logger._logger.removeHandler(h)
        _logger = None


if __name__ == "__main__":
    log = get_logger()
    log.info("日志模块自测开始")
    log.debug("这是一条 DEBUG 信息（控制台不显示，文件中有）")
    log.warn("这是一条 WARN 信息")
    log.error("这是一条 ERROR 信息")
    log.info(f"日志文件位置: {log.log_file}")
    log.info("日志模块自测结束")
