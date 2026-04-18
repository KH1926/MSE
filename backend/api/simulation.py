from __future__ import annotations

from fastapi import APIRouter

try:
    from common import ok
    from models.schemas import SimulationRequest
    from services.simulation_service import run_simulation
except ModuleNotFoundError:
    from ..common import ok
    from ..models.schemas import SimulationRequest
    from ..services.simulation_service import run_simulation

router = APIRouter(tags=["simulation"])


@router.post("/simulation/run")
def run_simulation_route(payload: SimulationRequest) -> dict[str, object]:
    return ok(run_simulation(payload))
