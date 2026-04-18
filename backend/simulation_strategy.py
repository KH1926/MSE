from __future__ import annotations

try:
    from simulation.strategy import SimulationStrategy, load_strategy
except ModuleNotFoundError:
    from .simulation.strategy import SimulationStrategy, load_strategy

__all__ = ["SimulationStrategy", "load_strategy"]
