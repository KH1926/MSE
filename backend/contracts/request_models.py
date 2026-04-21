from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

try:
    from common import PRODUCT_CODE, SCENARIO_S1_NORMAL
except ModuleNotFoundError:
    from ..common import PRODUCT_CODE, SCENARIO_S1_NORMAL


class OrderCreate(BaseModel):
    product_code: str = Field(default=PRODUCT_CODE)
    quantity: int = Field(gt=0, description="订单数量")
    due_date: date
    priority: int = Field(default=2, ge=1, le=9)


class ScheduleRequest(BaseModel):
    force_reschedule: bool = Field(default=False)


class SimulationRequest(BaseModel):
    scenario: str = Field(default=SCENARIO_S1_NORMAL)
    order_count: int = Field(default=10, ge=1)
    fault_station: str | None = Field(default=None)
    fault_duration_min: int = Field(default=0, ge=0)
    rush_order_at_min: int | None = Field(default=None, ge=0)
    run_id: str | None = Field(default=None, description="后端生成的仿真批次 ID，客户端无需传入")
