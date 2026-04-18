from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

try:
    from common import (
        DATETIME_FMT,
        EVENT_COMPLETE,
        EVENT_START,
        REWORK_STATION_ID,
        QC_STATION_ID,
        TASK_STATUS_PENDING,
        TASK_STATUS_IN_PROGRESS,
        WORK_ORDER_STATUS_PENDING,
        WORK_ORDER_STATUS_IN_PROGRESS,
        parse_datetime,
    )
    from db import get_connection, query_all, query_one, write_transaction
    from models.schemas import ScheduleRequest
except ModuleNotFoundError:
    from ..common import (
        DATETIME_FMT,
        EVENT_COMPLETE,
        EVENT_START,
        QC_STATION_ID,
        REWORK_STATION_ID,
        TASK_STATUS_IN_PROGRESS,
        TASK_STATUS_PENDING,
        WORK_ORDER_STATUS_IN_PROGRESS,
        WORK_ORDER_STATUS_PENDING,
        parse_datetime,
    )
    from ..db import get_connection, query_all, query_one, write_transaction
    from ..models.schemas import ScheduleRequest


def get_station_params(conn) -> dict[str, dict[str, Any]]:
    rows = query_all(
        conn,
        """
        SELECT station_id, min_time, mode_time, max_time, sigma, capacity
        FROM station
        """,
    )
    return {row["station_id"]: row for row in rows}


def run_schedule(payload: ScheduleRequest) -> dict[str, Any]:
    with write_transaction() as conn:
        work_orders = query_all(
            conn,
            """
            SELECT
                wo.work_order_no,
                wo.order_no,
                wo.product_code,
                wo.quantity,
                so.priority,
                so.due_date
            FROM work_order wo
            JOIN sales_order so ON so.order_no = wo.order_no
            WHERE wo.work_order_status IN (?, ?)
            ORDER BY so.priority ASC, so.due_date ASC, wo.created_at ASC
            """,
            (WORK_ORDER_STATUS_PENDING, WORK_ORDER_STATUS_IN_PROGRESS),
        )
        if not work_orders:
            raise HTTPException(status_code=400, detail="无可排产工单")

        station_map = get_station_params(conn)
        station_available_min: dict[str, float] = {
            row["station_id"]: 0.0
            for row in query_all(conn, "SELECT station_id FROM station")
        }
        base_time = datetime.now()
        scheduled_count = 0
        task_count = 0

        for work_order in work_orders:
            existing_count = query_one(
                conn,
                "SELECT COUNT(*) AS n FROM schedule_task WHERE work_order_no = ?",
                (work_order["work_order_no"],),
            )
            if existing_count and existing_count["n"] > 0 and not payload.force_reschedule:
                continue
            if payload.force_reschedule:
                conn.execute(
                    "DELETE FROM schedule_task WHERE work_order_no = ?",
                    (work_order["work_order_no"],),
                )

            route = query_all(
                conn,
                """
                SELECT station_id, sequence
                FROM process_route
                WHERE product_code = ?
                ORDER BY sequence ASC
                """,
                (work_order["product_code"],),
            )
            if not route:
                raise HTTPException(
                    status_code=400,
                    detail=f"产品 {work_order['product_code']} 缺少工艺路线",
                )

            work_order_ready_min = 0.0
            first_start: str | None = None
            last_end: str | None = None
            for step in route:
                station_id = step["station_id"]
                station = station_map.get(station_id)
                if not station:
                    raise HTTPException(status_code=400, detail=f"工位 {station_id} 参数缺失")

                duration_min = float(station["mode_time"]) / 60.0
                start_min = max(
                    work_order_ready_min,
                    station_available_min.get(station_id, 0.0),
                )
                end_min = start_min + duration_min
                planned_start = (base_time + timedelta(minutes=start_min)).strftime(
                    DATETIME_FMT
                )
                planned_end = (base_time + timedelta(minutes=end_min)).strftime(
                    DATETIME_FMT
                )
                if first_start is None:
                    first_start = planned_start
                last_end = planned_end

                conn.execute(
                    """
                    INSERT INTO schedule_task (
                        work_order_no, station_id, sequence,
                        planned_start, planned_end, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        work_order["work_order_no"],
                        station_id,
                        step["sequence"],
                        planned_start,
                        planned_end,
                        TASK_STATUS_PENDING,
                    ),
                )
                task_count += 1
                station_available_min[station_id] = end_min
                work_order_ready_min = end_min

            conn.execute(
                """
                UPDATE work_order
                SET scheduled_start = ?, scheduled_end = ?
                WHERE work_order_no = ?
                """,
                (first_start, last_end, work_order["work_order_no"]),
            )
            scheduled_count += 1

    return {
        "scheduled_work_orders": scheduled_count,
        "created_tasks": task_count,
        "force_reschedule": payload.force_reschedule,
    }


def list_schedule_tasks() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return query_all(
            conn,
            """
            SELECT *
            FROM schedule_task
            ORDER BY planned_start ASC, work_order_no ASC, sequence ASC
            """,
        )


def get_schedule_actual_timeline() -> list[dict[str, Any]]:
    with get_connection() as conn:
        events = query_all(
            conn,
            """
            SELECT work_order_no, station_id, event_type, event_time, id
            FROM production_event
            WHERE event_type IN (?, ?)
            ORDER BY event_time ASC, id ASC
            """,
            (EVENT_START, EVENT_COMPLETE),
        )

    start_time_queue: dict[tuple[str, str], list[str]] = {}
    run_counter: dict[tuple[str, str], int] = {}
    timeline_rows: list[dict[str, Any]] = []

    for event in events:
        station_id = event["station_id"]
        if not station_id:
            continue
        key = (event["work_order_no"], station_id)

        if event["event_type"] == EVENT_START:
            start_time_queue.setdefault(key, []).append(event["event_time"])
            continue

        queued_start_times = start_time_queue.get(key, [])
        if not queued_start_times:
            continue

        actual_start = queued_start_times.pop(0)
        actual_end = event["event_time"]
        run_no = run_counter.get(key, 0) + 1
        run_counter[key] = run_no
        duration_min = (
            parse_datetime(actual_end) - parse_datetime(actual_start)
        ).total_seconds() / 60.0

        timeline_rows.append(
            {
                "work_order_no": event["work_order_no"],
                "station_id": station_id,
                "run_no": run_no,
                "actual_start": actual_start,
                "actual_end": actual_end,
                "duration_min": duration_min,
                "is_rework_run": station_id in {REWORK_STATION_ID, QC_STATION_ID}
                and run_no > 1,
            }
        )

    timeline_rows.sort(
        key=lambda row: (
            row["actual_start"],
            row["work_order_no"],
            row["station_id"],
            row["run_no"],
        )
    )
    return timeline_rows
