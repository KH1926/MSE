from __future__ import annotations

try:
    from simulation.strategy_b_template import BTeamSimulationStrategy
except ModuleNotFoundError:
    from .simulation.strategy_b_template import BTeamSimulationStrategy

__all__ = ["BTeamSimulationStrategy"]
