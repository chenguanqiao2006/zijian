#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_status.py — 拉取状态跟踪器测试
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data import status as data_status


class TestStatusBasic:
    def test_load_empty(self, tmp_path):
        """状态文件不存在时返回空结构。"""
        with patch.object(data_status, "STATUS_FILE", tmp_path / "nonexistent.json"):
            s = data_status.load_status()
            assert s == {"last_run": None, "stocks": {}}

    def test_save_and_load(self, tmp_path):
        """保存后能正确加载。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.save_status({"last_run": "2026-10-07 15:00:00", "stocks": {"sh600519": {}}})
            s = data_status.load_status()
            assert s["last_run"] == "2026-10-07 15:00:00"
            assert "sh600519" in s["stocks"]

    def test_corrupted_file(self, tmp_path):
        """状态文件损坏时返回空结构，不崩溃。"""
        status_file = tmp_path / "corrupted.json"
        status_file.write_text("not valid json{{{", encoding="utf-8")
        with patch.object(data_status, "STATUS_FILE", status_file):
            s = data_status.load_status()
            assert s == {"last_run": None, "stocks": {}}


class TestUpdateStockStatus:
    def test_update_min1(self, tmp_path):
        """更新1分钟状态。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.update_stock_status(
                code="sh600519", data_type="min1", source="sina",
                bar_count=1970, trading_days=8,
                date_range=["2026-09-25", "2026-10-07"],
                is_valid=True, issues=[],
            )
            s = data_status.load_status()
            assert "sh600519" in s["stocks"]
            assert s["stocks"]["sh600519"]["min1"]["source"] == "sina"
            assert s["stocks"]["sh600519"]["min1"]["trading_days"] == 8
            assert s["stocks"]["sh600519"]["min1"]["is_valid"] is True

    def test_update_daily(self, tmp_path):
        """更新日线状态。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.update_stock_status(
                code="sh600519", data_type="daily", source="tencent",
                bar_count=120, trading_days=None,
                date_range=["2026-04-01", "2026-10-07"],
                is_valid=True, issues=[],
            )
            s = data_status.load_status()
            assert s["stocks"]["sh600519"]["daily"]["source"] == "tencent"
            assert s["stocks"]["sh600519"]["daily"]["trading_days"] is None

    def test_update_multiple_stocks(self, tmp_path):
        """多只股票状态互不干扰。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.update_stock_status("sh600519", "min1", "sina", 1000, 5, ["a", "b"], True, [])
            data_status.update_stock_status("sz000001", "min1", "tencent", 500, 2, ["c", "d"], True, [])
            s = data_status.load_status()
            assert len(s["stocks"]) == 2
            assert s["stocks"]["sh600519"]["min1"]["bar_count"] == 1000
            assert s["stocks"]["sz000001"]["min1"]["bar_count"] == 500

    def test_issues_truncated(self, tmp_path):
        """问题列表最多保留10条。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            issues = [f"问题{i}" for i in range(20)]
            data_status.update_stock_status("sh600519", "min1", "sina", 100, 1, ["a", "b"], False, issues)
            s = data_status.load_status()
            assert len(s["stocks"]["sh600519"]["min1"]["issues"]) == 10

    def test_invalid_code_raises(self, tmp_path):
        """非法代码抛出异常。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            try:
                data_status.update_stock_status("600519", "min1", "sina", 100, 1, ["a", "b"], True, [])
                assert False, "应该抛出异常"
            except ValueError:
                pass


class TestGetStockStatus:
    def test_existing(self, tmp_path):
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.update_stock_status("sh600519", "min1", "sina", 1000, 5, ["a", "b"], True, [])
            s = data_status.get_stock_status("sh600519")
            assert s is not None
            assert "min1" in s

    def test_not_existing(self, tmp_path):
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            s = data_status.get_stock_status("sz999999")
            assert s is None


class TestGetSummary:
    def test_empty(self, tmp_path):
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            summary = data_status.get_summary()
            assert summary["total_stocks"] == 0
            assert summary["min1_stocks"] == 0

    def test_with_data(self, tmp_path):
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.update_stock_status("sh600519", "min1", "sina", 1970, 8, ["a", "b"], True, [])
            data_status.update_stock_status("sh600519", "daily", "tencent", 120, None, ["c", "d"], True, [])
            data_status.update_stock_status("sz000001", "min1", "sina", 500, 2, ["e", "f"], True, [])
            summary = data_status.get_summary()
            assert summary["total_stocks"] == 2
            assert summary["daily_stocks"] == 1
            assert summary["min1_stocks"] == 2
            assert summary["min1_avg_days"] == 5.0  # (8+2)/2
            assert summary["min1_max_days"] == 8
            assert summary["min1_min_days"] == 2


class TestPrintSummary:
    def test_print_no_crash(self, tmp_path, capsys):
        """打印汇总不崩溃。"""
        status_file = tmp_path / "test_status.json"
        with patch.object(data_status, "STATUS_FILE", status_file):
            data_status.update_stock_status("sh600519", "min1", "sina", 1970, 8, ["2026-09-25", "2026-10-07"], True, [])
            data_status.print_summary()
            captured = capsys.readouterr()
            assert "数据拉取状态汇总" in captured.out
            assert "sh600519" in captured.out


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
