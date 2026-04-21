from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

try:
    from common import (
        DATE_FMT,
        DATETIME_FMT,
        EVENT_COMPLETE,
        EVENT_FAULT_END,
        EVENT_FAULT_START,
        EVENT_QC_PASS,
        EVENT_QC_REPAIR,
        EVENT_QC_SCRAP,
        EVENT_RUSH_ORDER,
        EVENT_START,
        EVENT_TRANSFER,
        MAX_REPAIR_COUNT,
        NEXT_STATION_BY_STATION_ID,
        ORDER_STATUS_COMPLETED,
        ORDER_STATUS_IN_PRODUCTION,
        ORDER_STATUS_OVERDUE,
        PACK_STATION_ID,
        QC_STATION_ID,
        QUALITY_RESULT_PASS,
        QUALITY_RESULT_REPAIR,
        QUALITY_RESULT_SCRAP,
        REWORK_STATION_ID,
        SCENARIO_CODES,
        SCENARIO_S2_RUSH,
        SCENARIO_S3_FAULT,
        STATION_STATUS_BLOCKED,
        STATION_STATUS_BUSY,
        STATION_STATUS_FAULT,
        STATION_STATUS_IDLE,
        STATION_STATUS_WAITING,
        STATION_STATUS_WAITING_MATERIAL,
        TASK_STATUS_COMPLETED,
        TASK_STATUS_IN_PROGRESS,
        TASK_STATUS_PENDING,
        WORK_ORDER_STATUS_COMPLETED,
        WORK_ORDER_STATUS_IN_PROGRESS,
        WORK_ORDER_STATUS_SCRAPPED,
        now_str,
        parse_datetime,
    )
    from db import get_connection, query_all, query_one, write_transaction
    from contracts.request_models import SimulationRequest
    from contracts.simulation_result import SimulationResult
    from domain.kpi import compute_and_store_kpi
    from domain.schedule import get_station_params
    from integration.strategy_loader import SimulationStrategy, load_strategy
except ModuleNotFoundError:
    from ..common import (
        DATE_FMT,
        DATETIME_FMT,
        EVENT_COMPLETE,
        EVENT_FAULT_END,
        EVENT_FAULT_START,
        EVENT_QC_PASS,
        EVENT_QC_REPAIR,
        EVENT_QC_SCRAP,
        EVENT_RUSH_ORDER,
        EVENT_START,
        EVENT_TRANSFER,
        MAX_REPAIR_COUNT,
        NEXT_STATION_BY_STATION_ID,
        ORDER_STATUS_COMPLETED,
        ORDER_STATUS_IN_PRODUCTION,
        ORDER_STATUS_OVERDUE,
        PACK_STATION_ID,
        QC_STATION_ID,
        QUALITY_RESULT_PASS,
        QUALITY_RESULT_REPAIR,
        QUALITY_RESULT_SCRAP,
        REWORK_STATION_ID,
        SCENARIO_CODES,
        SCENARIO_S2_RUSH,
        SCENARIO_S3_FAULT,
        STATION_STATUS_BLOCKED,
        STATION_STATUS_BUSY,
        STATION_STATUS_FAULT,
        STATION_STATUS_IDLE,
        STATION_STATUS_WAITING,
        STATION_STATUS_WAITING_MATERIAL,
        TASK_STATUS_COMPLETED,
        TASK_STATUS_IN_PROGRESS,
        TASK_STATUS_PENDING,
        WORK_ORDER_STATUS_COMPLETED,
        WORK_ORDER_STATUS_IN_PROGRESS,
        WORK_ORDER_STATUS_SCRAPPED,
        now_str,
        parse_datetime,
    )
    from ..db import get_connection, query_all, query_one, write_transaction
    from ..contracts.request_models import SimulationRequest
    from ..contracts.simulation_result import SimulationResult
    from ..domain.kpi import compute_and_store_kpi
    from ..domain.schedule import get_station_params
    from ..integration.strategy_loader import SimulationStrategy, load_strategy


def create_run_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"RUN-{timestamp}-{uuid.uuid4().hex[:8]}"


def create_simulation_run(
    conn,
    *,
    run_id: str,
    payload: SimulationRequest,
    strategy_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO simulation_run (
            run_id, scenario, strategy_name, status, request_payload, started_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            payload.scenario,
            strategy_name,
            "running",
            json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
            now_str(),
        ),
    )


def complete_simulation_run(
    conn,
    *,
    run_id: str,
    result: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE simulation_run
        SET status = ?, result_summary = ?, completed_at = ?
        WHERE run_id = ?
        """,
        (
            "completed",
            json.dumps(result, ensure_ascii=False),
            now_str(),
            run_id,
        ),
    )


def validate_strategy_result(
    raw_result: dict[str, Any],
    *,
    expected_scenario: str,
) -> dict[str, Any]:
    try:
        result = SimulationResult.model_validate(raw_result).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail="仿真策略返回格式错误") from exc

    if result["scenario"] != expected_scenario:
        raise HTTPException(status_code=500, detail="仿真策略返回 scenario 与请求不一致")
    return result


def insert_event(
    conn,
    *,
    run_id: str | None,
    work_order_no: str,
    station_id: str | None,
    event_type: str,
    event_time: str,
    remark: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO production_event (
            run_id, work_order_no, station_id, event_type, event_time, remark
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, work_order_no, station_id, event_type, event_time, remark),
    )


def insert_quality_record(
    conn,
    *,
    run_id: str | None,
    work_order_no: str,
    inspect_time: str,
    quality_result: str,
    repair_count: int,
    remark: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO quality_record (
            run_id, work_order_no, inspect_time, quality_result, repair_count, remark
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, work_order_no, inspect_time, quality_result, repair_count, remark),
    )


def sample_duration_seconds(station_param: dict[str, Any]) -> float:
    sigma = station_param["sigma"]
    mode_time = station_param["mode_time"]
    if sigma is not None:
        sampled = random.gauss(mode_time, sigma)
        return max(0.1, sampled)

    min_time = station_param["min_time"]
    max_time = station_param["max_time"]
    if min_time is None or max_time is None:
        return float(mode_time)
    return max(0.1, random.triangular(min_time, max_time, mode_time))


def consume_station_materials(
    conn,
    *,
    product_code: str,
    station_id: str,
    work_order_quantity: int,
    consume_time: str,
) -> tuple[bool, list[dict[str, Any]]]:
    bom_rows = query_all(
        conn,
        """
        SELECT b.material_code, b.qty_per_unit
        FROM bom b
        WHERE b.product_code = ? AND b.consume_station_id = ?
        ORDER BY b.material_code
        """,
        (product_code, station_id),
    )
    if not bom_rows:
        return True, []

    conn.execute("SAVEPOINT consume_station_materials;")
    shortage_rows: list[dict[str, Any]] = []
    for row in bom_rows:
        required_qty = float(row["qty_per_unit"]) * float(work_order_quantity)
        material_code = row["material_code"]
        updated = conn.execute(
            """
            UPDATE inventory
            SET current_qty = current_qty - ?, updated_at = ?
            WHERE material_code = ? AND current_qty >= ?
            """,
            (required_qty, consume_time, material_code, required_qty),
        )
        if updated.rowcount == 0:
            qty_row = query_one(
                conn,
                "SELECT COALESCE(current_qty, 0) AS current_qty FROM inventory WHERE material_code = ?",
                (material_code,),
            )
            shortage_rows.append(
                {
                    "material_code": material_code,
                    "required_qty": required_qty,
                    "current_qty": float(qty_row["current_qty"]) if qty_row else 0.0,
                }
            )

    if shortage_rows:
        conn.execute("ROLLBACK TO SAVEPOINT consume_station_materials;")
        conn.execute("RELEASE SAVEPOINT consume_station_materials;")
        return False, shortage_rows

    conn.execute("RELEASE SAVEPOINT consume_station_materials;")
    return True, []


class BuiltinSimulationStrategy:
    strategy_name = "builtin_v1"

    def run(self, conn, payload: SimulationRequest) -> dict[str, Any]:
        run_id = payload.run_id
        defect_rate_map = {
            "S1_normal": 0.08,
            "S2_rush": 0.12,
            "S3_fault": 0.18,
        }
        defect_rate = defect_rate_map.get(payload.scenario, 0.1)

        pending_tasks = query_all(
            conn,
            """
            SELECT
                st.*,
                wo.order_no,
                wo.product_code,
                wo.quantity
            FROM schedule_task st
            JOIN work_order wo ON wo.work_order_no = st.work_order_no
            WHERE st.status = ?
            ORDER BY st.planned_start ASC, st.work_order_no ASC, st.sequence ASC
            """,
            (TASK_STATUS_PENDING,),
        )
        if not pending_tasks:
            raise HTTPException(status_code=400, detail="无待执行排产任务")

        selected_work_orders: list[str] = []
        selected_set: set[str] = set()
        for task in pending_tasks:
            work_order_no = task["work_order_no"]
            if (
                work_order_no not in selected_set
                and len(selected_work_orders) < payload.order_count
            ):
                selected_set.add(work_order_no)
                selected_work_orders.append(work_order_no)
        if not selected_work_orders:
            raise HTTPException(status_code=400, detail="无可执行工单")

        placeholders = ",".join("?" for _ in selected_work_orders)
        conn.execute(
            f"""
            UPDATE work_order
            SET work_order_status = ?
            WHERE work_order_no IN ({placeholders})
            """,
            (WORK_ORDER_STATUS_IN_PROGRESS, *selected_work_orders),
        )
        conn.execute(
            f"""
            UPDATE sales_order
            SET order_status = ?
            WHERE order_no IN (
                SELECT order_no
                FROM work_order
                WHERE work_order_no IN ({placeholders})
            )
            """,
            (ORDER_STATUS_IN_PRODUCTION, *selected_work_orders),
        )

        tasks = [task for task in pending_tasks if task["work_order_no"] in selected_set]
        station_params = get_station_params(conn)
        planned_time_candidates = [
            parse_datetime(task["planned_start"]) for task in tasks if task["planned_start"]
        ]
        base_time = min(planned_time_candidates) if planned_time_candidates else datetime.now()
        station_available_min: dict[str, float] = {
            row["station_id"]: 0.0
            for row in query_all(conn, "SELECT station_id FROM station")
        }
        work_order_available_min: dict[str, float] = {}
        work_order_start: dict[str, str] = {}
        work_order_end: dict[str, str] = {}
        work_order_scrapped: set[str] = set()
        work_order_repair_count: dict[str, int] = {}
        work_order_waiting_rework: set[str] = set()
        work_order_waiting_material: set[str] = set()
        deferred_pack_task_by_work_order: dict[str, dict[str, Any]] = {}

        fault_injected = False
        rush_logged = False
        executed_task_count = 0
        events_created = 0
        quality_created = 0

        task_queue: list[dict[str, Any]] = list(tasks)
        cursor = 0
        while cursor < len(task_queue):
            task = task_queue[cursor]
            cursor += 1

            work_order_no = task["work_order_no"]
            station_id = task["station_id"]
            task_id = task.get("id")

            if work_order_no in work_order_scrapped:
                if task_id is not None:
                    conn.execute(
                        """
                        UPDATE schedule_task
                        SET status = ?
                        WHERE id = ? AND status = ?
                        """,
                        (TASK_STATUS_COMPLETED, task_id, TASK_STATUS_PENDING),
                    )
                continue

            if work_order_no in work_order_waiting_material:
                continue

            if station_id == PACK_STATION_ID and work_order_no in work_order_waiting_rework:
                deferred_pack_task_by_work_order.setdefault(work_order_no, task)
                continue

            station = station_params.get(station_id)
            if not station:
                raise HTTPException(status_code=400, detail=f"工位参数缺失: {station_id}")

            start_min = max(
                station_available_min.get(station_id, 0.0),
                work_order_available_min.get(work_order_no, 0.0),
            )
            actual_start = (base_time + timedelta(minutes=start_min)).strftime(DATETIME_FMT)

            can_consume_material, _ = consume_station_materials(
                conn,
                product_code=task["product_code"],
                station_id=station_id,
                work_order_quantity=int(task["quantity"]),
                consume_time=actual_start,
            )
            if not can_consume_material:
                work_order_waiting_material.add(work_order_no)
                if task_id is not None:
                    conn.execute(
                        """
                        UPDATE schedule_task
                        SET status = ?
                        WHERE id = ? AND status = ?
                        """,
                        (TASK_STATUS_PENDING, task_id, TASK_STATUS_PENDING),
                    )
                continue

            if (
                payload.scenario == SCENARIO_S3_FAULT
                and payload.fault_station
                and station_id == payload.fault_station
                and not fault_injected
                and payload.fault_duration_min > 0
            ):
                fault_start = (base_time + timedelta(minutes=start_min)).strftime(DATETIME_FMT)
                fault_end = (
                    base_time + timedelta(minutes=start_min + payload.fault_duration_min)
                ).strftime(DATETIME_FMT)
                insert_event(
                    conn,
                    run_id=run_id,
                    work_order_no=work_order_no,
                    station_id=station_id,
                    event_type=EVENT_FAULT_START,
                    event_time=fault_start,
                    remark="故障注入",
                )
                insert_event(
                    conn,
                    run_id=run_id,
                    work_order_no=work_order_no,
                    station_id=station_id,
                    event_type=EVENT_FAULT_END,
                    event_time=fault_end,
                    remark="故障恢复",
                )
                events_created += 2
                start_min += payload.fault_duration_min
                fault_injected = True

            if (
                payload.scenario == SCENARIO_S2_RUSH
                and payload.rush_order_at_min is not None
                and not rush_logged
                and start_min >= payload.rush_order_at_min
            ):
                rush_time = (
                    base_time + timedelta(minutes=payload.rush_order_at_min)
                ).strftime(DATETIME_FMT)
                insert_event(
                    conn,
                    run_id=run_id,
                    work_order_no=work_order_no,
                    station_id=station_id,
                    event_type=EVENT_RUSH_ORDER,
                    event_time=rush_time,
                    remark="插单扰动事件",
                )
                events_created += 1
                rush_logged = True

            duration_sec = sample_duration_seconds(station)
            duration_min = duration_sec / 60.0
            end_min = start_min + duration_min
            actual_end = (base_time + timedelta(minutes=end_min)).strftime(DATETIME_FMT)

            if task_id is not None:
                conn.execute(
                    """
                    UPDATE schedule_task
                    SET actual_start = ?, status = ?
                    WHERE id = ?
                    """,
                    (actual_start, TASK_STATUS_IN_PROGRESS, task_id),
                )
                conn.execute(
                    """
                    UPDATE schedule_task
                    SET actual_end = ?, status = ?
                    WHERE id = ?
                    """,
                    (actual_end, TASK_STATUS_COMPLETED, task_id),
                )

            insert_event(
                conn,
                run_id=run_id,
                work_order_no=work_order_no,
                station_id=station_id,
                event_type=EVENT_START,
                event_time=actual_start,
            )
            insert_event(
                conn,
                run_id=run_id,
                work_order_no=work_order_no,
                station_id=station_id,
                event_type=EVENT_COMPLETE,
                event_time=actual_end,
            )
            events_created += 2
            executed_task_count += 1

            if station_id in NEXT_STATION_BY_STATION_ID:
                next_station_id = NEXT_STATION_BY_STATION_ID[station_id]
                insert_event(
                    conn,
                    run_id=run_id,
                    work_order_no=work_order_no,
                    station_id=station_id,
                    event_type=EVENT_TRANSFER,
                    event_time=actual_end,
                    remark=f"流转至下一工位 {next_station_id}",
                )
                events_created += 1

            if station_id == QC_STATION_ID:
                repaired_before = work_order_repair_count.get(work_order_no, 0)
                quality_result = QUALITY_RESULT_PASS
                if random.random() < defect_rate:
                    if repaired_before < MAX_REPAIR_COUNT:
                        quality_result = QUALITY_RESULT_REPAIR
                    else:
                        quality_result = QUALITY_RESULT_SCRAP

                insert_quality_record(
                    conn,
                    run_id=run_id,
                    work_order_no=work_order_no,
                    inspect_time=actual_end,
                    quality_result=quality_result,
                    repair_count=repaired_before,
                    remark=f"scenario={payload.scenario}",
                )
                quality_created += 1

                qc_event = EVENT_QC_PASS
                if quality_result == QUALITY_RESULT_REPAIR:
                    qc_event = EVENT_QC_REPAIR
                    work_order_repair_count[work_order_no] = repaired_before + 1
                    work_order_waiting_rework.add(work_order_no)
                    task_queue.append(
                        {
                            "id": None,
                            "work_order_no": work_order_no,
                            "order_no": task["order_no"],
                            "product_code": task["product_code"],
                            "quantity": task["quantity"],
                            "station_id": REWORK_STATION_ID,
                            "sequence": 303,
                        }
                    )
                    task_queue.append(
                        {
                            "id": None,
                            "work_order_no": work_order_no,
                            "order_no": task["order_no"],
                            "product_code": task["product_code"],
                            "quantity": task["quantity"],
                            "station_id": QC_STATION_ID,
                            "sequence": 404,
                        }
                    )
                    insert_event(
                        conn,
                        run_id=run_id,
                        work_order_no=work_order_no,
                        station_id=station_id,
                        event_type=EVENT_TRANSFER,
                        event_time=actual_end,
                        remark=f"质检返修回流至 {REWORK_STATION_ID}",
                    )
                    events_created += 1
                elif quality_result == QUALITY_RESULT_SCRAP:
                    qc_event = EVENT_QC_SCRAP
                    work_order_waiting_rework.discard(work_order_no)
                    work_order_scrapped.add(work_order_no)
                    deferred_pack_task_by_work_order.pop(work_order_no, None)
                else:
                    work_order_waiting_rework.discard(work_order_no)
                    deferred_pack_task = deferred_pack_task_by_work_order.pop(
                        work_order_no,
                        None,
                    )
                    if deferred_pack_task is not None:
                        task_queue.append(deferred_pack_task)
                    insert_event(
                        conn,
                        run_id=run_id,
                        work_order_no=work_order_no,
                        station_id=station_id,
                        event_type=EVENT_TRANSFER,
                        event_time=actual_end,
                        remark=f"质检通过流转至 {PACK_STATION_ID}",
                    )
                    events_created += 1

                insert_event(
                    conn,
                    run_id=run_id,
                    work_order_no=work_order_no,
                    station_id=station_id,
                    event_type=qc_event,
                    event_time=actual_end,
                    remark=f"quality_result={quality_result}, repaired_before={repaired_before}",
                )
                events_created += 1

            if work_order_no not in work_order_start:
                work_order_start[work_order_no] = actual_start
            work_order_end[work_order_no] = actual_end
            station_available_min[station_id] = end_min
            work_order_available_min[work_order_no] = end_min

        for work_order_no in selected_work_orders:
            if work_order_no in work_order_scrapped:
                final_status = WORK_ORDER_STATUS_SCRAPPED
            else:
                has_pending_task = query_one(
                    conn,
                    """
                    SELECT 1 AS flag
                    FROM schedule_task
                    WHERE work_order_no = ? AND status = ?
                    LIMIT 1
                    """,
                    (work_order_no, TASK_STATUS_PENDING),
                )
                if (
                    has_pending_task
                    or work_order_no in work_order_waiting_material
                    or work_order_no in work_order_waiting_rework
                ):
                    final_status = WORK_ORDER_STATUS_IN_PROGRESS
                else:
                    final_status = WORK_ORDER_STATUS_COMPLETED

            actual_start = work_order_start.get(work_order_no)
            actual_end = work_order_end.get(work_order_no)
            conn.execute(
                """
                UPDATE work_order
                SET work_order_status = ?, actual_start = ?, actual_end = ?
                WHERE work_order_no = ?
                """,
                (final_status, actual_start, actual_end, work_order_no),
            )

            if final_status == WORK_ORDER_STATUS_SCRAPPED and actual_end:
                conn.execute(
                    """
                    UPDATE schedule_task
                    SET status = ?,
                        actual_start = COALESCE(actual_start, ?),
                        actual_end = COALESCE(actual_end, ?)
                    WHERE work_order_no = ? AND status = ?
                    """,
                    (
                        TASK_STATUS_COMPLETED,
                        actual_end,
                        actual_end,
                        work_order_no,
                        TASK_STATUS_PENDING,
                    ),
                )

            order_row = query_one(
                conn,
                """
                SELECT so.order_no, so.due_date
                FROM sales_order so
                JOIN work_order wo ON so.order_no = wo.order_no
                WHERE wo.work_order_no = ?
                """,
                (work_order_no,),
            )
            if not order_row:
                continue

            if final_status == WORK_ORDER_STATUS_IN_PROGRESS:
                order_status = ORDER_STATUS_IN_PRODUCTION
            else:
                order_status = ORDER_STATUS_COMPLETED
                if final_status == WORK_ORDER_STATUS_COMPLETED and actual_end:
                    if datetime.strptime(actual_end, DATETIME_FMT).date() > datetime.strptime(
                        order_row["due_date"],
                        DATE_FMT,
                    ).date():
                        order_status = ORDER_STATUS_OVERDUE
            conn.execute(
                "UPDATE sales_order SET order_status = ? WHERE order_no = ?",
                (order_status, order_row["order_no"]),
            )

        return {
            "scenario": payload.scenario,
            "processed_work_orders": len(selected_work_orders),
            "processed_tasks": executed_task_count,
            "events_created": events_created,
            "quality_records_created": quality_created,
        }


ACTIVE_SIMULATION_STRATEGY: SimulationStrategy = load_strategy(BuiltinSimulationStrategy())


def run_simulation(payload: SimulationRequest) -> dict[str, Any]:
    if payload.scenario not in SCENARIO_CODES:
        raise HTTPException(status_code=400, detail="scenario 仅支持 S1_normal/S2_rush/S3_fault")

    strategy_name = ACTIVE_SIMULATION_STRATEGY.strategy_name
    run_id = create_run_id()
    runtime_payload = payload.model_copy(update={"run_id": run_id})

    with write_transaction() as conn:
        create_simulation_run(
            conn,
            run_id=run_id,
            payload=runtime_payload,
            strategy_name=strategy_name,
        )
        raw_strategy_result = ACTIVE_SIMULATION_STRATEGY.run(conn, runtime_payload)
        strategy_result = validate_strategy_result(
            raw_strategy_result,
            expected_scenario=runtime_payload.scenario,
        )
        kpi = compute_and_store_kpi(conn, runtime_payload.scenario, run_id)
        response_data = {
            **strategy_result,
            "run_id": run_id,
            "strategy_name": strategy_name,
            "kpi_snapshot": kpi,
        }
        complete_simulation_run(conn, run_id=run_id, result=response_data)

    return response_data


def list_events(limit: int, run_id: str | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if run_id:
            return query_all(
                conn,
                """
                SELECT *
                FROM production_event
                WHERE run_id = ?
                ORDER BY event_time DESC, id DESC
                LIMIT ?
                """,
                (run_id, limit),
            )
        return query_all(
            conn,
            """
            SELECT *
            FROM production_event
            ORDER BY event_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )


def list_quality_records(limit: int, run_id: str | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if run_id:
            return query_all(
                conn,
                """
                SELECT *
                FROM quality_record
                WHERE run_id = ?
                ORDER BY inspect_time DESC, id DESC
                LIMIT ?
                """,
                (run_id, limit),
            )
        return query_all(
            conn,
            """
            SELECT *
            FROM quality_record
            ORDER BY inspect_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )


def get_station_status() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = query_all(
            conn,
            """
            SELECT
                s.station_id,
                s.station_name,
                COALESCE(ev.fault_start_cnt, 0) AS fault_start_cnt,
                COALESCE(ev.fault_end_cnt, 0) AS fault_end_cnt,
                COALESCE(wm.waiting_material_cnt, 0) AS waiting_material_cnt,
                COALESCE(ts.busy_cnt, 0) AS busy_cnt,
                COALESCE(bl.blocked_cnt, 0) AS blocked_cnt,
                COALESCE(ts.pending_cnt, 0) AS pending_cnt
            FROM station s
            LEFT JOIN (
                SELECT
                    station_id,
                    SUM(CASE WHEN event_type = ? THEN 1 ELSE 0 END) AS fault_start_cnt,
                    SUM(CASE WHEN event_type = ? THEN 1 ELSE 0 END) AS fault_end_cnt
                FROM production_event
                GROUP BY station_id
            ) ev ON s.station_id = ev.station_id
            LEFT JOIN (
                SELECT
                    st.station_id,
                    SUM(
                        CASE
                            WHEN COALESCE(i.current_qty, 0) < (b.qty_per_unit * wo.quantity)
                            THEN 1
                            ELSE 0
                        END
                    ) AS waiting_material_cnt
                FROM schedule_task st
                JOIN work_order wo ON st.work_order_no = wo.work_order_no
                JOIN bom b
                  ON b.product_code = wo.product_code
                 AND b.consume_station_id = st.station_id
                LEFT JOIN inventory i ON b.material_code = i.material_code
                WHERE st.status IN (?, ?)
                GROUP BY st.station_id
            ) wm ON s.station_id = wm.station_id
            LEFT JOIN (
                SELECT
                    station_id,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS busy_cnt,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS pending_cnt
                FROM schedule_task
                GROUP BY station_id
            ) ts ON s.station_id = ts.station_id
            LEFT JOIN (
                SELECT
                    cur.station_id,
                    SUM(CASE WHEN nxt.id IS NOT NULL THEN 1 ELSE 0 END) AS blocked_cnt
                FROM schedule_task cur
                LEFT JOIN schedule_task nxt
                  ON cur.work_order_no = nxt.work_order_no
                 AND nxt.sequence = cur.sequence + 1
                 AND nxt.status = ?
                WHERE cur.status = ?
                GROUP BY cur.station_id
            ) bl ON s.station_id = bl.station_id
            ORDER BY s.station_id ASC
            """,
            (
                EVENT_FAULT_START,
                EVENT_FAULT_END,
                TASK_STATUS_PENDING,
                TASK_STATUS_IN_PROGRESS,
                TASK_STATUS_IN_PROGRESS,
                TASK_STATUS_PENDING,
                TASK_STATUS_PENDING,
                TASK_STATUS_COMPLETED,
            ),
        )

    result = []
    for row in rows:
        if row["fault_start_cnt"] > row["fault_end_cnt"]:
            status = STATION_STATUS_FAULT
        elif row["waiting_material_cnt"] > 0:
            status = STATION_STATUS_WAITING_MATERIAL
        elif row["busy_cnt"] > 0:
            status = STATION_STATUS_BUSY
        elif row["blocked_cnt"] > 0:
            status = STATION_STATUS_BLOCKED
        elif row["pending_cnt"] > 0:
            status = STATION_STATUS_WAITING
        else:
            status = STATION_STATUS_IDLE

        result.append(
            {
                "station_id": row["station_id"],
                "station_name": row["station_name"],
                "status": status,
            }
        )

    return result
