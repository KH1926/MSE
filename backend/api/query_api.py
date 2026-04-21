from __future__ import annotations

from fastapi import APIRouter, Query

try:
    from common import ok
    from domain.kpi import get_kpi_compare, get_latest_kpi
    from domain.simulation import (
        get_station_status,
        list_events,
        list_quality_records,
    )
except ModuleNotFoundError:
    from ..common import ok
    from ..domain.kpi import get_kpi_compare, get_latest_kpi
    from ..domain.simulation import (
        get_station_status,
        list_events,
        list_quality_records,
    )

router = APIRouter(tags=["query"])


@router.get("/")
def home_route() -> dict[str, object]:
    return ok({"service": "manufacturing-backend", "version": "0.1.0"})


@router.get("/events")
def get_events_route(
    limit: int = Query(default=100, ge=1, le=1000),
    run_id: str | None = Query(default=None),
) -> dict[str, object]:
    return ok(list_events(limit, run_id))


@router.get("/quality/records")
def get_quality_records_route(
    limit: int = Query(default=100, ge=1, le=1000),
    run_id: str | None = Query(default=None),
) -> dict[str, object]:
    return ok(list_quality_records(limit, run_id))


@router.get("/kpi/latest")
def get_kpi_latest_route(run_id: str | None = Query(default=None)) -> dict[str, object]:
    return ok(get_latest_kpi(run_id))


@router.get("/kpi/compare")
def get_kpi_compare_route() -> dict[str, object]:
    return ok(get_kpi_compare())


@router.get("/stations/status")
def get_stations_status_route() -> dict[str, object]:
    return ok(get_station_status())
