from __future__ import annotations

from datetime import datetime, timedelta

try:
    from db import get_connection, init_db
except ModuleNotFoundError:
    from .db import get_connection, init_db

PRODUCT_CODE = "CAR-001"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def seed_products(conn) -> None:
    conn.execute(
        """
        INSERT INTO product (product_code, product_name)
        VALUES (?, ?)
        """,
        (PRODUCT_CODE, "智能小车"),
    )


def seed_stations(conn) -> None:
    # 工位参数与《团队协作契约》保持一致：字段名固定为 min/mode/max/sigma（秒）。
    stations = [
        ("WS10", "底盘上线", 8.0, 10.0, 14.0, None, 1),
        ("WS20", "核心组装", 25.0, 30.0, 45.0, None, 1),
        ("WS30", "自动锁螺丝", None, 15.0, None, 0.5, 1),
        ("WS40", "视觉检测", None, 12.0, None, 0.2, 1),
        ("WS50", "成品包装", 9.0, 10.0, 13.0, None, 1),
    ]
    conn.executemany(
        """
        INSERT INTO station (
            station_id, station_name, min_time, mode_time, max_time, sigma, capacity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        stations,
    )


def seed_process_route(conn) -> None:
    routes = [
        (PRODUCT_CODE, "WS10", 1),
        (PRODUCT_CODE, "WS20", 2),
        (PRODUCT_CODE, "WS30", 3),
        (PRODUCT_CODE, "WS40", 4),
        (PRODUCT_CODE, "WS50", 5),
    ]
    conn.executemany(
        """
        INSERT INTO process_route (product_code, station_id, sequence)
        VALUES (?, ?, ?)
        """,
        routes,
    )


def seed_materials(conn) -> None:
    materials = [
        ("M001", "底盘", "pcs"),
        ("M002", "轮子", "pcs"),
        ("M003", "芯片", "pcs"),
        ("M004", "外壳", "pcs"),
        ("M005", "螺丝包", "pcs"),
    ]
    conn.executemany(
        """
        INSERT INTO material (material_code, material_name, unit)
        VALUES (?, ?, ?)
        """,
        materials,
    )


def seed_bom(conn) -> None:
    rows = [
        (PRODUCT_CODE, "M001", 1.0, "WS10"),
        (PRODUCT_CODE, "M002", 4.0, "WS20"),
        (PRODUCT_CODE, "M003", 1.0, "WS20"),
        (PRODUCT_CODE, "M004", 1.0, "WS30"),
        (PRODUCT_CODE, "M005", 1.0, "WS30"),
    ]
    conn.executemany(
        """
        INSERT INTO bom (product_code, material_code, qty_per_unit, consume_station_id)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def seed_inventory(conn) -> None:
    updated = now_str()
    rows = [
        ("M001", 300.0, 50.0, updated),
        ("M002", 1200.0, 300.0, updated),
        ("M003", 280.0, 80.0, updated),
        ("M004", 320.0, 50.0, updated),
        ("M005", 320.0, 80.0, updated),
    ]
    conn.executemany(
        """
        INSERT INTO inventory (material_code, current_qty, safety_qty, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def seed_orders(conn) -> None:
    base_due = datetime.now().date()
    created_at = now_str()
    rows = []
    for idx in range(1, 11):
        # 编号规则与后端主程序保持一致：SO-YYYYMMDD-xxx。
        order_no = f"SO-{datetime.now().strftime('%Y%m%d')}-{idx:03d}"
        quantity = 5 + idx
        due_date = (base_due + timedelta(days=(idx % 5) + 1)).strftime("%Y-%m-%d")
        priority = 1 if idx % 3 == 0 else 2 if idx % 3 == 1 else 3
        rows.append(
            (
                order_no,
                PRODUCT_CODE,
                quantity,
                due_date,
                priority,
                "pending",
                created_at,
            )
        )
    conn.executemany(
        """
        INSERT INTO sales_order (
            order_no, product_code, quantity, due_date, priority, order_status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def run_seed() -> None:
    init_db()
    with get_connection() as conn:
        seed_products(conn)
        seed_stations(conn)
        seed_process_route(conn)
        seed_materials(conn)
        seed_bom(conn)
        seed_inventory(conn)
        seed_orders(conn)
        conn.commit()
    print("Seed complete: SQLite schema and base data initialized.")


if __name__ == "__main__":
    run_seed()
