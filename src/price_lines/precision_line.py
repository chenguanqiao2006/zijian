"""精准线（precision_line）—— 稀有且金贵的"擒庄绳"

规格：spec_batch3_price_line.md 规格卡6
原著：《量线捉涨停》（第4版）第11讲，张得一著，四川人民出版社2021年版

核心逻辑：
1. 水平精准线：至少2个K线关键价位（开/收/高/低）在同一价位重合
2. 倾斜精准线：至少3个K线关键价位在一条倾斜线上
3. 取点类型须一致（同向相切）或双向相切
4. 量线生根：取点K线对应关键量柱
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BasePriceLine


# 水平重合容差
HORIZONTAL_DELTA = 0.01
# 倾斜切合容差
SLANT_DELTA = 0.02
# 最小水平取点数
MIN_HORIZONTAL_POINTS = 2
# 最小倾斜取点数
MIN_SLANT_POINTS = 3


class PrecisionLine(BasePriceLine):
    """精准线规格卡实现"""

    signal_id = "precision_line"
    signal_name = "精准线"

    def _extract_key_prices(self, data: Dict[str, Any], price_type: str) -> List[float]:
        """提取指定类型的关键价位序列"""
        o, h, l, c, _ = self._extract_series(data)
        if price_type == "open":
            return o
        elif price_type == "high":
            return h
        elif price_type == "low":
            return l
        elif price_type == "close":
            return c
        return c

    def _find_horizontal_precision(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """找水平精准线：至少2个取点同价位重合。
        遍历四种价位类型（高/低/收/开），找重合最多的价位。
        """
        price_types = ["low", "high", "close", "open"]
        best = None

        for ptype in price_types:
            prices = self._extract_key_prices(data, ptype)
            n = len(prices)
            # 统计每个价位的出现次数（在容差内）
            for i in range(n):
                if prices[i] <= 0:
                    continue
                points = []
                for j in range(n):
                    if abs(prices[j] - prices[i]) <= HORIZONTAL_DELTA:
                        points.append(j)
                if len(points) >= MIN_HORIZONTAL_POINTS:
                    # 检查取点K线是否对应关键量柱（简化：量柱>均值）
                    v = data.get("volume", [])
                    avg_v = sum(v) / len(v) if v else 0
                    key_volume_points = [p for p in points if p < len(v) and v[p] > avg_v]
                    is_rooted = len(key_volume_points) >= 1

                    if best is None or len(points) > len(best["points"]):
                        best = {
                            "line_price": prices[i],
                            "points": points,
                            "price_type": ptype,
                            "is_rooted": is_rooted,
                            "line_type": "horizontal_precision",
                        }

        return best

    def _find_slant_precision(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """找倾斜精准线：至少3个取点在一条斜线上。
        使用首尾两点法确定直线，检查中间点是否在容差内。
        """
        price_types = ["low", "high", "close", "open"]
        best = None

        for ptype in price_types:
            prices = self._extract_key_prices(data, ptype)
            n = len(prices)
            if n < MIN_SLANT_POINTS:
                continue

            # 遍历所有首尾点组合
            for i in range(n - MIN_SLANT_POINTS + 1):
                for j in range(i + MIN_SLANT_POINTS - 1, n):
                    if prices[i] <= 0 or prices[j] <= 0:
                        continue
                    interval = j - i
                    if interval <= 0:
                        continue
                    slope = (prices[j] - prices[i]) / interval
                    intercept = prices[i]  # 以i为x=0

                    # 检查中间点是否在斜线上
                    points = [i]
                    for k in range(i + 1, j + 1):
                        line_price = intercept + slope * (k - i)
                        if abs(prices[k] - line_price) <= SLANT_DELTA:
                            points.append(k)

                    if len(points) >= MIN_SLANT_POINTS:
                        # 检查量柱生根
                        v = data.get("volume", [])
                        avg_v = sum(v) / len(v) if v else 0
                        key_volume_points = [p for p in points if p < len(v) and v[p] > avg_v]
                        is_rooted = len(key_volume_points) >= 1

                        if best is None or len(points) > len(best["points"]):
                            best = {
                                "slope": round(slope, 6),
                                "intercept": round(intercept, 4),
                                "points": points,
                                "price_type": ptype,
                                "is_rooted": is_rooted,
                                "line_type": "slant_precision",
                            }

        return best

    def _get_direction(self, price_type: str, line_price: float, data: Dict[str, Any]) -> str:
        """判定精准线的方向性：最低点形成→上涨，最高点形成→下跌"""
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)
        if n == 0:
            return "unknown"
        current_price = c[-1]
        if price_type == "low":
            return "up" if current_price >= line_price else "unknown"
        elif price_type == "high":
            return "down" if current_price <= line_price else "unknown"
        return "unknown"

    def detect(self, data: Dict[str, Any], date: Optional[str] = None) -> Dict[str, Any]:
        """精准线检测主入口"""
        _, _, _, c, _ = self._extract_series(data)
        n = len(c)

        if n < MIN_HORIZONTAL_POINTS:
            return self._invalid_result(date, "数据不足，无法判定精准线")

        t_idx = n - 1

        # 优先找水平精准线，其次找倾斜精准线
        horizontal = self._find_horizontal_precision(data)
        slant = self._find_slant_precision(data)

        # 选择取点更多的精准线
        best = None
        if horizontal and slant:
            best = horizontal if len(horizontal["points"]) >= len(slant["points"]) else slant
        elif horizontal:
            best = horizontal
        elif slant:
            best = slant

        if best is None:
            return self._invalid_result(date, "未找到符合条件的精准线（取点不足或未重合）")

        # 位置判定
        position_result = self._compute_position(data, date)
        position = position_result.get("position", "unknown")

        # 性质描述
        if best["line_type"] == "horizontal_precision":
            if best["price_type"] == "low":
                nature = "底部精准支撑线（整理者分析，非权威来源）"
            elif best["price_type"] == "high":
                nature = "顶部精准压力线（整理者分析，非权威来源）"
            else:
                nature = "水平精准线（整理者分析，非权威来源）"
        else:
            nature = "倾斜精准线（整理者分析，非权威来源）"

        # 置信度
        confidence = "confirmed" if best["is_rooted"] else "unconfirmed"

        dates = data.get("dates", [])
        result = {
            "signal_id": self.signal_id,
            "date": date or (dates[t_idx] if t_idx < len(dates) else f"idx_{t_idx}"),
            "is_valid": True,
            "line_type": best["line_type"],
            "取点数量": len(best["points"]),
            "取点类型": best["price_type"],
            "position": position,
            "nature": nature,
            "confidence": confidence,
            "is_rooted": best["is_rooted"],
        }

        if best["line_type"] == "horizontal_precision":
            result["line_price"] = round(best["line_price"], 4)
            result["重合精度"] = 0.0  # 简化
        else:
            result["slope"] = best["slope"]
            result["intercept"] = best["intercept"]

        if not best["is_rooted"]:
            result["note"] = "未生根精准线，可靠性低"

        return result

    def _invalid_result(self, date: Optional[str], reason: str) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "date": date or "unknown",
            "is_valid": False,
            "line_type": None,
            "line_price": None,
            "取点数量": 0,
            "取点类型": None,
            "position": "unknown",
            "nature": "无法判定性质",
            "confidence": "invalid",
            "reason": reason,
        }
