# 生产管理后端目录说明

本文档只说明 `backend/` 目录。根目录中的方案文档、比赛资料、计划表等不属于后端运行必需内容。

当前后端的定位是：为智能小车虚拟装配线生产管控系统提供一个**可启动、可初始化、可联调、便于 B/C 接入**的最小后端。

- A：维护后端接口、数据库、业务流程和数据落库。
- B：在固定接口内接入或替换仿真策略。
- C：通过稳定 API 对接前端页面。

---

## 1. 快速启动

推荐在 `backend/` 目录内运行：

```powershell
cd D:\生产管理MSE\backend
python -m pip install -r requirements.txt
python seed.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

- 接口文档：`http://127.0.0.1:8000/docs`
- 服务检测：`http://127.0.0.1:8000/`

也可以在项目根目录按包启动：

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 2. 总体目录结构

```text
backend/
├─ main.py
├─ db.py
├─ common.py
├─ schema.sql
├─ seed.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ __init__.py
├─ simulation_strategy.py
├─ simulation_strategy_b_template.py
├─ api/
│  ├─ __init__.py
│  ├─ orders.py
│  ├─ schedule.py
│  ├─ simulation.py
│  └─ query.py
├─ models/
│  ├─ __init__.py
│  └─ schemas.py
├─ services/
│  ├─ __init__.py
│  ├─ order_service.py
│  ├─ schedule_service.py
│  ├─ simulation_service.py
│  └─ kpi_service.py
└─ simulation/
   ├─ __init__.py
   ├─ strategy.py
   └─ strategy_b_template.py
```

分层原则：

- `main.py`：应用入口，只负责组装。
- `api/`：接口层，C 主要看这里和 `/docs`。
- `models/`：请求模型层，统一定义接口入参。
- `services/`：业务逻辑层，A 主要维护这里。
- `simulation/`：仿真策略边界，B 主要看这里。
- `db.py`、`schema.sql`、`seed.py`：数据库相关文件。

---

## 3. 根级文件说明

| 文件 | 作用 | 主要维护人 | B/C 是否需要看 |
| --- | --- | --- | --- |
| `main.py` | FastAPI 应用入口，创建 `app`、注册异常处理、挂载各个 `api` 路由模块 | A | 通常不需要；确认服务入口时可看 |
| `db.py` | SQLite 数据库连接、事务封装、通用查询函数、执行 `schema.sql` 初始化 | A | B 写策略时可能需要知道 `conn` 是 SQLite 连接 |
| `common.py` | 全局常量和通用函数，例如状态枚举、事件类型、场景编码、时间格式、`ok()` 响应包装 | A | B/C 可查看状态值和事件值 |
| `schema.sql` | 数据库表结构定义，包含产品、工位、BOM、库存、订单、工单、排产、事件、质检、KPI 等表 | A | B/C 需要字段口径时可看 |
| `seed.py` | 一键重建数据库并写入基础测试数据，用于联调前初始化 | A | B/C 本地联调时会运行 |
| `requirements.txt` | Python 依赖清单，目前包含 `fastapi`、`uvicorn`、`pydantic` | A | B/C 本地运行后端时会用 |
| `README.md` | 当前说明文档，解释后端结构、启动方式、接口、B/C 接入方式 | A | B/C 都需要看 |
| `.gitignore` | 忽略后端运行产物，例如 `__pycache__/`、`*.pyc`、`mes.db` | A | 不需要 |
| `__init__.py` | 让 `backend` 可以作为 Python 包导入，支持 `uvicorn backend.main:app` | A | 不需要 |
| `simulation_strategy.py` | 旧版兼容入口，重新导出 `simulation/strategy.py` 中的 `SimulationStrategy` 和 `load_strategy` | A | B 如果沿用旧导入方式可看 |
| `simulation_strategy_b_template.py` | 旧版兼容模板入口，重新导出 `simulation/strategy_b_template.py` 中的模板类 | A/B | B 如果沿用旧模板路径可看 |

注意：

- `mes.db` 不作为代码文件维护，它是 `python seed.py` 或服务运行后生成的 SQLite 数据库文件。
- `__pycache__/` 和 `*.pyc` 是 Python 缓存文件，不应作为业务代码维护。

---

## 4. `api/` 接口层说明

`api/` 目录只负责接收 HTTP 请求、调用 `services/`、返回统一结构。这里尽量不写复杂业务逻辑。

| 文件 | 负责接口 | 用途 | 主要接入方 |
| --- | --- | --- | --- |
| `api/__init__.py` | 无具体接口 | 标记 `api` 为 Python 包 | A |
| `api/orders.py` | `GET /orders`、`POST /orders`、`POST /orders/{order_no}/generate-work-order` | 订单查询、新建订单、订单转工单 | C |
| `api/schedule.py` | `POST /schedule`、`GET /schedule/tasks`、`GET /schedule/actual-timeline` | 触发排产、查询计划任务、查询实际执行时间线 | C |
| `api/simulation.py` | `POST /simulation/run` | 触发仿真，并写入事件、质检、KPI | B/C |
| `api/query.py` | `GET /`、`GET /events`、`GET /quality/records`、`GET /kpi/latest`、`GET /kpi/compare`、`GET /stations/status` | 查询服务状态、事件、质检、KPI、工位状态 | C |

接口层的维护原则：

- 改接口路径前必须同步 C；
- 改请求字段前必须同步 B/C；
- 接口层只做参数接收和结果返回，业务逻辑放到 `services/`。

---

## 5. `models/` 请求模型层说明

`models/` 目录集中放接口入参模型，方便 B/C 确认请求字段。

| 文件 | 作用 | 说明 |
| --- | --- | --- |
| `models/__init__.py` | 标记 `models` 为 Python 包 | 无业务逻辑 |
| `models/schemas.py` | 定义请求模型 | 当前包含 `OrderCreate`、`ScheduleRequest`、`SimulationRequest` |

当前模型含义：

- `OrderCreate`：新建订单入参，包含 `product_code`、`quantity`、`due_date`、`priority`。
- `ScheduleRequest`：排产入参，包含 `force_reschedule`。
- `SimulationRequest`：仿真入参，包含 `scenario`、`order_count`、`fault_station`、`fault_duration_min`、`rush_order_at_min`。

B 重点关注：

- `SimulationRequest`，因为它决定 `/simulation/run` 能接收哪些仿真参数。

C 重点关注：

- `OrderCreate`，因为订单页面需要按这个结构提交数据。
- `ScheduleRequest` 和 `SimulationRequest`，因为页面如果触发排产或仿真，需要按这些字段传参。

---

## 6. `services/` 业务逻辑层说明

`services/` 是后端核心业务层。`api/` 调用这里的函数，数据库读写和业务规则主要放在这里。

| 文件 | 作用 | 主要内容 |
| --- | --- | --- |
| `services/__init__.py` | 标记 `services` 为 Python 包 | 无业务逻辑 |
| `services/order_service.py` | 订单与工单业务 | 订单列表、新建订单、生成工单、BOM 物料预检查、编号生成 |
| `services/schedule_service.py` | 排产业务 | 获取工位参数、生成排产任务、查询排产任务、还原实际执行时间线 |
| `services/simulation_service.py` | 仿真承接与生产执行业务 | 内置仿真策略、工位执行、事件落库、质检记录、工位状态查询、调用 B 策略入口 |
| `services/kpi_service.py` | KPI 统计业务 | 计算并写入 KPI 快照、查询最新 KPI、查询不同场景 KPI 对比 |

各文件具体说明：

### 6.1 `services/order_service.py`

负责订单到工单的前半段流程：

1. 查询订单列表；
2. 新建销售订单；
3. 生成销售订单编号；
4. 做 BOM 物料预检查；
5. 将订单转换为工单；
6. 更新订单状态。

对应接口：

- `GET /orders`
- `POST /orders`
- `POST /orders/{order_no}/generate-work-order`

### 6.2 `services/schedule_service.py`

负责工单到排产任务的流程：

1. 读取待排产工单；
2. 按优先级、交期、创建时间排序；
3. 根据工艺路线生成 `schedule_task`；
4. 写入计划开始时间和计划结束时间；
5. 查询排产任务；
6. 根据生产事件还原实际执行时间线。

对应接口：

- `POST /schedule`
- `GET /schedule/tasks`
- `GET /schedule/actual-timeline`

### 6.3 `services/simulation_service.py`

负责仿真承接，是当前最大、最重要的业务文件：

1. 提供内置默认仿真策略 `BuiltinSimulationStrategy`；
2. 加载 B 侧自定义策略；
3. 执行工位加工逻辑；
4. 写入 `production_event`；
5. 写入 `quality_record`；
6. 更新工单和订单状态；
7. 查询事件列表；
8. 查询质检记录；
9. 计算工位状态。

对应接口：

- `POST /simulation/run`
- `GET /events`
- `GET /quality/records`
- `GET /stations/status`

B 如果不接入自己的策略，系统会使用这里的内置策略。

### 6.4 `services/kpi_service.py`

负责 KPI 统计和查询：

1. 统计完工量；
2. 统计准时率；
3. 统计平均生产周期；
4. 统计在制品数量；
5. 统计不良率和返修率；
6. 计算生产线平衡率；
7. 识别瓶颈工位；
8. 写入 `kpi_snapshot`；
9. 查询最新 KPI 和场景对比 KPI。

对应接口：

- `GET /kpi/latest`
- `GET /kpi/compare`

---

## 7. `simulation/` B 侧策略接入层说明

`simulation/` 是专门留给 B 对接仿真策略的边界目录。B 不需要改 `api/` 和 `services/` 的路由代码，只需要按协议提供策略类。

| 文件 | 作用 | B 是否需要看 |
| --- | --- | --- |
| `simulation/__init__.py` | 重新导出 `SimulationStrategy` 和 `load_strategy` | 可选 |
| `simulation/strategy.py` | 定义 `SimulationStrategy` 协议，并根据 `MES_SIMULATION_STRATEGY` 动态加载策略 | 必看 |
| `simulation/strategy_b_template.py` | B 侧策略模板，说明策略类的最小写法和返回字段 | 必看 |

B 的策略类必须满足：

```python
class BTeamSimulationStrategy:
    strategy_name = "b_team"

    def run(self, conn, payload):
        return {
            "scenario": payload.scenario,
            "processed_work_orders": 0,
            "processed_tasks": 0,
            "events_created": 0,
            "quality_records_created": 0,
        }
```

推荐接入步骤：

1. 复制 `backend/simulation/strategy_b_template.py`；
2. 新建 `backend/simulation/strategy_b.py`；
3. 实现 `BTeamSimulationStrategy.run(conn, payload)`；
4. 在启动后端前设置环境变量；
5. 调用 `POST /simulation/run` 验证策略是否生效。

在 `backend/` 目录内启动时：

```powershell
$env:MES_SIMULATION_STRATEGY = "simulation.strategy_b:BTeamSimulationStrategy"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

在项目根目录按包启动时：

```powershell
$env:MES_SIMULATION_STRATEGY = "backend.simulation.strategy_b:BTeamSimulationStrategy"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

如果不设置 `MES_SIMULATION_STRATEGY`，系统默认使用 `services/simulation_service.py` 中的内置策略。

---

## 8. 数据库文件说明

### 8.1 `schema.sql`

`schema.sql` 是数据库结构的单一来源。当前包含以下核心表：

| 表名 | 作用 |
| --- | --- |
| `product` | 产品主数据，例如智能小车 `CAR-001` |
| `station` | 工位主数据，例如 `WS10` 到 `WS50` |
| `process_route` | 产品工艺路线，定义产品依次经过哪些工位 |
| `material` | 物料主数据 |
| `bom` | 产品 BOM，定义每台产品消耗哪些物料 |
| `inventory` | 库存数据 |
| `sales_order` | 销售订单 |
| `work_order` | 生产工单 |
| `schedule_task` | 排产任务 |
| `production_event` | 生产事件 |
| `quality_record` | 质检记录 |
| `kpi_snapshot` | KPI 快照 |

### 8.2 `seed.py`

`seed.py` 用于重建数据库并写入基础数据：

- 产品：`CAR-001`
- 工位：`WS10`、`WS20`、`WS30`、`WS40`、`WS50`
- 工艺路线：`WS10 -> WS20 -> WS30 -> WS40 -> WS50`
- 物料、BOM、库存
- 示例销售订单

运行方式：

```powershell
cd D:\生产管理MSE\backend
python seed.py
```

运行后会生成 `backend/mes.db`。该文件是运行产物，可以删除后重新生成。

---

## 9. C 侧前端接口清单

C 优先访问 `/docs` 查看接口字段，也可以按下表直接联调：

| 方法 | 路径 | 所在文件 | 作用 |
| --- | --- | --- | --- |
| `GET` | `/` | `api/query.py` | 服务检测 |
| `GET` | `/orders` | `api/orders.py` | 查询订单与工单状态 |
| `POST` | `/orders` | `api/orders.py` | 新建订单 |
| `POST` | `/orders/{order_no}/generate-work-order` | `api/orders.py` | 订单转工单 |
| `POST` | `/schedule` | `api/schedule.py` | 生成排产任务 |
| `GET` | `/schedule/tasks` | `api/schedule.py` | 查询排产任务 |
| `GET` | `/schedule/actual-timeline` | `api/schedule.py` | 查询实际执行时间线 |
| `POST` | `/simulation/run` | `api/simulation.py` | 触发仿真 |
| `GET` | `/events` | `api/query.py` | 查询生产事件 |
| `GET` | `/quality/records` | `api/query.py` | 查询质检记录 |
| `GET` | `/kpi/latest` | `api/query.py` | 查询最新 KPI |
| `GET` | `/kpi/compare` | `api/query.py` | 查询各场景最新 KPI |
| `GET` | `/stations/status` | `api/query.py` | 查询工位状态 |

统一返回结构：

```json
{
  "code": 200,
  "message": "ok",
  "data": {}
}
```

错误返回结构：

```json
{
  "code": 400,
  "message": "错误说明",
  "data": null
}
```

---

## 10. 最小联调流程

初始化数据库后，推荐按下面顺序验证主链路：

1. `GET /`
2. `GET /orders`
3. `POST /orders`
4. `POST /orders/{order_no}/generate-work-order`
5. `POST /schedule`
6. `GET /schedule/tasks`
7. `POST /simulation/run`
8. `GET /events`
9. `GET /quality/records`
10. `GET /kpi/latest`
11. `GET /stations/status`

这条链路跑通，就说明后端、B 侧策略接口、C 侧查询接口的基础连接是正常的。

---

## 11. A/B/C 分工建议

### 11.1 A 维护后端

A 主要维护：

- `api/`
- `services/`
- `models/schemas.py`
- `db.py`
- `schema.sql`
- `seed.py`

改动规则：

- 改接口路径时通知 C；
- 改请求字段时通知 B/C；
- 改数据库字段时同步更新 `schema.sql` 和相关服务逻辑；
- 改 KPI 口径时通知 C。

### 11.2 B 接入仿真

B 主要看：

- `simulation/strategy.py`
- `simulation/strategy_b_template.py`
- `models/schemas.py` 中的 `SimulationRequest`
- `POST /simulation/run`

B 尽量不要直接改：

- `api/`
- `main.py`
- `db.py`

除非 A/B 已经同步确认接口边界需要调整。

### 11.3 C 对接前端

C 主要看：

- `README.md`
- `/docs`
- `api/` 中的接口路径

C 不需要关心：

- `services/` 的内部实现；
- B 的仿真算法细节；
- SQLite 的底层查询细节。

---

## 12. 修改文件时的定位指南

| 你想做的事 | 应该改哪里 |
| --- | --- |
| 新增接口 | `api/`，必要时新增对应 `services/` 函数 |
| 修改接口入参 | `models/schemas.py` |
| 修改订单逻辑 | `services/order_service.py` |
| 修改排产逻辑 | `services/schedule_service.py` |
| 修改仿真执行逻辑 | `services/simulation_service.py` 或 B 自己的策略文件 |
| 修改 KPI 计算 | `services/kpi_service.py` |
| 修改数据库结构 | `schema.sql`，并同步调整 `seed.py` 和服务代码 |
| 修改基础数据 | `seed.py` |
| 修改 B 策略协议 | `simulation/strategy.py` |
| 修改启动入口 | `main.py` |

原则：

- 接口层保持薄；
- 业务逻辑放到 `services/`；
- 请求模型集中在 `models/`；
- B 的算法放到 `simulation/`；
- 数据库结构以 `schema.sql` 为准。
