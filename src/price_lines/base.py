"""量线基类 - 所有量线规格卡的抽象基类

量线与信号卡的本质区别：
- 信号卡 = 检测信号（判定条件，输出 is_signal）
- 量线 = 绘制规则（取点+画线+有效性判定，输出 is_valid + line_price）

零未来函数声明：所有量线取点仅使用当日及之前数据；
确认日定义严格按各规格卡第8节，不得用未来数据反推取点。

输入数据约束（见 spec_data_contract.md）：
- 所有量线的输入数据必须为前复权数据
- 必须包含的字段：close / high / low / volume（可选：open / dates）
- 未复权数据会导致量线价位失真，代码不进行复权校验
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from ..global_rules.price_position import PricePosition


class BasePriceLine(ABC):
    """量线基类

    所有量线规格卡继承此类，实现 detect 方法。
    输出 JSON 必须包含 position 和 nature 字段（引用全局规则）。
    """

    signal_id: str = ""
    signal_name: str = ""
    line_type: str = "horizontal"  # horizontal / slant / channel

    def __init__(self):
        self._position_engine = PricePosition()

    @abstractmethod
    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """量线检测主入口：取点→画线→有效性判定→输出JSON"""
        ...

    def _compute_position(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """调用全局规则计算位置判定"""
        return self._position_engine.compute(data, date)

    def _get_nature(self, position: str) -> str:
        """根据位置获取性质描述（子类须覆盖，引用位置-性质映射表）
        量线的 nature 映射均标注【整理者分析，非权威来源】
        """
        if position == "unknown":
            return "无法判定性质"
        return "中性量线（整理者分析，非权威来源）"

    def _extract_series(self, data: Dict[str, Any]) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
        """从 data 字典提取价格/量序列，统一处理索引。
        返回 (open, high, low, close, volume) 五个列表。
        """
        o = data.get("open", [])
        h = data.get("high", [])
        l = data.get("low", [])
        c = data.get("close", [])
        v = data.get("volume", [])
        return o, h, l, c, v

    def _is_valid_data_point(self, o: float, h: float, l: float, c: float, v: float) -> bool:
        """检查单个数据点是否有效（非空、非负、价格合理）"""
        if any(x is None for x in [o, h, l, c, v]):
            return False
        if any(x < 0 for x in [o, h, l, c, v]):
            return False
        if c <= 0:
            return False
        return True

    def _real_top(self, o: float, c: float) -> float:
        """实顶 = max(open, close)"""
        return max(o, c)

    def _real_bottom(self, o: float, c: float) -> float:
        """实底 = min(open, close)"""
        return min(o, c)
