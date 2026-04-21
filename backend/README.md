# 生产管理后端说明

本文档只描述当前 `backend/` 的目录结构、启动方式、A/B/C 分工入口和联调流程。

---

## 1. 后端定位

当前后端的定位是一个：

- 可启动
- 可初始化
- 可联调
- 可冒烟测试
- 便于 A 维护、B 接入策略、C 对接页面

的轻量后端。

三类使用者的关注点：

- A：维护业务流程、数据库结构、接口实现
- B：实现或替换仿真策略
- C：调用稳定 API 完成前端页面联调

---

## 2. 当前目录结构

```text
backend/
├─ main.py
├─ common.py
├─ db.py
├─ schema.sql
├─ seed.py
├─ smoke_test.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ __init__.py
├─ api/
│  ├─ __init__.py
│  ├─ order_api.py
│  ├─ schedule_api.py
│  ├─ simulation_api.py
│  └─ query_api.py
├─ domain/
│  ├─ __init__.py
│  ├─ orders.py
│  ├─ schedule.py
│  ├─ simulation.py
│  └─ kpi.py
├─ contracts/
│  ├─ __init__.py
│  ├─ request_models.py
│  └─ simulation_result.py
├─ integration/
│  ├─ __init__.py
│  ├─ security.py
│  └─ strategy_loader.py
└─ b_strategy/
   ├─ __init__.py
   └─ strategy_template.py
```

当前结构按“读者角色 + 业务阶段”组织：

- `api/`：给 C 看，直接对应接口
- `domain/`：给 A 看，直接对应业务流程
- `contracts/`：给 A/B/C 看，直接对应共享数据契约
- `integration/`：给 A/B 看，放安全和策略加载
- `b_strategy/`：给 B 看，放策略模板与后续策略实现

---

## 3. 每个文件和目录的作用

### 3.1 根级文件

| 文件 | 作用 | 主要使用者 |
| --- | --- | --- |
| `main.py` | FastAPI 启动入口，注册异常处理、CORS、API Key 中间件，并挂载所有接口路由 | A |
| `common.py` | 放全局常量、状态枚举、事件类型、时间格式、统一响应函数 `ok()` | A/B/C |
| `db.py` | 提供 SQLite 连接、事务封装、通用查询函数、数据库初始化函数 | A |
| `schema.sql` | 数据库结构定义，是表结构的单一来源 | A |
| `seed.py` | 开发/演示初始化脚本，用于重建数据库并写入基础数据 | A/B/C |
| `smoke_test.py` | 一键全链路冒烟测试脚本，用于验证后端是否能跑通主链路 | A |
| `requirements.txt` | Python 依赖清单 | A |
| `README.md` | 当前说明文档 | A/B/C |
| `.gitignore` | 忽略数据库文件、缓存文件等运行产物 | A |
| `__init__.py` | 让 `backend` 可以作为 Python 包导入 | A |

### 3.2 `api/`

`api/` 只负责 HTTP 接口，不放复杂业务逻辑。

| 文件 | 作用 |
| --- | --- |
| `api/order_api.py` | 提供订单查询、新建订单、订单转工单接口 |
| `api/schedule_api.py` | 提供排产生成、排产任务查询、实际时间线查询接口 |
| `api/simulation_api.py` | 提供仿真触发接口 |
| `api/query_api.py` | 提供服务检测、事件、质检、KPI、工位状态查询接口 |
| `api/__init__.py` | 标记 `api` 为 Python 包 |

### 3.3 `domain/`

`domain/` 放核心业务流程，是 A 主要维护的目录。

| 文件 | 作用 |
| --- | --- |
| `domain/orders.py` | 订单列表、新建订单、订单转工单、物料预检查、单号生成 |
| `domain/schedule.py` | 读取工位参数、生成排产任务、查询排产任务、还原实际执行时间线 |
| `domain/simulation.py` | 创建仿真批次、加载策略、执行仿真、写入事件/质检、维护工位状态 |
| `domain/kpi.py` | 计算 KPI、写入 KPI 快照、查询最新 KPI 和场景对比 |
| `domain/__init__.py` | 标记 `domain` 为 Python 包 |

### 3.4 `contracts/`

`contracts/` 放共享的数据契约，是 A/B/C 共同遵守的结构定义。

| 文件 | 作用 |
| --- | --- |
| `contracts/request_models.py` | 定义接口请求模型：`OrderCreate`、`ScheduleRequest`、`SimulationRequest` |
| `contracts/simulation_result.py` | 定义 `SimulationResult`，用于校验 B 策略返回值 |
| `contracts/__init__.py` | 统一导出契约模型 |

### 3.5 `integration/`

`integration/` 放横切能力和外部接入点，不直接承担业务流程。

| 文件 | 作用 |
| --- | --- |
| `integration/security.py` | 处理 API Key 鉴权、CORS 来源配置、调试错误开关 |
| `integration/strategy_loader.py` | 定义 `SimulationStrategy` 协议，并根据环境变量加载 B 的策略类 |
| `integration/__init__.py` | 统一导出安全和策略加载能力 |

### 3.6 `b_strategy/`

`b_strategy/` 是给 B 使用的目录，用于放策略模板和后续真实策略实现。

| 文件 | 作用 |
| --- | --- |
| `b_strategy/strategy_template.py` | 提供 B 的策略模板 |
| `b_strategy/__init__.py` | 导出模板类 |

---

## 4. 启动方式

推荐在 `backend/` 目录内运行：

```powershell
cd D:\生产管理MSE\backend
python -m pip install -r requirements.txt
python seed.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

也可以在项目根目录运行：

```powershell
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/docs`

---

## 5. 安全与运行配置

通过环境变量控制：

| 环境变量 | 作用 | 默认行为 |
| --- | --- | --- |
| `MES_API_KEY` | 设置后启用 API Key 鉴权 | 不设置则不开启鉴权 |
| `MES_CORS_ORIGINS` | 允许跨域的前端地址，多个地址用逗号分隔 | 默认放行本地常见前端开发地址 |
| `MES_DEBUG_ERRORS` | 是否向前端返回详细异常文本 | 默认关闭 |
| `MES_SIMULATION_STRATEGY` | 指定 B 的策略类路径 | 默认使用内置策略 |

如果设置了 `MES_API_KEY`，请求头需要带：

```http
X-API-Key: your-api-key
```

---

## 6. B 侧策略接入方式

B 只需要重点看三个位置：

- `b_strategy/strategy_template.py`
- `integration/strategy_loader.py`
- `contracts/request_models.py`

推荐步骤：

1. 复制 `backend/b_strategy/strategy_template.py`
2. 新建自己的策略文件，例如：`backend/b_strategy/strategy_b.py`
3. 实现 `BTeamSimulationStrategy.run(conn, payload)`
4. 设置环境变量 `MES_SIMULATION_STRATEGY`
5. 调用 `POST /simulation/run` 验证策略是否生效

在 `backend/` 目录内启动时示例：

```powershell
$env:MES_SIMULATION_STRATEGY = "b_strategy.strategy_b:BTeamSimulationStrategy"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

在项目根目录按包启动时示例：

```powershell
$env:MES_SIMULATION_STRATEGY = "backend.b_strategy.strategy_b:BTeamSimulationStrategy"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

策略返回值必须满足 `contracts/simulation_result.py` 中的结构要求。

---

## 7. C 侧接口入口

C 主要看：

- `/docs`
- `api/`
- 本 README

当前核心接口：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/` | 服务检测 |
| `GET` | `/orders` | 查询订单与工单状态 |
| `POST` | `/orders` | 新建订单 |
| `POST` | `/orders/{order_no}/generate-work-order` | 订单转工单 |
| `POST` | `/schedule` | 生成排产任务 |
| `GET` | `/schedule/tasks` | 查询排产任务 |
| `GET` | `/schedule/actual-timeline` | 查询实际执行时间线 |
| `POST` | `/simulation/run` | 触发仿真，返回 `run_id` |
| `GET` | `/events` | 查询事件，可选 `run_id` |
| `GET` | `/quality/records` | 查询质检记录，可选 `run_id` |
| `GET` | `/kpi/latest` | 查询最新 KPI，可选 `run_id` |
| `GET` | `/kpi/compare` | 查询各场景 KPI 对比 |
| `GET` | `/stations/status` | 查询工位状态 |

统一响应结构：

```json
{
  "code": 200,
  "message": "ok",
  "data": {}
}
```

---

## 8. 数据库说明

数据库结构由 `schema.sql` 统一维护。当前核心表包括：

- `product`
- `station`
- `process_route`
- `material`
- `bom`
- `inventory`
- `sales_order`
- `simulation_run`
- `work_order`
- `schedule_task`
- `production_event`
- `quality_record`
- `kpi_snapshot`

开发和演示时，通过 `seed.py` 生成基础数据。

---

## 9. 一键冒烟测试

在项目根目录运行：

```powershell
python .\backend\smoke_test.py
```

或进入 `backend/` 目录运行：

```powershell
python smoke_test.py
```

该脚本会自动完成：

1. 执行 `seed.py`
2. 启动本地服务
3. 走完整个主链路
4. 打印 `order_no`、`work_order_no`、`run_id`
5. 自动关闭服务

如果设置了 `MES_API_KEY`，脚本会自动读取并带上 `X-API-Key`。

---

## 10. 修改定位指南

| 你想改什么 | 去哪里改 |
| --- | --- |
| 新增或修改接口 | `api/` |
| 修改订单逻辑 | `domain/orders.py` |
| 修改排产逻辑 | `domain/schedule.py` |
| 修改仿真逻辑 | `domain/simulation.py` |
| 修改 KPI 逻辑 | `domain/kpi.py` |
| 修改请求模型 | `contracts/request_models.py` |
| 修改策略返回值约束 | `contracts/simulation_result.py` |
| 修改 API Key / CORS / 调试错误配置 | `integration/security.py` |
| 修改 B 策略加载逻辑 | `integration/strategy_loader.py` |
| 修改 B 策略模板 | `b_strategy/strategy_template.py` |
| 修改数据库结构 | `schema.sql` |
| 修改初始化数据 | `seed.py` |
| 修改启动入口 | `main.py` |

原则：

- `api/` 保持薄
- `domain/` 放业务
- `contracts/` 放共享数据契约
- `integration/` 放安全和外部接入
- `b_strategy/` 放 B 的策略
- 数据库结构以 `schema.sql` 为准
