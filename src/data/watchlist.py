#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/data/watchlist.py — 自定义股票池管理
==========================================

支持增删查的自定义股票池，JSON 持久化，替代硬编码 HOLDINGS。

股票池文件位置：data/watchlist.json

数据结构：
    {
        "version": 1,
        "updated_at": "2026-10-07 12:00:00",
        "groups": {
            "holdings": [     # 自选持仓（默认组）
                {"code": "sh600519", "name": "贵州茅台", "added_at": "..."},
                ...
            ],
            "watch":    [...],  # 观察池
            "benchmark": [...]   # 基准指数
        }
    }

使用方式：
    from data.watchlist import Watchlist
    wl = Watchlist()
    wl.add("sh600519", name="贵州茅台")
    wl.remove("sh600519")
    codes = wl.get_codes()           # 获取所有股票代码
    codes = wl.get_codes("holdings") # 获取指定组
    wl.print_list()                   # 打印股票池
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import BASE, validate_code


# 股票池文件
WATCHLIST_FILE = BASE / "data" / "watchlist.json"

# 默认股票池（首次初始化时导入，与原 HOLDINGS 一致）
DEFAULT_HOLDINGS = [
    ("sh600584", "长电科技"),
    ("sz002156", "通富微电"),
    ("sh603283", "赛腾股份"),
    ("sz300394", "天孚通信"),
    ("sh601138", "工业富联"),
    ("sh601231", "环旭电子"),
    ("sz300476", "胜宏科技"),
    ("sh603516", "淳中科技"),
]
DEFAULT_BENCHMARK = [
    ("sh000001", "上证指数"),
]

# 合法组名
VALID_GROUPS = ("holdings", "watch", "benchmark")


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_bj(code: str) -> bool:
    """北交所过滤（与 fetch_quotes 保持一致）。"""
    c = (code or "").lower().strip()
    if c.startswith("bj"):
        return True
    digits = c[2:] if (len(c) > 2 and c[:2] in ("sh", "sz")) else c
    return digits.startswith(("920", "83", "87", "43"))


class Watchlist:
    """自定义股票池管理器。"""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or WATCHLIST_FILE
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        """加载股票池，不存在则用默认池初始化。"""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "groups" in data:
                    # 确保所有组都存在
                    for g in VALID_GROUPS:
                        data["groups"].setdefault(g, [])
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        # 首次初始化：导入默认池
        data = self._default_data()
        self._save(data)
        return data

    def _default_data(self) -> Dict[str, Any]:
        """构造默认股票池数据。"""
        now = _now_str()
        groups: Dict[str, List[Dict[str, str]]] = {}
        for g in VALID_GROUPS:
            groups[g] = []
        for code, name in DEFAULT_HOLDINGS:
            groups["holdings"].append({
                "code": code, "name": name, "added_at": now,
            })
        for code, name in DEFAULT_BENCHMARK:
            groups["benchmark"].append({
                "code": code, "name": name, "added_at": now,
            })
        return {
            "version": 1,
            "updated_at": now,
            "groups": groups,
        }

    def _save(self, data: Optional[Dict[str, Any]] = None):
        """原子写盘。"""
        if data is None:
            data = self._data
        data["updated_at"] = _now_str()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self._path)

    # ------------------------------------------------------------------
    # 增删查
    # ------------------------------------------------------------------

    def add(self, code: str, name: str = "", group: str = "holdings") -> bool:
        """添加股票到股票池。

        Args:
            code: 股票代码（如 sh600519）
            name: 股票名称（可选）
            group: 组名（holdings/watch/benchmark）

        Returns:
            True if added, False if already exists or invalid
        """
        if group not in VALID_GROUPS:
            raise ValueError(f"非法组名: {group}（合法: {', '.join(VALID_GROUPS)}）")
        try:
            code = validate_code(code)
        except ValueError:
            return False
        if _is_bj(code):
            return False  # 北交所不支持

        # 检查是否已存在（跨所有组）
        for g in VALID_GROUPS:
            for item in self._data["groups"][g]:
                if item["code"] == code:
                    return False  # 已存在

        self._data["groups"][group].append({
            "code": code,
            "name": name or "",
            "added_at": _now_str(),
        })
        self._save()
        return True

    def remove(self, code: str) -> bool:
        """从股票池移除股票（从所有组中移除）。

        Returns:
            True if removed, False if not found
        """
        try:
            code = validate_code(code)
        except ValueError:
            return False
        found = False
        for g in VALID_GROUPS:
            before = len(self._data["groups"][g])
            self._data["groups"][g] = [
                item for item in self._data["groups"][g]
                if item["code"] != code
            ]
            if len(self._data["groups"][g]) < before:
                found = True
        if found:
            self._save()
        return found

    def contains(self, code: str) -> bool:
        """检查股票是否在股票池中。"""
        try:
            code = validate_code(code)
        except ValueError:
            return False
        for g in VALID_GROUPS:
            for item in self._data["groups"][g]:
                if item["code"] == code:
                    return True
        return False

    def get_codes(self, group: Optional[str] = None) -> List[str]:
        """获取股票代码列表。

        Args:
            group: 组名，None 表示获取所有组（去重，按 holdings→watch→benchmark 顺序）

        Returns:
            股票代码列表
        """
        if group is not None:
            if group not in VALID_GROUPS:
                raise ValueError(f"非法组名: {group}")
            return [item["code"] for item in self._data["groups"][group]]
        # 所有组去重
        seen = set()
        result = []
        for g in ("holdings", "watch", "benchmark"):
            for item in self._data["groups"][g]:
                if item["code"] not in seen:
                    seen.add(item["code"])
                    result.append(item["code"])
        return result

    def get_items(self, group: Optional[str] = None) -> List[Dict[str, str]]:
        """获取股票详情列表（含名称）。"""
        if group is not None:
            if group not in VALID_GROUPS:
                raise ValueError(f"非法组名: {group}")
            return list(self._data["groups"][group])
        result = []
        seen = set()
        for g in ("holdings", "watch", "benchmark"):
            for item in self._data["groups"][g]:
                if item["code"] not in seen:
                    seen.add(item["code"])
                    result.append(item)
        return result

    def clear(self, group: Optional[str] = None):
        """清空股票池。

        Args:
            group: 组名，None 表示清空所有组
        """
        if group is not None:
            if group not in VALID_GROUPS:
                raise ValueError(f"非法组名: {group}")
            self._data["groups"][group] = []
        else:
            for g in VALID_GROUPS:
                self._data["groups"][g] = []
        self._save()

    def count(self, group: Optional[str] = None) -> int:
        """获取股票数量。"""
        return len(self.get_codes(group))

    # ------------------------------------------------------------------
    # 打印
    # ------------------------------------------------------------------

    def print_list(self):
        """打印股票池（人类可读）。"""
        print("=" * 60)
        print("📋 自定义股票池")
        print("=" * 60)
        group_names = {
            "holdings": "自选持仓",
            "watch": "观察池",
            "benchmark": "基准指数",
        }
        for g in ("holdings", "watch", "benchmark"):
            items = self._data["groups"][g]
            print(f"\n  【{group_names[g]}】({len(items)} 只)")
            if not items:
                print("    (空)")
                continue
            print(f"    {'代码':<12} {'名称':<12} {'加入时间':<20}")
            print("    " + "-" * 48)
            for item in items:
                name = item.get("name", "") or "-"
                added = item.get("added_at", "")
                print(f"    {item['code']:<12} {name:<12} {added:<20}")
        print(f"\n  合计: {self.count()} 只")
        print(f"  更新时间: {self._data.get('updated_at', '未知')}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# 命令行接口
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="自定义股票池管理")
    sub = ap.add_subparsers(dest="command", help="子命令")

    # list
    sub.add_parser("list", help="列出股票池")

    # add
    p_add = sub.add_parser("add", help="添加股票")
    p_add.add_argument("code", help="股票代码（如 sh600519）")
    p_add.add_argument("--name", default="", help="股票名称")
    p_add.add_argument("--group", default="holdings",
                       choices=VALID_GROUPS, help="组名（默认 holdings）")

    # remove
    p_rm = sub.add_parser("remove", help="移除股票")
    p_rm.add_argument("code", help="股票代码")

    # reset
    sub.add_parser("reset", help="重置为默认股票池")

    args = ap.parse_args()

    wl = Watchlist()

    if args.command == "list" or args.command is None:
        wl.print_list()
    elif args.command == "add":
        ok = wl.add(args.code, args.name, args.group)
        if ok:
            print(f"✅ 已添加: {args.code} {args.name}")
        else:
            print(f"❌ 添加失败: {args.code}（已存在或代码非法）")
        wl.print_list()
    elif args.command == "remove":
        ok = wl.remove(args.code)
        if ok:
            print(f"✅ 已移除: {args.code}")
        else:
            print(f"❌ 移除失败: {args.code}（不在股票池中）")
        wl.print_list()
    elif args.command == "reset":
        wl.clear()
        # 重新导入默认池
        for code, name in DEFAULT_HOLDINGS:
            wl.add(code, name, "holdings")
        for code, name in DEFAULT_BENCHMARK:
            wl.add(code, name, "benchmark")
        print("✅ 已重置为默认股票池")
        wl.print_list()


if __name__ == "__main__":
    main()
