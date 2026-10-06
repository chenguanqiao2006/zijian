#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_logger.py — 结构化日志记录器测试
============================================
"""

import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestLoggerBasic:
    """日志基本功能测试。"""

    def setup_method(self):
        """每个测试前重置单例。"""
        from data.logger import reset_logger
        reset_logger()

    def teardown_method(self):
        """每个测试后重置单例。"""
        from data.logger import reset_logger
        reset_logger()

    def test_get_logger_returns_instance(self):
        """get_logger 返回 FetchLogger 实例。"""
        from data.logger import get_logger, FetchLogger
        log = get_logger()
        assert isinstance(log, FetchLogger)

    def test_singleton(self):
        """多次调用 get_logger 返回同一实例。"""
        from data.logger import get_logger
        log1 = get_logger()
        log2 = get_logger()
        assert log1 is log2

    def test_log_file_created(self):
        """日志文件被创建。"""
        from data.logger import get_logger
        log = get_logger()
        assert log.log_file.exists()
        assert log.log_file.name.startswith("fetch_")
        assert log.log_file.suffix == ".log"

    def test_info_log_writes_to_file(self):
        """INFO 级别日志写入文件。"""
        from data.logger import get_logger
        log = get_logger()
        test_msg = "测试INFO日志写入"
        log.info(test_msg)
        # flush handlers
        for h in log._logger.handlers:
            h.flush()
        content = log.log_file.read_text(encoding="utf-8")
        assert test_msg in content
        assert "INFO" in content

    def test_warn_log_writes_to_file(self):
        """WARN 级别日志写入文件。"""
        from data.logger import get_logger
        log = get_logger()
        test_msg = "测试WARN日志写入"
        log.warn(test_msg)
        for h in log._logger.handlers:
            h.flush()
        content = log.log_file.read_text(encoding="utf-8")
        assert test_msg in content
        assert "WARNING" in content

    def test_error_log_writes_to_file(self):
        """ERROR 级别日志写入文件。"""
        from data.logger import get_logger
        log = get_logger()
        test_msg = "测试ERROR日志写入"
        log.error(test_msg)
        for h in log._logger.handlers:
            h.flush()
        content = log.log_file.read_text(encoding="utf-8")
        assert test_msg in content
        assert "ERROR" in content

    def test_debug_not_in_console_by_default(self):
        """DEBUG 级别默认不输出到控制台（但写入文件）。"""
        from data.logger import get_logger
        log = get_logger(level=logging.INFO)
        log.debug("这条DEBUG不应该在控制台")
        for h in log._logger.handlers:
            h.flush()
        content = log.log_file.read_text(encoding="utf-8")
        # 文件中应该有（文件 handler 是 DEBUG 级别）
        assert "这条DEBUG不应该在控制台" in content

    def test_log_format_contains_timestamp(self):
        """日志格式包含时间戳。"""
        from data.logger import get_logger
        log = get_logger()
        log.info("格式测试")
        for h in log._logger.handlers:
            h.flush()
        content = log.log_file.read_text(encoding="utf-8")
        # 时间格式 YYYY-MM-DD HH:MM:SS
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", content)

    def test_thread_safety(self):
        """多线程并发写日志不崩溃。"""
        import threading
        from data.logger import get_logger
        log = get_logger()

        def worker(n):
            for i in range(20):
                log.info(f"线程{n} 消息{i}")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for h in log._logger.handlers:
            h.flush()
        content = log.log_file.read_text(encoding="utf-8")
        # 100条消息都应该在文件中
        assert content.count("线程") >= 100


class TestLoggerCleanup:
    """日志清理功能测试。"""

    def setup_method(self):
        from data.logger import reset_logger
        reset_logger()

    def teardown_method(self):
        from data.logger import reset_logger
        reset_logger()

    def test_old_logs_cleanup(self):
        """超过保留天数的旧日志被清理。"""
        from data.logger import get_logger, LOG_DIR, RETENTION_DAYS
        from datetime import datetime, timedelta

        # 创建一个旧日志文件（40天前）
        old_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
        old_file = LOG_DIR / f"fetch_{old_date}.log"
        old_file.write_text("旧日志", encoding="utf-8")

        # 创建一个近期日志（5天前）
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        recent_file = LOG_DIR / f"fetch_{recent_date}.log"
        recent_file.write_text("近期日志", encoding="utf-8")

        # 触发清理（初始化 logger 时会调用 _cleanup_old_logs）
        log = get_logger()

        # 旧文件应该被删除
        assert not old_file.exists()
        # 近期文件应该保留
        assert recent_file.exists()

    def test_reset_logger(self):
        """reset_logger 后重新创建实例。"""
        from data.logger import get_logger, reset_logger
        log1 = get_logger()
        reset_logger()
        log2 = get_logger()
        assert log1 is not log2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
