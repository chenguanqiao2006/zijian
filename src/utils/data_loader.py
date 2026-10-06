"""数据加载工具 - 行情数据标准化

本模块仅提供数据格式校验与异常过滤工具。

重要声明：本模块不负责数据加载与前复权处理。
所有信号卡的输入数据必须为前复权数据，由调用方负责准备。
未复权数据会导致以下信号产生系统性错误：
- 位置判定（除权除息日的价格跳变导致 HHV/LLV 失真）
- 黄金柱（不破实顶条件误判）
- 元帅柱（除权缺口被误判为交易跳空）
- 将军柱（不破实底条件误判）
详细约束见 spec_data_contract.md。

零未来函数：数据加载不引入未来数据。
"""

from typing import Any, Dict, Optional


class DataLoader:
    """行情数据加载与标准化工具"""

    @staticmethod
    def validate(data: Dict[str, Any]) -> bool:
        """验证行情数据格式是否合法"""
        required_keys = ["close", "high", "low", "volume"]
        for key in required_keys:
            if key not in data or not isinstance(data[key], list):
                return False
        lengths = [len(data[k]) for k in required_keys]
        return len(set(lengths)) == 1

    @staticmethod
    def filter_invalid(data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤异常数据（负数、空值），异常点保留位置但标记为None"""
        result = dict(data)
        for key in ["close", "high", "low", "volume"]:
            if key in result:
                result[key] = [
                    v if (v is not None and isinstance(v, (int, float)) and v >= 0) else None
                    for v in result[key]
                ]
        return result

    @staticmethod
    def is_suspended(volume: Optional[float]) -> bool:
        """判断是否为停牌日（成交量为0或None）"""
        return volume is None or volume == 0

    @staticmethod
    def is_new_stock_first_day(data: Dict[str, Any], idx: int) -> bool:
        """判断是否为新股上市首日（索引为0）"""
        return idx == 0
