from __future__ import annotations

import importlib
import os
from typing import Any, Protocol, runtime_checkable

ALLOWED_STRATEGY_MODULE_PREFIXES = (
    "b_strategy.",
    "backend.b_strategy.",
)
ALLOWED_STRATEGY_MODULES = {
    "simulation_strategy_b",
    "backend.simulation_strategy_b",
}


@runtime_checkable
class SimulationStrategy(Protocol):
    strategy_name: str

    def run(self, conn: Any, payload: Any) -> dict[str, Any]:
        """执行仿真策略并返回统计结果（不包含 KPI 快照写入）。"""


def load_strategy(default_strategy: SimulationStrategy) -> SimulationStrategy:
    plugin = os.getenv("MES_SIMULATION_STRATEGY")
    if not plugin:
        return default_strategy
    if ":" not in plugin:
        raise RuntimeError(
            "MES_SIMULATION_STRATEGY 格式错误，应为 <module>:<class>，例如 "
            "b_strategy.strategy_b:BTeamSimulationStrategy"
        )

    module_name, class_name = plugin.split(":", 1)
    if module_name not in ALLOWED_STRATEGY_MODULES and not module_name.startswith(
        ALLOWED_STRATEGY_MODULE_PREFIXES
    ):
        raise RuntimeError(
            "MES_SIMULATION_STRATEGY 只允许加载 b_strategy 或 backend.b_strategy 下的策略模块"
        )

    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name, None)
    if strategy_cls is None:
        raise RuntimeError(f"未找到策略类: {class_name}（模块: {module_name}）")

    strategy = strategy_cls()
    if not isinstance(strategy, SimulationStrategy):
        raise RuntimeError(
            f"策略类 {module_name}:{class_name} 未实现 SimulationStrategy 协议"
        )
    return strategy
