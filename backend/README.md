# README（A 角色重点版）

这份文档重点回答三件事：

1. 你现在这套后端程序已经做了什么  
2. `backend` 目录下每个文件有什么用  
3. 你（A）如何和 B、C 两位协作者的内容拼接起来

---

## 1. 当前程序已经实现了什么

当前后端已经能跑通完整主链路：

`新建订单 -> 订单转工单 -> 排产 -> 仿真 -> 事件/质检/KPI落库 -> 前端查询`

具体已实现能力：

- 数据层：`SQLite` 12 张核心表（见 `schema.sql`）
- 业务层：
  - 订单新增、查询
  - 工单生成（含物料预检查）
  - 排产任务生成
  - 仿真执行（默认策略）
  - 返修闭环：`WS40 -> WS30 -> WS40`，最多返修 1 次，二次不合格报废
- 结果层：
  - `production_event` 生产事件
  - `quality_record` 质检记录
  - `kpi_snapshot` KPI 快照
  - `GET /schedule/actual-timeline` 可还原实际执行时序（含返修回流）
- 接口层：
  - 统一返回结构：`{code, message, data}`
  - `/docs` 可直接联调
- 协作层：
  - `/simulation/run` 已拆成“接口层 + 可替换策略层”
  - B 可以不改 `main.py`，只替换策略实现

---

## 2. 每个文件到底有什么用

下面按“你为什么需要这个文件”来解释。

| 文件 | 作用 | 你（A）主要操作 | B 主要操作 | C 主要操作 |
| --- | --- | --- | --- | --- |
| `main.py` | 后端入口与所有 API 路由 | 维护接口、状态流转、事务提交、错误处理 | 不直接改路由，按接口参数传值 | 调用这些接口做页面数据展示 |
| `db.py` | 数据库连接与通用查询函数 | 保持连接配置与查询工具稳定 | 通常不改 | 不改 |
| `schema.sql` | 数据库表结构定义（单一真相） | 维护表字段、约束、命名 | 按字段写仿真输出 | 按字段绑定前端 |
| `seed.py` | 一键重建数据库并写入基础数据 | 联调前初始化数据 | 用种子数据跑仿真 | 用种子数据联调页面 |
| `simulation_strategy.py` | 仿真策略接口协议 + 动态加载器 | 固定 A/B 边界（只负责“怎么接”） | 按协议接入策略 | 不改 |
| `simulation_strategy_b_template.py` | B 的策略模板文件 | 提供模板，不写 B 的算法细节 | 复制并实现自己的 `run` 逻辑 | 不改 |
| `__init__.py` | 让 `backend` 可作为包导入 | 保持即可 | 无 | 无 |
| `requirements.txt` | 依赖清单 | 管版本、补依赖 | 安装依赖 | 安装依赖（如本地直连后端） |
| `mes.db` | 本地运行后的数据库文件 | 查看运行结果、排错 | 检查仿真落库结果 | 可选查看数据 |

---

## 3. 你（A）和 B、C 怎么拼起来

### 3.1 对接边界（核心）

你们三人不是“互相改对方代码”，而是通过**稳定边界**协作：

- A 固定：接口、字段、状态枚举、落库位置
- B 提供：仿真策略实现（通过策略层挂载）
- C 消费：稳定 API 与字段渲染页面

### 3.2 A 与 B 的连接方式

A 侧给 B 的稳定输入：

- 接口：`POST /simulation/run`
- 入参：`scenario / order_count / fault_station / fault_duration_min / rush_order_at_min`
- 数据口径：`production_event`、`quality_record`、`kpi_snapshot` 字段命名

B 给 A 的交付物：

- 一个策略类文件（例如 `simulation_strategy_b.py`）
- 至少实现：
  - `strategy_name: str`
  - `run(conn, payload) -> dict`

启动时挂载 B 策略：

```powershell
$env:MES_SIMULATION_STRATEGY = "simulation_strategy_b:BTeamSimulationStrategy"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

不设置该环境变量时，系统走内置默认策略。

### 3.3 A 与 C 的连接方式

A 侧给 C：

- 接口地址：`http://127.0.0.1:8000`
- 文档页：`http://127.0.0.1:8000/docs`
- 稳定接口：
  - `GET /orders`
  - `GET /schedule/tasks`
  - `GET /events`
  - `GET /quality/records`
  - `GET /kpi/latest`
  - `GET /kpi/compare`
  - `GET /stations/status`

C 给 A 的反馈：

- 字段缺失/命名不一致
- 状态值不在协作契约枚举中
- 页面联调时返回结构不符合预期

---

## 4. 推荐联调顺序（按角色）

### 第一步：A 先准备稳定底座

```powershell
cd D:\生产管理MSE\backend
python -m pip install -r requirements.txt
python seed.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 第二步：B 接入策略（可选并行）

- B 在自己的策略文件实现 `run(conn, payload)`
- 设置 `MES_SIMULATION_STRATEGY` 后调用 `/simulation/run`
- 确认事件、质检、KPI 正常落库

### 第三步：C 对接页面

- C 先对接查询接口（`/orders`、`/schedule/tasks`、`/kpi/latest`）
- 再对接监控与质量接口（`/events`、`/quality/records`、`/stations/status`）

---

## 5. 快速验收：你这边是否“可交付”

满足以下 5 条就说明 A 侧可交付：

1. `python seed.py` 成功（可重建数据）
2. `uvicorn main:app --reload` 能启动
3. `/docs` 可访问
4. 主链路接口可跑通：  
   `POST /orders -> POST /orders/{order_no}/generate-work-order -> POST /schedule -> POST /simulation/run -> GET /kpi/latest`
5. 返回结构始终是：

```json
{
  "code": 200,
  "message": "ok",
  "data": {}
}
```

---

## 6. 注意事项（避免协作冲突）

- 字段和状态命名以 `团队协作契约.md` 为准
- `work_order`、`schedule_task`、`production_event` 相关命名不要私自改
- 任何影响 B/C 的接口改动，需要当天同步通知
- A 的职责是“稳定底座”，不要把页面逻辑写进后端，也不要把 B 的算法耦合进接口层
