from __future__ import annotations

from fastapi import APIRouter

try:
    from common import ok
    from contracts.request_models import ScheduleRequest
    from domain.schedule import (
        get_schedule_actual_timeline,
        list_schedule_tasks,
        run_schedule,
    )
except ModuleNotFoundError:
    from ..common import ok
    from ..contracts.request_models import ScheduleRequest
    from ..domain.schedule import (
        get_schedule_actual_timeline,
        list_schedule_tasks,
        run_schedule,
    )

router = APIRouter(tags=["schedule"])


@router.post("/schedule")
def run_schedule_route(payload: ScheduleRequest) -> dict[str, object]:
    return ok(run_schedule(payload))


@router.get("/schedule/tasks")
def get_schedule_tasks_route() -> dict[str, object]:
    return ok(list_schedule_tasks())


@router.get("/schedule/actual-timeline")
def get_schedule_actual_timeline_route() -> dict[str, object]:
    return ok(get_schedule_actual_timeline())
