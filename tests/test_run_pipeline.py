#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_run_pipeline.py — 数据管道运行入口测试
==================================================
"""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestRunPipelineArgs:
    """管道参数解析测试。"""

    def test_default_args(self):
        """默认参数值正确。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.full is False
                assert args.days == 120
                assert args.codes is None
                assert args.no_hs300 is False
                assert args.dry_run is False
                assert args.no_delete is False
                assert args.skip_fetch is False
                assert args.skip_analysis is False

    def test_skip_fetch_flag(self):
        """--skip-fetch 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--skip-fetch']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.skip_fetch is True
                assert args.skip_analysis is False

    def test_skip_analysis_flag(self):
        """--skip-analysis 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--skip-analysis']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.skip_analysis is True
                assert args.skip_fetch is False

    def test_dry_run_flag(self):
        """--dry-run 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--dry-run']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.dry_run is True

    def test_no_delete_flag(self):
        """--no-delete 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--no-delete']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.no_delete is True

    def test_codes_arg(self):
        """--codes 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--codes', 'sh600519', 'sz000688']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.codes == ['sh600519', 'sz000688']

    def test_no_hs300_flag(self):
        """--no-hs300 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--no-hs300']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.no_hs300 is True

    def test_full_flag(self):
        """--full 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--full']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.full is True

    def test_days_arg(self):
        """--days 参数正确解析。"""
        from data.run_pipeline import main
        with patch('sys.argv', ['run_pipeline', '--days', '250']):
            with patch('data.run_pipeline.run_pipeline', return_value=0) as mock_run:
                main()
                args = mock_run.call_args[0][0]
                assert args.days == 250


class TestRunPipelineLogic:
    """管道逻辑测试（使用 mock 避免网络请求）。"""

    def _make_args(self, **kwargs):
        """构造默认 args 对象。"""
        defaults = dict(
            full=False, days=120, codes=None, self_check=False,
            watchlist=False, no_hs300=False,
            dry_run=False, no_delete=False,
            skip_fetch=False, skip_analysis=False,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_skip_both_steps(self):
        """同时跳过拉取和分析时，管道正常完成。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args(skip_fetch=True, skip_analysis=True)
        result = run_pipeline(args)
        assert result == 0

    def test_skip_fetch_only(self):
        """只跳过拉取时，调用 run_analysis。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args(skip_fetch=True)
        with patch('data.run_pipeline.run_analysis', return_value=0) as mock_analysis:
            with patch('data.run_pipeline.run_fetch', return_value=0) as mock_fetch:
                result = run_pipeline(args)
                assert result == 0
                mock_fetch.assert_not_called()
                mock_analysis.assert_called_once_with(args)

    def test_skip_analysis_only(self):
        """只跳过分析时，调用 run_fetch。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args(skip_analysis=True)
        with patch('data.run_pipeline.run_fetch', return_value=0) as mock_fetch:
            with patch('data.run_pipeline.run_analysis', return_value=0) as mock_analysis:
                result = run_pipeline(args)
                assert result == 0
                mock_fetch.assert_called_once_with(args)
                mock_analysis.assert_not_called()

    def test_full_pipeline_calls_both(self):
        """完整管道同时调用拉取和分析。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args()
        with patch('data.run_pipeline.run_fetch', return_value=0) as mock_fetch:
            with patch('data.run_pipeline.run_analysis', return_value=0) as mock_analysis:
                result = run_pipeline(args)
                assert result == 0
                mock_fetch.assert_called_once_with(args)
                mock_analysis.assert_called_once_with(args)

    def test_fetch_failure_stops_pipeline(self):
        """拉取失败时管道终止，不调用分析。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args()
        with patch('data.run_pipeline.run_fetch', return_value=1) as mock_fetch:
            with patch('data.run_pipeline.run_analysis', return_value=0) as mock_analysis:
                result = run_pipeline(args)
                assert result == 1
                mock_fetch.assert_called_once_with(args)
                mock_analysis.assert_not_called()

    def test_dry_run_passed_to_analysis(self):
        """dry_run 参数透传给分析步骤。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args(dry_run=True)
        with patch('data.run_pipeline.run_fetch', return_value=0):
            with patch('data.run_pipeline.run_analysis', return_value=0) as mock_analysis:
                run_pipeline(args)
                called_args = mock_analysis.call_args[0][0]
                assert called_args.dry_run is True

    def test_no_delete_passed_to_analysis(self):
        """no_delete 参数透传给分析步骤。"""
        from data.run_pipeline import run_pipeline
        args = self._make_args(no_delete=True)
        with patch('data.run_pipeline.run_fetch', return_value=0):
            with patch('data.run_pipeline.run_analysis', return_value=0) as mock_analysis:
                run_pipeline(args)
                called_args = mock_analysis.call_args[0][0]
                assert called_args.no_delete is True


class TestRefactoredFunctions:
    """重构后的 run_fetch / run_analysis 函数可调用性测试。"""

    def test_run_fetch_callable_with_args(self):
        """run_fetch 可以用 argparse.Namespace 调用（self-check 模式不触发网络）。"""
        from data.fetch_quotes import run_fetch
        args = argparse.Namespace(
            full=False, days=120, codes=None, self_check=True,
            watchlist=False, no_hs300=False,
        )
        result = run_fetch(args)
        assert result == 0

    def test_run_fetch_watchlist_mode(self):
        """run_fetch watchlist 模式正常返回。"""
        from data.fetch_quotes import run_fetch
        args = argparse.Namespace(
            full=False, days=120, codes=None, self_check=False,
            watchlist=True, no_hs300=False,
        )
        result = run_fetch(args)
        assert result == 0

    def test_run_analysis_no_data(self):
        """run_analysis 在无1分钟数据时正常返回（不崩溃）。"""
        from analysis.record_truth import run_analysis
        import tempfile
        from pathlib import Path
        # 使用临时目录作为1分钟数据目录（空目录）
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_min1 = Path(tmpdir) / "kline_1min"
            tmp_ledger = Path(tmpdir) / "truth_ledger"
            tmp_min1.mkdir(parents=True, exist_ok=True)
            # 用 patch 替换目录函数
            with patch('analysis.record_truth.min1_dir', return_value=tmp_min1):
                with patch('analysis.record_truth.ledger_dir', return_value=tmp_ledger):
                    with patch('analysis.record_truth.load_history_store', return_value={}):
                        with patch('analysis.record_truth.load_market_volume', return_value={}):
                            args = argparse.Namespace(dry_run=True, no_delete=False)
                            result = run_analysis(args)
                            assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
