#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_watchlist.py — 自定义股票池管理测试
================================================
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def tmp_watchlist(tmp_path):
    """创建临时股票池文件。"""
    from data.watchlist import Watchlist
    wl_file = tmp_path / "watchlist.json"
    wl = Watchlist(path=wl_file)
    return wl, wl_file


class TestWatchlistInit:
    """初始化测试。"""

    def test_default_holdings_loaded(self, tmp_watchlist):
        """首次初始化时导入默认自选池。"""
        wl, _ = tmp_watchlist
        # 默认有8只持仓 + 1只基准 = 9只
        assert wl.count("holdings") == 8
        assert wl.count("benchmark") == 1
        assert wl.count() == 9

    def test_default_codes_present(self, tmp_watchlist):
        """默认股票池包含预期的代码。"""
        wl, _ = tmp_watchlist
        codes = wl.get_codes("holdings")
        assert "sh600584" in codes  # 长电科技
        assert "sz002156" in codes  # 通富微电
        assert "sh000001" in wl.get_codes("benchmark")

    def test_watch_group_empty_by_default(self, tmp_watchlist):
        """观察池默认为空。"""
        wl, _ = tmp_watchlist
        assert wl.count("watch") == 0
        assert wl.get_codes("watch") == []


class TestWatchlistAdd:
    """添加股票测试。"""

    def test_add_new_stock(self, tmp_watchlist):
        """添加新股票成功。"""
        wl, _ = tmp_watchlist
        ok = wl.add("sh600519", name="贵州茅台")
        assert ok is True
        assert wl.contains("sh600519")
        assert wl.count() == 10  # 原9 + 1

    def test_add_to_watch_group(self, tmp_watchlist):
        """添加到观察池。"""
        wl, _ = tmp_watchlist
        ok = wl.add("sz000858", name="五粮液", group="watch")
        assert ok is True
        assert "sz000858" in wl.get_codes("watch")
        assert wl.count("watch") == 1

    def test_add_duplicate_returns_false(self, tmp_watchlist):
        """添加已存在的股票返回 False。"""
        wl, _ = tmp_watchlist
        # sh600584 已在默认池中
        ok = wl.add("sh600584", name="长电科技")
        assert ok is False
        assert wl.count() == 9  # 数量不变

    def test_add_invalid_code_returns_false(self, tmp_watchlist):
        """添加非法代码返回 False。"""
        wl, _ = tmp_watchlist
        assert wl.add("invalid") is False
        assert wl.add("600519") is False  # 缺少前缀
        assert wl.add("") is False

    def test_add_bj_stock_returns_false(self, tmp_watchlist):
        """北交所股票被过滤。"""
        wl, _ = tmp_watchlist
        assert wl.add("bj430047") is False
        assert wl.add("sh830799") is False  # 83开头

    def test_add_with_uppercase_code(self, tmp_watchlist):
        """大写代码自动转小写。"""
        wl, _ = tmp_watchlist
        ok = wl.add("SH600519", name="贵州茅台")
        assert ok is True
        assert wl.contains("sh600519")

    def test_add_invalid_group_raises(self, tmp_watchlist):
        """非法组名抛出 ValueError。"""
        wl, _ = tmp_watchlist
        with pytest.raises(ValueError):
            wl.add("sh600519", group="invalid_group")


class TestWatchlistRemove:
    """移除股票测试。"""

    def test_remove_existing_stock(self, tmp_watchlist):
        """移除已存在的股票成功。"""
        wl, _ = tmp_watchlist
        ok = wl.remove("sh600584")
        assert ok is True
        assert not wl.contains("sh600584")
        assert wl.count() == 8

    def test_remove_nonexistent_returns_false(self, tmp_watchlist):
        """移除不存在的股票返回 False。"""
        wl, _ = tmp_watchlist
        ok = wl.remove("sh600519")
        assert ok is False
        assert wl.count() == 9

    def test_remove_from_all_groups(self, tmp_watchlist):
        """移除操作从所有组中移除。"""
        wl, _ = tmp_watchlist
        # 先添加到 watch 组
        wl.add("sh600519", group="watch")
        assert wl.contains("sh600519")
        # 移除
        ok = wl.remove("sh600519")
        assert ok is True
        assert not wl.contains("sh600519")
        assert "sh600519" not in wl.get_codes("watch")


class TestWatchlistQuery:
    """查询测试。"""

    def test_get_codes_all_groups(self, tmp_watchlist):
        """获取所有组的代码（去重）。"""
        wl, _ = tmp_watchlist
        codes = wl.get_codes()
        assert len(codes) == 9
        # 顺序：holdings → watch → benchmark
        assert codes[0] == "sh600584"
        assert codes[-1] == "sh000001"

    def test_get_codes_specific_group(self, tmp_watchlist):
        """获取指定组的代码。"""
        wl, _ = tmp_watchlist
        holdings = wl.get_codes("holdings")
        benchmark = wl.get_codes("benchmark")
        assert len(holdings) == 8
        assert len(benchmark) == 1
        assert "sh000001" not in holdings

    def test_get_items_contains_names(self, tmp_watchlist):
        """get_items 返回含名称的详情。"""
        wl, _ = tmp_watchlist
        items = wl.get_items("holdings")
        assert len(items) == 8
        assert items[0]["code"] == "sh600584"
        assert items[0]["name"] == "长电科技"
        assert "added_at" in items[0]

    def test_contains_existing(self, tmp_watchlist):
        """contains 对已存在股票返回 True。"""
        wl, _ = tmp_watchlist
        assert wl.contains("sh600584") is True
        assert wl.contains("sh000001") is True

    def test_contains_nonexistent(self, tmp_watchlist):
        """contains 对不存在股票返回 False。"""
        wl, _ = tmp_watchlist
        assert wl.contains("sh600519") is False

    def test_count(self, tmp_watchlist):
        """count 返回正确数量。"""
        wl, _ = tmp_watchlist
        assert wl.count() == 9
        assert wl.count("holdings") == 8
        assert wl.count("watch") == 0
        assert wl.count("benchmark") == 1


class TestWatchlistClear:
    """清空测试。"""

    def test_clear_specific_group(self, tmp_watchlist):
        """清空指定组。"""
        wl, _ = tmp_watchlist
        wl.clear("holdings")
        assert wl.count("holdings") == 0
        assert wl.count("benchmark") == 1  # 其他组不受影响

    def test_clear_all_groups(self, tmp_watchlist):
        """清空所有组。"""
        wl, _ = tmp_watchlist
        wl.clear()
        assert wl.count() == 0
        assert wl.get_codes() == []

    def test_clear_invalid_group_raises(self, tmp_watchlist):
        """清空非法组名抛出 ValueError。"""
        wl, _ = tmp_watchlist
        with pytest.raises(ValueError):
            wl.clear("invalid")


class TestWatchlistPersistence:
    """持久化测试。"""

    def test_add_persists_to_file(self, tmp_watchlist):
        """添加操作持久化到文件。"""
        wl, wl_file = tmp_watchlist
        wl.add("sh600519", name="贵州茅台")
        # 重新加载
        data = json.loads(wl_file.read_text(encoding="utf-8"))
        codes = [item["code"] for item in data["groups"]["holdings"]]
        assert "sh600519" in codes

    def test_remove_persists_to_file(self, tmp_watchlist):
        """移除操作持久化到文件。"""
        wl, wl_file = tmp_watchlist
        wl.remove("sh600584")
        data = json.loads(wl_file.read_text(encoding="utf-8"))
        codes = [item["code"] for item in data["groups"]["holdings"]]
        assert "sh600584" not in codes

    def test_reload_from_file(self, tmp_watchlist):
        """重新实例化能从文件加载数据。"""
        from data.watchlist import Watchlist
        wl1, wl_file = tmp_watchlist
        wl1.add("sh600519", name="贵州茅台")
        # 新建实例，从同一文件加载
        wl2 = Watchlist(path=wl_file)
        assert wl2.contains("sh600519")
        assert wl2.count() == 10

    def test_updated_at_field(self, tmp_watchlist):
        """数据包含 updated_at 字段。"""
        wl, wl_file = tmp_watchlist
        data = json.loads(wl_file.read_text(encoding="utf-8"))
        assert "updated_at" in data
        assert data["version"] == 1

    def test_corrupted_file_resets_to_default(self, tmp_path):
        """损坏的文件重置为默认池。"""
        from data.watchlist import Watchlist
        wl_file = tmp_path / "watchlist.json"
        wl_file.write_text("不是合法的JSON{{{", encoding="utf-8")
        wl = Watchlist(path=wl_file)
        # 应该重置为默认池
        assert wl.count() == 9


class TestWatchlistPrint:
    """打印功能测试（不崩溃即可）。"""

    def test_print_list_no_crash(self, tmp_watchlist, capsys):
        """print_list 不崩溃。"""
        wl, _ = tmp_watchlist
        wl.print_list()
        captured = capsys.readouterr()
        assert "自定义股票池" in captured.out
        assert "长电科技" in captured.out

    def test_print_empty_watch_group(self, tmp_watchlist, capsys):
        """空组显示 (空)。"""
        wl, _ = tmp_watchlist
        wl.print_list()
        captured = capsys.readouterr()
        assert "观察池" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
