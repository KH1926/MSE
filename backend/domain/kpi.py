from __future__ import annotations

from typing import Any

try:
    from common import (
        DEFAULT_BOTTLENECK_STATION_ID,
        PACK_STATION_ID,
        QUALITY_RESULT_PASS,
        QUALITY_RESULT_REPAIR,
        WORK_ORDER_STATUS_COMPLETED,
        WORK_ORDER_STATUS_IN_PROGRESS,
        now_str,
    )
    from db import get_connection, query_all, query_one
except ModuleNotFoundError:
    from ..common import (
        DEFAULT_BOTTLENECK_STATION_ID,
        PACK_STATION_ID,
        QUALITY_RESULT_PASS,
        QUALITY_RESULT_REPAIR,
        WORK_ORDER_STATUS_COMPLETED,
        WORK_ORDER_STATUS_IN_PROGRESS,
        now_str,
    )
    from ..db import get_connection, query_all, query_one


def _run_filter_clause(run_id: str | None) -> tuple[str, tuple[str, ...]]:
    if not run_id:
        return "", ()
    return (
        """
        AND wo.work_order_no IN (
            SELECT DISTINCT work_order_no
            FROM production_event
            WHERE run_id = ?
        )
        """,
        (run_id,),
    )


def compute_and_store_kpi(
    conn,
    scenario: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    work_order_filter, work_order_params = _run_filter_clause(run_id)

    total_completed_row = query_one(
        conn,
        f"""
        SELECT COUNT(*) AS n
        FROM work_order wo
        WHERE wo.work_order_status = ?
        {work_order_filter}
        """,
        (WORK_ORDER_STATUS_COMPLETED, *work_order_params),
    )
    total_completed = int(total_completed_row["n"] if total_completed_row else 0)

    on_time_row = query_one(
        conn,
        f"""
        SELECT COUNT(*) AS n
        FROM work_order wo
        JOIN sales_order so ON wo.order_no = so.order_no
        WHERE wo.work_order_status = ?
          AND DATE(wo.actual_end) <= DATE(so.due_date)
          {work_order_filter}
        """,
        (WORK_ORDER_STATUS_COMPLETED, *work_order_params),
    )
    on_time_count = int(on_time_row["n"] if on_time_row else 0)
    on_time_rate = (on_time_count / total_completed) if total_completed else 0.0

    avg_lead_row = query_one(
        conn,
        f"""
        SELECT AVG((julianday(wo.actual_end) - julianday(wo.actual_start)) * 24.0 * 60.0) AS avg_mins
        FROM work_order wo
        WHERE wo.work_order_status = ?
          AND wo.actual_start IS NOT NULL
          AND wo.actual_end IS NOT NULL
          {work_order_filter}
        """,
        (WORK_ORDER_STATUS_COMPLETED, *work_order_params),
    )
    avg_lead_time = float(avg_lead_row["avg_mins"] or 0.0)

    wip_row = query_one(
        conn,
        f"""
        SELECT COUNT(*) AS n
        FROM work_order wo
        WHERE wo.work_order_status = ?
        {work_order_filter}
        """,
        (WORK_ORDER_STATUS_IN_PROGRESS, *work_order_params),
    )
    wip_count = int(wip_row["n"] if wip_row else 0)

    if run_id:
        quality_params: tuple[Any, ...] = (run_id,)
        quality_where = "WHERE run_id = ?"
    else:
        quality_params = ()
        quality_where = ""

    total_quality_row = query_one(
        conn,
        f"SELECT COUNT(*) AS n FROM quality_record {quality_where}",
        quality_params,
    )
    total_quality = int(total_quality_row["n"] if total_quality_row else 0)

    defect_row = query_one(
        conn,
        f"""
        SELECT COUNT(*) AS n
        FROM quality_record
        {quality_where}
        {"AND" if run_id else "WHERE"} quality_result != ?
        """,
        (*quality_params, QUALITY_RESULT_PASS),
    )
    defect_count = int(defect_row["n"] if defect_row else 0)

    repair_row = query_one(
        conn,
        f"""
        SELECT COUNT(*) AS n
        FROM quality_record
        {quality_where}
        {"AND" if run_id else "WHERE"} quality_result = ?
        """,
        (*quality_params, QUALITY_RESULT_REPAIR),
    )
    repair_count = int(repair_row["n"] if repair_row else 0)

    defect_rate = (defect_count / total_quality) if total_quality else 0.0
    repair_rate = (repair_count / total_quality) if total_quality else 0.0

    line_row = query_one(
        conn,
        "SELECT SUM(mode_time) AS total_mode, COUNT(*) AS cnt, MAX(mode_time) AS max_mode FROM station",
    )
    total_mode = float(line_row["total_mode"] or 0.0)
    station_count = int(line_row["cnt"] or 0)
    max_mode = float(line_row["max_mode"] or 0.0)
    line_balance_rate = (
        total_mode / (station_count * max_mode)
        if station_count and max_mode
        else 0.0
    )

    bottleneck_row = query_one(
        conn,
        "SELECT station_id FROM station ORDER BY mode_time DESC LIMIT 1",
    )
    bottleneck_station = (
        bottleneck_row["station_id"] if bottleneck_row else DEFAULT_BOTTLENECK_STATION_ID
    )

    if run_id:
        completed_at_pack = query_one(
            conn,
            """
            SELECT COUNT(DISTINCT work_order_no) AS n
            FROM production_event
            WHERE run_id = ? AND station_id = ? AND event_type = 'complete'
            """,
            (run_id, PACK_STATION_ID),
        )
        packed_count = int(completed_at_pack["n"] if completed_at_pack else 0)
        total_completed = max(total_completed, packed_count)

    snapshot = {
        "run_id": run_id,
        "snapshot_time": now_str(),
        "scenario": scenario,
        "total_completed": total_completed,
        "on_time_rate": on_time_rate,
        "avg_lead_time": avg_lead_time,
        "wip_count": wip_count,
        "defect_rate": defect_rate,
        "repair_rate": repair_rate,
        "line_balance_rate": line_balance_rate,
        "bottleneck_station": bottleneck_station,
    }
    conn.execute(
        """
        INSERT INTO kpi_snapshot (
            run_id, snapshot_time, scenario, total_completed, on_time_rate, avg_lead_time,
            wip_count, defect_rate, repair_rate, line_balance_rate, bottleneck_station
        )
        VALUES (
            :run_id, :snapshot_time, :scenario, :total_completed, :on_time_rate, :avg_lead_time,
            :wip_count, :defect_rate, :repair_rate, :line_balance_rate, :bottleneck_station
        )
        """,
        snapshot,
    )
    return snapshot


def get_latest_kpi(run_id: str | None = None) -> dict[str, Any]:
    with get_connection() as conn:
        if run_id:
            return query_one(
                conn,
                """
                SELECT *
                FROM kpi_snapshot
                WHERE run_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (run_id,),
            ) or {}
        return query_one(
            conn,
            """
            SELECT *
            FROM kpi_snapshot
            ORDER BY id DESC
            LIMIT 1
            """,
        ) or {}


def get_kpi_compare() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return query_all(
            conn,
            """
            SELECT ks.*
            FROM kpi_snapshot ks
            JOIN (
                SELECT scenario, MAX(id) AS max_id
                FROM kpi_snapshot
                GROUP BY scenario
            ) t ON ks.id = t.max_id
            ORDER BY ks.scenario ASC
            """,
        )
