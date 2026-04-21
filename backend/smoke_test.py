from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("MES_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        content = response.read().decode("utf-8")
        return json.loads(content)


def wait_for_server(base_url: str, headers: dict[str, str], timeout_seconds: int = 20) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            payload = request_json("GET", f"{base_url}/", headers=headers)
            if payload.get("code") == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)

    if last_error is not None:
        raise RuntimeError(f"等待服务启动超时，最后一次错误：{last_error}") from last_error
    raise RuntimeError("等待服务启动超时")


def assert_ok(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("code") != 200:
        raise RuntimeError(f"{name} 失败：{json.dumps(payload, ensure_ascii=False)}")
    data = payload.get("data")
    print(f"[OK] {name}")
    return data


def start_server(port: int) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        HOST,
        "--port",
        str(port),
        "--log-level",
        "warning",
        "--no-access-log",
    ]
    return subprocess.Popen(
        command,
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def read_process_output(process: subprocess.Popen[str]) -> str:
    try:
        output, _ = process.communicate(timeout=2)
        return output or ""
    except subprocess.TimeoutExpired:
        return ""


def run_seed() -> None:
    print("[RUN] 初始化数据库：python seed.py")
    subprocess.run([sys.executable, "seed.py"], cwd=BASE_DIR, check=True)


def run_smoke_test() -> None:
    headers = build_headers()
    run_seed()

    port = pick_free_port()
    base_url = f"http://{HOST}:{port}"
    print(f"[RUN] 启动服务：{base_url}")
    process = start_server(port)

    try:
        if process.poll() is not None:
            raise RuntimeError(f"服务启动立即退出：\n{read_process_output(process)}")

        wait_for_server(base_url, headers)

        home = assert_ok("GET /", request_json("GET", f"{base_url}/", headers=headers))
        print(f"      服务：{home}")

        orders = assert_ok(
            "GET /orders",
            request_json("GET", f"{base_url}/orders", headers=headers),
        )
        print(f"      初始订单数：{len(orders)}")

        order_payload = {
            "product_code": "CAR-001",
            "quantity": 2,
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
            "priority": 1,
        }
        created_order = assert_ok(
            "POST /orders",
            request_json(
                "POST",
                f"{base_url}/orders",
                headers=headers,
                payload=order_payload,
            ),
        )
        order_no = created_order["order_no"]
        print(f"      新订单：{order_no}")

        work_order_result = assert_ok(
            "POST /orders/{order_no}/generate-work-order",
            request_json(
                "POST",
                f"{base_url}/orders/{order_no}/generate-work-order",
                headers=headers,
                payload={},
            ),
        )
        work_order_no = work_order_result["work_order"]["work_order_no"]
        print(f"      工单：{work_order_no}")

        schedule_result = assert_ok(
            "POST /schedule",
            request_json(
                "POST",
                f"{base_url}/schedule",
                headers=headers,
                payload={"force_reschedule": False},
            ),
        )
        print(
            "      排产："
            f"scheduled_work_orders={schedule_result['scheduled_work_orders']}, "
            f"created_tasks={schedule_result['created_tasks']}"
        )

        schedule_tasks = assert_ok(
            "GET /schedule/tasks",
            request_json("GET", f"{base_url}/schedule/tasks", headers=headers),
        )
        print(f"      排产任务数：{len(schedule_tasks)}")

        simulation_result = assert_ok(
            "POST /simulation/run",
            request_json(
                "POST",
                f"{base_url}/simulation/run",
                headers=headers,
                payload={"scenario": "S1_normal", "order_count": 1},
            ),
        )
        run_id = simulation_result["run_id"]
        print(
            "      仿真："
            f"run_id={run_id}, strategy={simulation_result['strategy_name']}, "
            f"processed_tasks={simulation_result['processed_tasks']}"
        )

        actual_timeline = assert_ok(
            "GET /schedule/actual-timeline",
            request_json(
                "GET",
                f"{base_url}/schedule/actual-timeline",
                headers=headers,
            ),
        )
        print(f"      实际时间线条目：{len(actual_timeline)}")

        events = assert_ok(
            "GET /events?run_id=...",
            request_json("GET", f"{base_url}/events?run_id={run_id}", headers=headers),
        )
        print(f"      事件数：{len(events)}")

        quality_records = assert_ok(
            "GET /quality/records?run_id=...",
            request_json(
                "GET",
                f"{base_url}/quality/records?run_id={run_id}",
                headers=headers,
            ),
        )
        print(f"      质检记录数：{len(quality_records)}")

        latest_kpi = assert_ok(
            "GET /kpi/latest?run_id=...",
            request_json(
                "GET",
                f"{base_url}/kpi/latest?run_id={run_id}",
                headers=headers,
            ),
        )
        print(
            "      KPI："
            f"scenario={latest_kpi['scenario']}, "
            f"total_completed={latest_kpi['total_completed']}, "
            f"run_id={latest_kpi.get('run_id')}"
        )

        kpi_compare = assert_ok(
            "GET /kpi/compare",
            request_json("GET", f"{base_url}/kpi/compare", headers=headers),
        )
        print(f"      KPI 对比条目：{len(kpi_compare)}")

        station_status = assert_ok(
            "GET /stations/status",
            request_json("GET", f"{base_url}/stations/status", headers=headers),
        )
        print(f"      工位状态数：{len(station_status)}")

        print()
        print("[PASS] 全链路冒烟测试通过")
        print(f"       order_no={order_no}")
        print(f"       work_order_no={work_order_no}")
        print(f"       run_id={run_id}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        run_smoke_test()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[FAIL] HTTP 错误：status={exc.code}, body={body}")
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        raise SystemExit(1) from exc
