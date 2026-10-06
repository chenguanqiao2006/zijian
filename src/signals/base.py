"""信号卡基类 - 所有量学信号卡的抽象基类"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..global_rules.price_position import PricePosition


class BaseSignal(ABC):
    """信号卡基类

    零未来函数声明：所有信号判定仅使用当日及之前数据。
    所有输出JSON必须包含 position 和 nature 字段（引用全局规则）。

    输入数据约束（见 spec_data_contract.md）：
    - 所有信号的输入数据必须为前复权数据
    - 必须包含的字段：close / high / low / volume（可选：open / dates）
    - 未复权数据会导致信号系统性错误，代码不进行复权校验
    - 调用方须在数据加载阶段完成前复权处理
    """

    signal_id: str = ""
    signal_name: str = ""

    def __init__(self):
        self._position_engine = PricePosition()

    @abstractmethod
    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """信号检测主入口"""
        ...

    def _compute_position(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """调用全局规则计算位置判定"""
        return self._position_engine.compute(data, date)

    def _get_nature(self, position: str) -> str:
        """根据位置获取性质描述（子类须覆盖，引用位置-性质映射表）"""
        if position == "unknown":
            return "无法判定性质"
        return "中性/换手性质"
