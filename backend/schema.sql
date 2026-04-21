PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS kpi_snapshot;
DROP TABLE IF EXISTS quality_record;
DROP TABLE IF EXISTS production_event;
DROP TABLE IF EXISTS schedule_task;
DROP TABLE IF EXISTS work_order;
DROP TABLE IF EXISTS sales_order;
DROP TABLE IF EXISTS simulation_run;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS bom;
DROP TABLE IF EXISTS material;
DROP TABLE IF EXISTS process_route;
DROP TABLE IF EXISTS station;
DROP TABLE IF EXISTS product;

CREATE TABLE product (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL
);

CREATE TABLE station (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL UNIQUE,
    station_name TEXT NOT NULL,
    min_time REAL,
    mode_time REAL NOT NULL,
    max_time REAL,
    sigma REAL,
    capacity INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE process_route (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL,
    station_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    UNIQUE(product_code, station_id),
    UNIQUE(product_code, sequence),
    FOREIGN KEY(product_code) REFERENCES product(product_code),
    FOREIGN KEY(station_id) REFERENCES station(station_id)
);

CREATE TABLE material (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_code TEXT NOT NULL UNIQUE,
    material_name TEXT NOT NULL,
    unit TEXT NOT NULL
);

CREATE TABLE bom (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL,
    material_code TEXT NOT NULL,
    qty_per_unit REAL NOT NULL,
    consume_station_id TEXT NOT NULL,
    UNIQUE(product_code, material_code, consume_station_id),
    FOREIGN KEY(product_code) REFERENCES product(product_code),
    FOREIGN KEY(material_code) REFERENCES material(material_code),
    FOREIGN KEY(consume_station_id) REFERENCES station(station_id)
);

CREATE TABLE inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_code TEXT NOT NULL UNIQUE,
    current_qty REAL NOT NULL,
    safety_qty REAL NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(material_code) REFERENCES material(material_code)
);

CREATE TABLE sales_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL UNIQUE,
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    priority INTEGER NOT NULL,
    order_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(product_code) REFERENCES product(product_code)
);

CREATE TABLE simulation_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    scenario TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    status TEXT NOT NULL,
    request_payload TEXT,
    result_summary TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE work_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no TEXT NOT NULL UNIQUE,
    order_no TEXT NOT NULL UNIQUE,
    product_code TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    work_order_status TEXT NOT NULL,
    scheduled_start TEXT,
    scheduled_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_no) REFERENCES sales_order(order_no),
    FOREIGN KEY(product_code) REFERENCES product(product_code)
);

CREATE TABLE schedule_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_no TEXT NOT NULL,
    station_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    planned_start TEXT,
    planned_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    status TEXT NOT NULL,
    UNIQUE(work_order_no, station_id),
    FOREIGN KEY(work_order_no) REFERENCES work_order(work_order_no),
    FOREIGN KEY(station_id) REFERENCES station(station_id)
);

CREATE TABLE production_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    work_order_no TEXT NOT NULL,
    station_id TEXT,
    event_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    remark TEXT,
    FOREIGN KEY(run_id) REFERENCES simulation_run(run_id),
    FOREIGN KEY(work_order_no) REFERENCES work_order(work_order_no)
);

CREATE TABLE quality_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    work_order_no TEXT NOT NULL,
    inspect_time TEXT NOT NULL,
    quality_result TEXT NOT NULL,
    repair_count INTEGER NOT NULL DEFAULT 0,
    remark TEXT,
    FOREIGN KEY(run_id) REFERENCES simulation_run(run_id),
    FOREIGN KEY(work_order_no) REFERENCES work_order(work_order_no)
);

CREATE TABLE kpi_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    snapshot_time TEXT NOT NULL,
    scenario TEXT NOT NULL,
    total_completed INTEGER NOT NULL,
    on_time_rate REAL NOT NULL,
    avg_lead_time REAL NOT NULL,
    wip_count INTEGER NOT NULL,
    defect_rate REAL NOT NULL,
    repair_rate REAL NOT NULL,
    line_balance_rate REAL NOT NULL,
    bottleneck_station TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES simulation_run(run_id)
);

CREATE INDEX IF NOT EXISTS idx_task_status
ON schedule_task(work_order_no, status);

CREATE INDEX IF NOT EXISTS idx_event_timeline
ON production_event(event_time, event_type);

CREATE INDEX IF NOT EXISTS idx_wo_order_no
ON work_order(order_no);

CREATE INDEX IF NOT EXISTS idx_event_run_id
ON production_event(run_id, event_time);

CREATE INDEX IF NOT EXISTS idx_quality_run_id
ON quality_record(run_id, inspect_time);

CREATE INDEX IF NOT EXISTS idx_kpi_run_id
ON kpi_snapshot(run_id, scenario);
