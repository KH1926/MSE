from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    # 兼容在 backend 目录内直接运行：uvicorn main:app
    from db import DB_PATH, get_connection, init_db, query_all, query_one
    from simulation_strategy import SimulationStrategy, load_strategy
except ModuleNotFoundError:
    # 兼容在项目根目录按包运行：uvicorn backend.main:app
    from .db import DB_PATH, get_connection, init_db, query_all, query_one
    from .simulation_strategy import SimulationStrategy, load_strategy

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

# 协作契约中的统一枚举，集中定义可避免后续出现命名漂移。
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

app = FastAPI(title="生产管理后端服务", version="0.1.0")


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


@app.on_event("startup")
def startup_event() -> None:
    if not DB_PATH.exists():
        init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"internal error: {exc}", "data": None},
    )


def ok(data: Any) -> dict[str, Any]:
    return {"code": 200, "message": "ok", "data": data}


def now_str() -> str:
    return datetime.now().strftime(DATETIME_FMT)


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FMT)


def generate_doc_no(conn, table: str, column: str, prefix: str) -> str:
    # 统一编号规则：<前缀>-<YYYYMMDD>-<3位流水号>，与协作文档示例一致。
    today = datetime.now().strftime("%Y%m%d")
    like_pattern = f"{prefix}-{today}-%"
    row = query_one(
        conn,
        f"SELECT {column} AS doc_no FROM {table} WHERE {column} LIKE ? ORDER BY {column} DESC LIMIT 1",
        (like_pattern,),
    )
    next_seq = 1
    if row:
        next_seq = int(row["doc_no"].split("-")[-1]) + 1
    return f"{prefix}-{today}-{next_seq:03d}"


def get_station_params(conn) -> dict[str, dict[str, Any]]:
    rows = query_all(
        conn,
        """
        SELECT station_id, min_time, mode_time, max_time, sigma
        FROM station
        """,
    )
    return {row["station_id"]: row for row in rows}


def sample_duration_seconds(station_param: dict[str, Any]) -> float:
    # station 表参数统一以“秒”存储，仿真阶段再换算成分钟。
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


def get_material_precheck(
    conn, product_code: str, quantity: int
) -> list[dict[str, Any]]:
    # 订单转工单阶段只做预检查，不做库存扣减（扣减应发生在工位开工时）。
    rows = query_all(
        conn,
        """
        SELECT
            b.material_code,
            m.material_name,
            b.qty_per_unit,
            b.consume_station_id,
            COALESCE(i.current_qty, 0) AS current_qty,
            COALESCE(i.safety_qty, 0) AS safety_qty
        FROM bom b
        JOIN material m ON b.material_code = m.material_code
        LEFT JOIN inventory i ON b.material_code = i.material_code
        WHERE b.product_code = ?
        ORDER BY b.consume_station_id, b.material_code
        """,
        (product_code,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        required_qty = row["qty_per_unit"] * quantity
        current_qty = row["current_qty"]
        safety_qty = row["safety_qty"]
        if current_qty < required_qty:
            status = "insufficient"
        elif current_qty - required_qty < safety_qty:
            status = "low_after_production"
        else:
            status = "ok"
        result.append(
            {
                "material_code": row["material_code"],
                "material_name": row["material_name"],
                "consume_station_id": row["consume_station_id"],
                "required_qty": required_qty,
                "current_qty": current_qty,
                "safety_qty": safety_qty,
                "status": status,
            }
        )
    return result


def compute_and_store_kpi(conn, scenario: str) -> dict[str, Any]:
    # KPI 口径严格对齐《团队协作契约》第 7 节，避免前后端统计定义不一致。
    total_completed_row = query_one(
        conn,
        "SELECT COUNT(*) AS n FROM work_order WHERE work_order_status = ?",
        (WORK_ORDER_STATUS_COMPLETED,),
    )
    total_completed = int(total_completed_row["n"] if total_completed_row else 0)

    on_time_row = query_one(
        conn,
        """
        SELECT COUNT(*) AS n
        FROM work_order wo
        JOIN sales_order so ON wo.order_no = so.order_no
        WHERE wo.work_order_status = ?
          AND DATE(wo.actual_end) <= DATE(so.due_date)
        """,
        (WORK_ORDER_STATUS_COMPLETED,),
    )
    on_time_count = int(on_time_row["n"] if on_time_row else 0)
    on_time_rate = (on_time_count / total_completed) if total_completed else 0.0

    avg_lead_row = query_one(
        conn,
        """
        SELECT AVG((julianday(actual_end) - julianday(actual_start)) * 24.0 * 60.0) AS avg_mins
        FROM work_order
        WHERE work_order_status = ?
          AND actual_start IS NOT NULL
          AND actual_end IS NOT NULL
        """,
        (WORK_ORDER_STATUS_COMPLETED,),
    )
    avg_lead_time = float(avg_lead_row["avg_mins"] or 0.0)

    wip_row = query_one(
        conn,
        "SELECT COUNT(*) AS n FROM work_order WHERE work_order_status = ?",
        (WORK_ORDER_STATUS_IN_PROGRESS,),
    )
    wip_count = int(wip_row["n"] if wip_row else 0)

    total_quality_row = query_one(conn, "SELECT COUNT(*) AS n FROM quality_record")
    total_quality = int(total_quality_row["n"] if total_quality_row else 0)

    defect_row = query_one(
        conn,
        "SELECT COUNT(*) AS n FROM quality_record WHERE quality_result != ?",
        (QUALITY_RESULT_PASS,),
    )
    defect_count = int(defect_row["n"] if defect_row else 0)

    repair_row = query_one(
        conn,
        "SELECT COUNT(*) AS n FROM quality_record WHERE quality_result = ?",
        (QUALITY_RESULT_REPAIR,),
    )
    repair_count = int(repair_row["n"] if repair_row else 0)

    defect_rate = (defect_count / total_quality) if total_quality else 0.0
    repair_rate = (repair_count / total_quality) if total_quality else 0.0

    line_row = query_one(
        conn,
        "SELECT SUM(mode_time) AS total_mode, COUNT(*) AS cnt, MAX(mode_time) AS max_mode FROM station",
    )
    total_mode = float(line_row["total_mode"] or 0.0)
    cnt = int(line_row["cnt"] or 0)
    max_mode = float(line_row["max_mode"] or 0.0)
    line_balance_rate = (total_mode / (cnt * max_mode)) if cnt and max_mode else 0.0

    bottleneck_row = query_one(
        conn,
        "SELECT station_id FROM station ORDER BY mode_time DESC LIMIT 1",
    )
    bottleneck_station = (
        bottleneck_row["station_id"] if bottleneck_row else DEFAULT_BOTTLENECK_STATION_ID
    )

    snapshot = {
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
            snapshot_time, scenario, total_completed, on_time_rate, avg_lead_time,
            wip_count, defect_rate, repair_rate, line_balance_rate, bottleneck_station
        )
        VALUES (
            :snapshot_time, :scenario, :total_completed, :on_time_rate, :avg_lead_time,
            :wip_count, :defect_rate, :repair_rate, :line_balance_rate, :bottleneck_station
        )
        """,
        snapshot,
    )
    return snapshot


class BuiltinSimulationStrategy:
    strategy_name = "builtin_v1"

    def run(self, conn, payload: SimulationRequest) -> dict[str, Any]:
        defect_rate_map = {
            SCENARIO_S1_NORMAL: 0.08,
            SCENARIO_S2_RUSH: 0.12,
            SCENARIO_S3_FAULT: 0.18,
        }
        defect_rate = defect_rate_map.get(payload.scenario, 0.1)

        pending_tasks = query_all(
            conn,
            """
            SELECT st.*, wo.order_no
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
            wo = task["work_order_no"]
            if wo not in selected_set and len(selected_work_orders) < payload.order_count:
                selected_set.add(wo)
                selected_work_orders.append(wo)
        if not selected_work_orders:
            raise HTTPException(status_code=400, detail="无可执行工单")

        # 仿真执行阶段将工单/订单置为生产中，确保状态枚举与协作契约一致。
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

        tasks = [t for t in pending_tasks if t["work_order_no"] in selected_set]
        station_params = get_station_params(conn)

        base_time = datetime.now()
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
        deferred_pack_task_by_work_order: dict[str, dict[str, Any]] = {}

        fault_injected = False
        rush_logged = False
        executed_task_count = 0
        events_created = 0
        quality_created = 0

        # 使用任务队列驱动仿真：在首检触发返修时，动态追加 WS30/WS40 回流任务。
        task_queue: list[dict[str, Any]] = list(tasks)
        cursor = 0
        while cursor < len(task_queue):
            task = task_queue[cursor]
            cursor += 1

            wo = task["work_order_no"]
            station_id = task["station_id"]
            task_id = task.get("id")

            if wo in work_order_scrapped:
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

            if station_id == PACK_STATION_ID and wo in work_order_waiting_rework:
                # WS50 先挂起，待返修闭环在 WS40 判定 pass 后再执行。
                deferred_pack_task_by_work_order.setdefault(wo, task)
                continue

            station = station_params.get(station_id)
            if not station:
                raise HTTPException(
                    status_code=400, detail=f"工位参数缺失: {station_id}"
                )

            start_min = max(
                station_available_min.get(station_id, 0.0),
                work_order_available_min.get(wo, 0.0),
            )

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
                conn.execute(
                    """
                    INSERT INTO production_event (
                        work_order_no, station_id, event_type, event_time, remark
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (wo, station_id, EVENT_FAULT_START, fault_start, "故障注入"),
                )
                conn.execute(
                    """
                    INSERT INTO production_event (
                        work_order_no, station_id, event_type, event_time, remark
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (wo, station_id, EVENT_FAULT_END, fault_end, "故障恢复"),
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
                conn.execute(
                    """
                    INSERT INTO production_event (
                        work_order_no, station_id, event_type, event_time, remark
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (wo, station_id, EVENT_RUSH_ORDER, rush_time, "插单扰动事件"),
                )
                events_created += 1
                rush_logged = True

            duration_sec = sample_duration_seconds(station)
            duration_min = duration_sec / 60.0
            end_min = start_min + duration_min

            actual_start = (base_time + timedelta(minutes=start_min)).strftime(DATETIME_FMT)
            actual_end = (base_time + timedelta(minutes=end_min)).strftime(DATETIME_FMT)

            # 排产表仅维护主路线任务，返修回流任务只写事件/质检，不新增 schedule_task。
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
            conn.execute(
                """
                INSERT INTO production_event (
                    work_order_no, station_id, event_type, event_time, remark
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (wo, station_id, EVENT_START, actual_start, None),
            )
            conn.execute(
                """
                INSERT INTO production_event (
                    work_order_no, station_id, event_type, event_time, remark
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (wo, station_id, EVENT_COMPLETE, actual_end, None),
            )
            events_created += 2
            executed_task_count += 1

            if station_id in NEXT_STATION_BY_STATION_ID:
                next_station_id = NEXT_STATION_BY_STATION_ID[station_id]
                conn.execute(
                    """
                    INSERT INTO production_event (
                        work_order_no, station_id, event_type, event_time, remark
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        wo,
                        station_id,
                        EVENT_TRANSFER,
                        actual_end,
                        f"流转至下一工位 {next_station_id}",
                    ),
                )
                events_created += 1

            if station_id == QC_STATION_ID:
                repaired_before = work_order_repair_count.get(wo, 0)
                quality_result = QUALITY_RESULT_PASS
                if random.random() < defect_rate:
                    if repaired_before < MAX_REPAIR_COUNT:
                        quality_result = QUALITY_RESULT_REPAIR
                    else:
                        quality_result = QUALITY_RESULT_SCRAP

                conn.execute(
                    """
                    INSERT INTO quality_record (
                        work_order_no, inspect_time, quality_result, repair_count, remark
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        wo,
                        actual_end,
                        quality_result,
                        repaired_before,
                        f"scenario={payload.scenario}",
                    ),
                )
                quality_created += 1

                qc_event = EVENT_QC_PASS
                if quality_result == QUALITY_RESULT_REPAIR:
                    qc_event = EVENT_QC_REPAIR
                    work_order_repair_count[wo] = repaired_before + 1
                    work_order_waiting_rework.add(wo)
                    task_queue.append(
                        {
                            "id": None,
                            "work_order_no": wo,
                            "order_no": task["order_no"],
                            "station_id": REWORK_STATION_ID,
                            "sequence": 303,
                        }
                    )
                    task_queue.append(
                        {
                            "id": None,
                            "work_order_no": wo,
                            "order_no": task["order_no"],
                            "station_id": QC_STATION_ID,
                            "sequence": 404,
                        }
                    )
                    conn.execute(
                        """
                        INSERT INTO production_event (
                            work_order_no, station_id, event_type, event_time, remark
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            wo,
                            station_id,
                            EVENT_TRANSFER,
                            actual_end,
                            f"质检返修回流至 {REWORK_STATION_ID}",
                        ),
                    )
                    events_created += 1
                elif quality_result == QUALITY_RESULT_SCRAP:
                    qc_event = EVENT_QC_SCRAP
                    work_order_waiting_rework.discard(wo)
                    work_order_scrapped.add(wo)
                    deferred_pack_task_by_work_order.pop(wo, None)
                else:
                    work_order_waiting_rework.discard(wo)
                    deferred_pack_task = deferred_pack_task_by_work_order.pop(wo, None)
                    if deferred_pack_task is not None:
                        task_queue.append(deferred_pack_task)
                    conn.execute(
                        """
                        INSERT INTO production_event (
                            work_order_no, station_id, event_type, event_time, remark
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            wo,
                            station_id,
                            EVENT_TRANSFER,
                            actual_end,
                            f"质检通过流转至 {PACK_STATION_ID}",
                        ),
                    )
                    events_created += 1

                conn.execute(
                    """
                    INSERT INTO production_event (
                        work_order_no, station_id, event_type, event_time, remark
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        wo,
                        station_id,
                        qc_event,
                        actual_end,
                        f"quality_result={quality_result}, repaired_before={repaired_before}",
                    ),
                )
                events_created += 1

            if wo not in work_order_start:
                work_order_start[wo] = actual_start
            work_order_end[wo] = actual_end
            station_available_min[station_id] = end_min
            work_order_available_min[wo] = end_min

        for wo in selected_work_orders:
            final_status = (
                WORK_ORDER_STATUS_SCRAPPED
                if wo in work_order_scrapped
                else WORK_ORDER_STATUS_COMPLETED
            )
            actual_start = work_order_start.get(wo)
            actual_end = work_order_end.get(wo)
            conn.execute(
                """
                UPDATE work_order
                SET work_order_status = ?, actual_start = ?, actual_end = ?
                WHERE work_order_no = ?
                """,
                (final_status, actual_start, actual_end, wo),
            )

            if final_status == WORK_ORDER_STATUS_SCRAPPED and actual_end:
                # 报废后主路线残留 pending 任务视作关闭，避免看板长期停留 waiting。
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
                        wo,
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
                (wo,),
            )
            if not order_row:
                continue
            order_status = ORDER_STATUS_COMPLETED
            if final_status == WORK_ORDER_STATUS_COMPLETED and actual_end:
                if datetime.strptime(actual_end, DATETIME_FMT).date() > datetime.strptime(
                    order_row["due_date"], DATE_FMT
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


@app.get("/")
def home() -> dict[str, Any]:
    return ok({"service": "manufacturing-backend", "version": "0.1.0"})


@app.get("/orders")
def get_orders() -> dict[str, Any]:
    with get_connection() as conn:
        rows = query_all(
            conn,
            """
            SELECT
                so.*,
                wo.work_order_no,
                wo.work_order_status
            FROM sales_order so
            LEFT JOIN work_order wo ON so.order_no = wo.order_no
            ORDER BY so.created_at DESC, so.order_no DESC
            """,
        )
    return ok(rows)


@app.post("/orders")
def create_order(payload: OrderCreate) -> dict[str, Any]:
    with get_connection() as conn:
        product = query_one(
            conn,
            "SELECT product_code FROM product WHERE product_code = ?",
            (payload.product_code,),
        )
        if not product:
            raise HTTPException(status_code=400, detail="product_code 不存在")

        order_no = generate_doc_no(conn, "sales_order", "order_no", "SO")
        created_at = now_str()
        conn.execute(
            """
            INSERT INTO sales_order (
                order_no, product_code, quantity, due_date, priority, order_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_no,
                payload.product_code,
                payload.quantity,
                payload.due_date.strftime(DATE_FMT),
                payload.priority,
                ORDER_STATUS_PENDING,
                created_at,
            ),
        )
        conn.commit()
        row = query_one(conn, "SELECT * FROM sales_order WHERE order_no = ?", (order_no,))
    return ok(row)


@app.post("/orders/{order_no}/generate-work-order")
def generate_work_order(order_no: str) -> dict[str, Any]:
    with get_connection() as conn:
        order = query_one(
            conn,
            "SELECT * FROM sales_order WHERE order_no = ?",
            (order_no,),
        )
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        existing = query_one(
            conn,
            "SELECT work_order_no FROM work_order WHERE order_no = ?",
            (order_no,),
        )
        if existing:
            raise HTTPException(status_code=400, detail="该订单已生成工单")

        material_precheck = get_material_precheck(
            conn,
            order["product_code"],
            int(order["quantity"]),
        )

        # 订单转工单后，订单状态应从 pending 进入 scheduled。
        work_order_no = generate_doc_no(conn, "work_order", "work_order_no", "WO")
        created_at = now_str()
        conn.execute(
            """
            INSERT INTO work_order (
                work_order_no, order_no, product_code, quantity,
                work_order_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                work_order_no,
                order_no,
                order["product_code"],
                order["quantity"],
                WORK_ORDER_STATUS_PENDING,
                created_at,
            ),
        )
        conn.execute(
            "UPDATE sales_order SET order_status = ? WHERE order_no = ?",
            (ORDER_STATUS_SCHEDULED, order_no),
        )
        conn.commit()
        work_order = query_one(
            conn,
            "SELECT * FROM work_order WHERE work_order_no = ?",
            (work_order_no,),
        )
    return ok({"work_order": work_order, "material_precheck": material_precheck})


@app.post("/schedule")
def run_schedule(payload: ScheduleRequest) -> dict[str, Any]:
    with get_connection() as conn:
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

        for wo in work_orders:
            existing_count = query_one(
                conn,
                "SELECT COUNT(*) AS n FROM schedule_task WHERE work_order_no = ?",
                (wo["work_order_no"],),
            )
            if existing_count and existing_count["n"] > 0 and not payload.force_reschedule:
                continue
            if payload.force_reschedule:
                conn.execute(
                    "DELETE FROM schedule_task WHERE work_order_no = ?",
                    (wo["work_order_no"],),
                )

            route = query_all(
                conn,
                """
                SELECT station_id, sequence
                FROM process_route
                WHERE product_code = ?
                ORDER BY sequence ASC
                """,
                (wo["product_code"],),
            )
            if not route:
                raise HTTPException(
                    status_code=400,
                    detail=f"产品 {wo['product_code']} 缺少工艺路线",
                )

            wo_ready_min = 0.0
            first_start: str | None = None
            last_end: str | None = None
            for step in route:
                station_id = step["station_id"]
                sequence = step["sequence"]
                station = station_map.get(station_id)
                if not station:
                    raise HTTPException(
                        status_code=400, detail=f"工位 {station_id} 参数缺失"
                    )
                duration_min = float(station["mode_time"]) / 60.0
                start_min = max(wo_ready_min, station_available_min.get(station_id, 0.0))
                end_min = start_min + duration_min

                # 排产阶段按基准节拍（mode_time）生成计划时间，不引入随机波动。
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
                        wo["work_order_no"],
                        station_id,
                        sequence,
                        planned_start,
                        planned_end,
                        TASK_STATUS_PENDING,
                    ),
                )
                task_count += 1
                station_available_min[station_id] = end_min
                wo_ready_min = end_min

            conn.execute(
                """
                UPDATE work_order
                SET scheduled_start = ?, scheduled_end = ?
                WHERE work_order_no = ?
                """,
                (first_start, last_end, wo["work_order_no"]),
            )
            scheduled_count += 1

        conn.commit()

    return ok(
        {
            "scheduled_work_orders": scheduled_count,
            "created_tasks": task_count,
            "force_reschedule": payload.force_reschedule,
        }
    )


@app.get("/schedule/tasks")
def get_schedule_tasks() -> dict[str, Any]:
    with get_connection() as conn:
        rows = query_all(
            conn,
            """
            SELECT *
            FROM schedule_task
            ORDER BY planned_start ASC, work_order_no ASC, sequence ASC
            """,
        )
    return ok(rows)


@app.post("/simulation/run")
def run_simulation(payload: SimulationRequest) -> dict[str, Any]:
    if payload.scenario not in SCENARIO_CODES:
        raise HTTPException(status_code=400, detail="scenario 仅支持 S1_normal/S2_rush/S3_fault")

    with get_connection() as conn:
        strategy_result = ACTIVE_SIMULATION_STRATEGY.run(conn, payload)
        kpi = compute_and_store_kpi(conn, payload.scenario)
        conn.commit()

    return ok({**strategy_result, "kpi_snapshot": kpi})


@app.get("/events")
def get_events(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    with get_connection() as conn:
        rows = query_all(
            conn,
            """
            SELECT *
            FROM production_event
            ORDER BY event_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    return ok(rows)


@app.get("/quality/records")
def get_quality_records(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, Any]:
    with get_connection() as conn:
        rows = query_all(
            conn,
            """
            SELECT *
            FROM quality_record
            ORDER BY inspect_time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    return ok(rows)


@app.get("/kpi/latest")
def get_kpi_latest() -> dict[str, Any]:
    with get_connection() as conn:
        row = query_one(
            conn,
            """
            SELECT *
            FROM kpi_snapshot
            ORDER BY id DESC
            LIMIT 1
            """,
        )
    return ok(row or {})


@app.get("/kpi/compare")
def get_kpi_compare() -> dict[str, Any]:
    with get_connection() as conn:
        rows = query_all(
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
    return ok(rows)


@app.get("/stations/status")
def get_station_status() -> dict[str, Any]:
    with get_connection() as conn:
        stations = query_all(
            conn,
            """
            SELECT station_id, station_name
            FROM station
            ORDER BY station_id ASC
            """,
        )
        result = []
        for station in stations:
            sid = station["station_id"]

            fault_start = query_one(
                conn,
                """
                SELECT COUNT(*) AS n
                FROM production_event
                WHERE station_id = ? AND event_type = ?
                """,
                (sid, EVENT_FAULT_START),
            )["n"]
            fault_end = query_one(
                conn,
                """
                SELECT COUNT(*) AS n
                FROM production_event
                WHERE station_id = ? AND event_type = ?
                """,
                (sid, EVENT_FAULT_END),
            )["n"]
            if fault_start > fault_end:
                status = STATION_STATUS_FAULT
            else:
                waiting_material = query_one(
                    conn,
                    """
                    SELECT 1 AS flag
                    FROM bom b
                    LEFT JOIN inventory i ON b.material_code = i.material_code
                    WHERE b.consume_station_id = ?
                      AND COALESCE(i.current_qty, 0) <= 0
                    LIMIT 1
                    """,
                    (sid,),
                )
                if waiting_material:
                    status = STATION_STATUS_WAITING_MATERIAL
                else:
                    busy_task = query_one(
                        conn,
                        """
                        SELECT 1 AS flag
                        FROM schedule_task
                        WHERE station_id = ? AND status = ?
                        LIMIT 1
                        """,
                        (sid, TASK_STATUS_IN_PROGRESS),
                    )
                    if busy_task:
                        status = STATION_STATUS_BUSY
                    else:
                        blocked_task = query_one(
                            conn,
                            """
                            SELECT 1 AS flag
                            FROM schedule_task cur
                            JOIN schedule_task nxt
                              ON cur.work_order_no = nxt.work_order_no
                             AND nxt.sequence = cur.sequence + 1
                            WHERE cur.station_id = ?
                              AND cur.status = ?
                              AND nxt.status = ?
                            LIMIT 1
                            """,
                            (sid, TASK_STATUS_COMPLETED, TASK_STATUS_PENDING),
                        )
                        if blocked_task:
                            status = STATION_STATUS_BLOCKED
                        else:
                            pending_task = query_one(
                                conn,
                                """
                                SELECT 1 AS flag
                                FROM schedule_task
                                WHERE station_id = ? AND status = ?
                                LIMIT 1
                                """,
                                (sid, TASK_STATUS_PENDING),
                            )
                            # 状态判断顺序遵循协作契约：故障 > 缺料 > 加工中 > 堵塞 > 等待 > 空闲。
                            status = (
                                STATION_STATUS_WAITING
                                if pending_task
                                else STATION_STATUS_IDLE
                            )

            result.append(
                {
                    "station_id": sid,
                    "station_name": station["station_name"],
                    "status": status,
                }
            )

    return ok(result)
