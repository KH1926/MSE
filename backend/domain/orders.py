from __future__ import annotations

from typing import Any

from fastapi import HTTPException

try:
    from common import DATE_FMT, ORDER_STATUS_PENDING, ORDER_STATUS_SCHEDULED, now_str
    from common import WORK_ORDER_STATUS_PENDING
    from db import get_connection, query_all, query_one, write_transaction
    from contracts.request_models import OrderCreate
except ModuleNotFoundError:
    from ..common import DATE_FMT, ORDER_STATUS_PENDING, ORDER_STATUS_SCHEDULED, now_str
    from ..common import WORK_ORDER_STATUS_PENDING
    from ..db import get_connection, query_all, query_one, write_transaction
    from ..contracts.request_models import OrderCreate


def generate_doc_no(conn, table: str, column: str, prefix: str) -> str:
    today = now_str()[:10].replace("-", "")
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


def get_material_precheck(conn, product_code: str, quantity: int) -> list[dict[str, Any]]:
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


def list_orders() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return query_all(
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


def create_order(payload: OrderCreate) -> dict[str, Any]:
    with write_transaction() as conn:
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
        return query_one(conn, "SELECT * FROM sales_order WHERE order_no = ?", (order_no,))


def generate_work_order(order_no: str) -> dict[str, Any]:
    with write_transaction() as conn:
        order = query_one(conn, "SELECT * FROM sales_order WHERE order_no = ?", (order_no,))
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
        work_order = query_one(
            conn,
            "SELECT * FROM work_order WHERE work_order_no = ?",
            (work_order_no,),
        )
        return {"work_order": work_order, "material_precheck": material_precheck}
