# 后端开发计划

更新时间：`2026-04-17`

本文档用于指导 A 角色的后端开发，目标是在最短时间内完成一个可联调、可演示、可扩展的后端主链路。计划遵循“先跑通主流程，再补细节；先稳定数据结构，再接复杂逻辑”的原则。

## 1. 当前目标

当前后端的最小可交付闭环为：

```text
初始化基础数据
-> 新增订单
-> 生成工单
-> 保存排产任务
-> 触发仿真
-> 写入事件 / 质检 / KPI
-> 前端查询展示
```

在此闭环稳定之前，不新增采购、供应商、库位、批次追溯、权限系统等非主线功能。

## 2. 已确定的固定口径

### 2.1 技术栈

- 后端框架：`FastAPI`
- 数据库：`SQLite`
- 仿真：由 B 使用 `SimPy` 提供逻辑，A 负责接口承接与数据落库
- 前后端交互格式：统一返回 `code`、`message`、`data`

### 2.2 产品与工位

- 产品编号统一使用：`CAR-001`
- 工艺路线固定：`WS10 -> WS20 -> WS30 -> WS40 -> WS50`
- 返修路线固定：`WS40 -> WS30 -> WS40`
- `WS20` 为瓶颈工位

### 2.3 工位随机分布参数

| 工位 | 分布 |
| --- | --- |
| `WS10` | 三角形分布：`min=8s, mode=10s, max=14s` |
| `WS20` | 三角形分布：`min=25s, mode=30s, max=45s` |
| `WS30` | 正态分布：`mu=15s, sigma=0.5s` |
| `WS40` | 正态分布：`mu=12s, sigma=0.2s` |
| `WS50` | 三角形分布：`min=9s, mode=10s, max=13s` |

后端数据库字段固定为：

- `min_time`
- `mode_time`
- `max_time`
- `sigma`

说明：

- 三角形分布使用 `min_time` / `mode_time` / `max_time`
- 正态分布使用 `mode_time(=mu)` / `sigma`
- 参数存储单位为“秒”
- 仿真内部可换算成“分钟”运行

### 2.4 工位状态

工位状态固定为：

- `idle`
- `busy`
- `waiting`
- `waiting_material`
- `blocked`
- `fault`

不再使用 `Running`、`WaitingMaterial`、`Blocked`、`Fault` 这类混合大小写写法。

## 3. 后端职责边界

A 负责：

- 建立 `SQLite` 表结构
- 维护基础主数据
- 提供 `FastAPI` 接口
- 保存订单、工单、排产、事件、质检、KPI 数据
- 定义和稳定接口返回字段
- 提供测试数据
- 联调前端和仿真逻辑

A 不负责：

- 设计复杂排产算法
- 编写 `SimPy` 主仿真逻辑
- 重做前端样式和页面设计

## 4. 开发总顺序

按以下顺序推进：

1. 搭后端项目骨架
2. 建数据库表与种子数据
3. 完成基础查询接口
4. 完成订单新增与查询
5. 完成订单转工单
6. 完成排产结果保存与查询
7. 完成仿真触发接口骨架
8. 完成事件、质检、KPI 查询接口
9. 接入 B 的真实仿真输出
10. 与 C 做前端联调
11. 固定演示数据与接口说明

## 5. 数据库实施顺序

### 5.1 第一批：基础数据表

先建这 6 张表：

- `product`
- `station`
- `process_route`
- `material`
- `bom`
- `inventory`

目的：

- 让系统先具备“认识产品、工位、物料、工艺路线、库存”的能力
- 为后续订单、工单、排产和仿真提供稳定输入

### 5.2 第二批：主流程表

再建这 3 张表：

- `sales_order`
- `work_order`
- `schedule_task`

目的：

- 先打通“订单 -> 工单 -> 排产”的主链路

### 5.3 第三批：结果数据表

最后建这 3 张表：

- `production_event`
- `quality_record`
- `kpi_snapshot`

目的：

- 承接仿真结果
- 提供质检与 KPI 查询数据源

## 6. 接口开发顺序

### 6.1 第一阶段接口：先查后写

先做查询接口，保证数据库和返回结构稳定：

- `GET /orders`
- `GET /stations/status`
- `GET /schedule/tasks`
- `GET /events`
- `GET /quality/records`
- `GET /kpi/latest`
- `GET /kpi/compare`

说明：

- `GET /stations/status` 初期可用 mock 或静态规则返回
- 如果事件和 KPI 尚未生成，可先返回空列表 / 空对象，但接口结构必须稳定

### 6.2 第二阶段接口：订单主链路

优先完成：

- `POST /orders`
- `POST /orders/{order_no}/generate-work-order`

要求：

- 支持订单新增
- 支持订单转工单
- 支持在订单转工单时做 BOM 与库存预检查
- 订单阶段只预检查，不扣库存

### 6.3 第三阶段接口：排产与仿真承接

完成：

- `POST /schedule`
- `POST /simulation/run`

要求：

- `POST /schedule` 保存排产结果到 `schedule_task`
- `POST /simulation/run` 接收 B 的仿真输入参数并承接仿真输出
- 初期若 B 逻辑未准备好，可先写 mock 版本

## 7. 当前执行计划

### Day 1：今天先完成的内容

今天先做以下内容：

1. 创建 `backend/` 目录与基础文件
2. 建立 `FastAPI` 可运行骨架
3. 建立 `SQLite` 连接
4. 写 `schema.sql`
5. 建 12 张核心表
6. 写 `seed.py`
7. 初始化产品、工位、物料、BOM、库存、测试订单

今天的验收标准：

- `uvicorn` 启动成功
- `/docs` 可以打开
- `SQLite` 数据库文件可生成
- 种子数据可一键初始化

### Day 2：订单与工单

1. 完成 `POST /orders`
2. 完成 `GET /orders`
3. 完成 `POST /orders/{order_no}/generate-work-order`
4. 补齐订单编号、工单编号生成规则

验收标准：

- 可以新增订单
- 可以查询订单
- 可以从订单生成工单

### Day 3：排产落库

1. 完成 `POST /schedule`
2. 完成 `GET /schedule/tasks`
3. 保存 `schedule_task`
4. 输出前端甘特图所需字段

验收标准：

- 工单可以生成对应排产任务
- 前端可以拿到排产任务列表

### Day 4：仿真结果承接

1. 完成 `POST /simulation/run`
2. 完成 `production_event` 写入
3. 完成 `quality_record` 写入
4. 更新 `schedule_task.actual_start / actual_end`
5. 更新 `work_order_status`

验收标准：

- 仿真接口能返回结果
- 事件、质检、实际开始/结束时间可写库

### Day 5：KPI 与联调

1. 生成 `kpi_snapshot`
2. 完成 `GET /kpi/latest`
3. 完成 `GET /kpi/compare`
4. 与 C 联调首页、订单页、排产页、监控页、质量页

验收标准：

- 前端可以稳定展示 KPI、排产、事件、质检数据

## 8. 推荐目录结构

建议目录如下：

```text
backend/
  app/
    main.py
    database.py
    response.py
    models/
    schemas/
    routers/
    services/
    seed.py
  data/
    mes.db
  schema.sql
  requirements.txt
```

建议职责：

- `routers/`：定义 API 路由
- `schemas/`：定义请求 / 响应模型
- `models/`：定义数据库模型
- `services/`：写业务逻辑，如订单转工单、BOM 预检查、KPI 计算

## 9. 统一接口要求

所有接口统一返回：

```json
{
  "code": 200,
  "message": "ok",
  "data": {}
}
```

错误时：

```json
{
  "code": 400,
  "message": "error message",
  "data": null
}
```

接口设计要求：

- 路径和字段命名固定后不要随意改动
- 前端可先使用空数据，但字段名必须稳定
- 对 B 的输入输出要提前定义结构，不等联调时再想

## 10. 风险与规避

### 风险 1：字段频繁变化

规避：

- 先按协作契约把字段固定
- `work_order`、`schedule_task` 不要在接口联调后频繁改名

### 风险 2：B 的仿真还没接上，后端卡住

规避：

- 先写 `POST /simulation/run` mock 版本
- 先生成 mock 事件、质检和 KPI，确保 C 可以联调

### 风险 3：前端等待接口太久

规避：

- 先提供基础查询接口和测试数据
- 优先保证查询接口稳定，而不是等所有写入逻辑都完成

### 风险 4：随机工时参数与仿真单位不一致

规避：

- 数据库存秒
- 仿真执行前统一换算
- 文档、代码、前端展示分别注明单位

## 11. 当前最小验收闭环

只要下面这条链路能跑通，就说明后端第一阶段合格：

```text
POST /orders
-> POST /orders/{order_no}/generate-work-order
-> POST /schedule
-> POST /simulation/run
-> GET /kpi/latest
```

## 12. 执行原则

- 先建表，再写接口
- 先跑主链路，再补边角
- 先稳定字段，再接前端
- 先 mock 托底，再接真实逻辑
- 所有改动优先服务演示闭环
