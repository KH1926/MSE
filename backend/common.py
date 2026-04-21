from __future__ import annotations

from datetime import datetime
from typing import Any

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
DATE_FMT = "%Y-%m-%d"
PRODUCT_CODE = "CAR-001"
QC_STATION_ID = "WS40"
REWORK_STATION_ID = "WS30"
PACK_STATION_ID = "WS50"
MAX_REPAIR_COUNT = 1
DEFAULT_BOTTLENECK_STATION_ID = "WS20"
NEXT_STATION_BY_STATION_ID = {
    "WS10": "WS20",
    "WS20": "WS30",
    "WS30": "WS40",
}

ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_SCHEDULED = "scheduled"
ORDER_STATUS_IN_PRODUCTION = "in_production"
ORDER_STATUS_COMPLETED = "completed"
ORDER_STATUS_OVERDUE = "overdue"

WORK_ORDER_STATUS_PENDING = "pending"
WORK_ORDER_STATUS_IN_PROGRESS = "in_progress"
WORK_ORDER_STATUS_COMPLETED = "completed"
WORK_ORDER_STATUS_SCRAPPED = "scrapped"

TASK_STATUS_PENDING = "pending"
TASK_STATUS_IN_PROGRESS = "in_progress"
TASK_STATUS_COMPLETED = "completed"

STATION_STATUS_IDLE = "idle"
STATION_STATUS_BUSY = "busy"
STATION_STATUS_WAITING = "waiting"
STATION_STATUS_WAITING_MATERIAL = "waiting_material"
STATION_STATUS_BLOCKED = "blocked"
STATION_STATUS_FAULT = "fault"

QUALITY_RESULT_PASS = "pass"
QUALITY_RESULT_REPAIR = "repair"
QUALITY_RESULT_SCRAP = "scrap"

EVENT_START = "start"
EVENT_COMPLETE = "complete"
EVENT_TRANSFER = "transfer"
EVENT_QC_PASS = "qc_pass"
EVENT_QC_REPAIR = "qc_repair"
EVENT_QC_SCRAP = "qc_scrap"
EVENT_FAULT_START = "fault_start"
EVENT_FAULT_END = "fault_end"
EVENT_RUSH_ORDER = "rush_order"

SCENARIO_S1_NORMAL = "S1_normal"
SCENARIO_S2_RUSH = "S2_rush"
SCENARIO_S3_FAULT = "S3_fault"
SCENARIO_CODES = {SCENARIO_S1_NORMAL, SCENARIO_S2_RUSH, SCENARIO_S3_FAULT}


def ok(data: Any) -> dict[str, Any]:
    return {"code": 200, "message": "ok", "data": data}


def now_str() -> str:
    return datetime.now().strftime(DATETIME_FMT)


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FMT)
