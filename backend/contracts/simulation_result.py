from __future__ import annotations

from pydantic import BaseModel, Field


class SimulationResult(BaseModel):
    scenario: str
    processed_work_orders: int = Field(ge=0)
    processed_tasks: int = Field(ge=0)
    events_created: int = Field(ge=0)
    quality_records_created: int = Field(ge=0)
