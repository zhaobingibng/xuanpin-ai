# Phase 43.1 — Admin API 设计文档

> 生成时间: 2026-07-21 | 前置调研: PHASE43_WEB_ARCHITECTURE_REPORT.md

---

## 0. 现有模块确认清单

### 0.1 Dashboard 模块 ✅

| 文件 | 行数 | 关键能力 |
|------|------|----------|
| [app/api/dashboard.py](file:///d:/Projects/xuanpin-ai/app/api/dashboard.py) | 228 | `/dashboard/overview`, `/dashboard/system`, `/dashboard/tasks`, `/dashboard/notifications`, `/dashboard/logs`, `/dashboard/crawler-status`, `/dashboard/taobao/*` (×6) |
| [app/services/dashboard/service.py](file:///d:/Projects/xuanpin-ai/app/services/dashboard/service.py) | 224 | `DashboardService(AsyncSession)` → `overview()`, `system_overview()`, `get_recent_tasks()`, `get_notifications()`, `get_logs()` |

**Admin 复用方式**: `DashboardService` 直接复用，不重复实现。Admin overview 合并 `overview()` + `system_overview()` 一次返回。

### 0.2 Report 模块 ✅

| 文件 | 行数 | 关键能力 |
|------|------|----------|
| [app/api/reports.py](file:///d:/Projects/xuanpin-ai/app/api/reports.py) | 175 | `/reports/daily`, `/reports/history`, `/reports/lifecycle/hot`, `/reports/lifecycle/rising`, `/reports/{id}` |
| [app/services/report/daily_report.py](file:///d:/Projects/xuanpin-ai/app/services/report/daily_report.py) | 174 | `DailyReportService(AsyncSession)` → `generate()`, `generate_and_save()` |

**Admin 复用方式**: `DailyReportService` 和 `ReportRepository` 直接复用。

### 0.3 Task 模块 ✅

| 文件 | 行数 | 关键能力 |
|------|------|----------|
| [app/api/tasks.py](file:///d:/Projects/xuanpin-ai/app/api/tasks.py) | 115 | `/tasks/failed`, `/tasks/{id}`, `/tasks/{id}/retry` |
| [app/tasks/scheduler.py](file:///d:/Projects/xuanpin-ai/app/tasks/scheduler.py) | 370 | `TaskScheduler` — `add_auto_crawl()`, `add_daily_selection()`, `list_jobs()`, `remove_job()`, `stop()`/`start()` |
| [app/tasks/jobs.py](file:///d:/Projects/xuanpin-ai/app/tasks/jobs.py) | 672 | `daily_crawl_job()`, `auto_crawl_job()`, `daily_pipeline_job()` |
| [app/tasks/daily_selection_task.py](file:///d:/Projects/xuanpin-ai/app/tasks/daily_selection_task.py) | 172 | `daily_selection_job()`, `run_daily_selection_once()` |
| [app/services/task_queue/service.py](file:///d:/Projects/xuanpin-ai/app/services/task_queue/service.py) | 193 | `TaskQueueService(AsyncSession)` — `record_failure()`, `retry_task()`, `get_failed_tasks()` |

**Admin 复用方式**:
- Scheduler 通过 `app.api.main._scheduler_instance` 全局变量访问 — **需提取为可控单例**
- `TaskQueueService` 直接复用
- `TaskExecutionRepository` 直接复用

### 0.4 淘宝登录模块 ✅

| 文件 | 行数 | 关键能力 |
|------|------|----------|
| [app/services/login_helper.py](file:///d:/Projects/xuanpin-ai/app/services/login_helper.py) | 300 | `LoginHelper(AsyncSession?)` — `save_state_file()`, `load_state_file()`, `has_state_file()`, `get_login_status_summary()`, `update_login_session()` |
| [app/crawler/auth_manager.py](file:///d:/Projects/xuanpin-ai/app/crawler/auth_manager.py) | 285 | `AuthManager(cookie_dir)` — `check_login_state()`, `can_crawl()`, `has_storage_state()`, `has_cookies()` |
| [app/crawler/taobao.py](file:///d:/Projects/xuanpin-ai/app/crawler/taobao.py) | 1221 | `TaobaoCrawler` — `crawl()`, `crawl_shop()`, `crawl_with_metrics()`, `check_login()`, `pre_crawl_auth_check()`, `_new_context()`, `load_storage_state()`, `save_storage_state()` |
| [app/services/taobao_session_service.py](file:///d:/Projects/xuanpin-ai/app/services/taobao_session_service.py) | 381 | `TaobaoSessionService` 全局单例 — `start_session()`, `stop_session()`, `check_status()`, `crawl()`, `wait_for_human()` |

**Admin 复用方式**:
- `LoginHelper.get_login_status_summary()` 直接复用 — 已覆盖淘宝/1688 登录态
- `TaobaoSessionService` 已有完整 API（dashboard.py 中），admin 直接引用，不重复
- 1688 暂无 SessionService — 仅查登录态即可

### 0.5 1688 供应链模块 ✅

| 文件 | 行数 | 关键能力 |
|------|------|----------|
| [app/services/supplier_matching.py](file:///d:/Projects/xuanpin-ai/app/services/supplier_matching.py) | 490 | `SupplierMatchingService` — `match_products_with_matcher()` (统一入口), `match_product()` (旧) |
| [app/services/supply_chain/matcher.py](file:///d:/Projects/xuanpin-ai/app/services/supply_chain/matcher.py) | 228 | `SupplyChainMatcher` **[DEPRECATED]** — 请使用 `SupplierMatchingService` |
| [app/services/supply_chain/provider.py](file:///d:/Projects/xuanpin-ai/app/services/supply_chain/provider.py) | 160 | `SupplyChainProvider` — 供应商数据获取 |
| [app/services/supply_chain/profit_calculator.py](file:///d:/Projects/xuanpin-ai/app/services/supply_chain/profit_calculator.py) | 165 | 利润计算 |

**确认**:
- 不存在 `app/matching/` 目录
- 不存在 `app/repositories/` 目录（repository 模式在 `app/database/` 下）
- Admin 暂不需要调用供应链匹配（那属于业务流水线）

---

## 1. 设计原则

1. **最大化复用**: 每个 admin 端点必须直接调用已有 Service/Repository，零业务逻辑重写
2. **纯编排层**: `app/api/admin.py` 只做参数校验 + 调用 + 格式转换
3. **不修改核心**: 不碰 `TaobaoCrawler`、`DailySelectionPipeline`、`ProductService` 等核心类
4. **统一返回格式**: `{"success": true, "data": ..., "message": ""}`
5. **全部带测试**: 每个端点对应 ≥1 个单元测试

---

## 2. 新增文件清单

| 文件 | 职责 |
|------|------|
| `app/api/admin.py` | Admin REST API 路由（纯编排，~250行） |
| `tests/test_admin_api.py` | Admin API 测试 |

> **不新增 service 层**：admin 端点直接调用已有 Service/Repository，不到 250 行代码无需抽象层。

---

## 3. 接口设计

### 3.1 Admin 总览

```
GET /admin/overview
```

**调用 Service**:
- `DashboardService.overview()` — 业务统计
- `DashboardService.system_overview()` — 运维统计
- `LoginHelper.get_login_status_summary()` — 登录态
- `ShopService.get_shop_stats()` — 店铺统计

**返回结构**:
```json
{
  "success": true,
  "data": {
    "business": {
      "products": 1234,
      "today_crawl": 56,
      "hot_products": 12,
      "rising_products": 34,
      "today_recommendations": 20,
      "average_score": 72.5,
      "platform_distribution": {"taobao": 800, "xiaohongshu": 434},
      "category_distribution": {"食品": 300, "美妆": 200}
    },
    "operations": {
      "health": {"status": "healthy", "database": true, "crawler": true, "scheduler": true},
      "task_stats": {"total": 150, "failed": 3, "success_rate": 98.0},
      "scheduler_running": true
    },
    "login": {
      "taobao": {"state_file_exists": true, "db_status": "ACTIVE", "is_active": true},
      "1688": {"state_file_exists": false, "db_status": null, "is_active": false}
    },
    "shops": {"total": 25, "enabled": 20, "by_platform": {"taobao": 15, "xiaohongshu": 10}}
  }
}
```

**风险**: 🟢 低 — 全部复用已有 Service，纯聚合查询。若任一子查询失败，单独捕获不阻断其他。

---

### 3.2 平台采集控制

#### 3.2.1 查看所有平台状态

```
GET /admin/platforms
```

**调用 Service**:
- `CrawlerStatusRepository.get_latest(limit=10)` — 各平台最近采集状态
- `app.config.settings.get_settings().crawl_platforms` — 已启用平台列表

**返回结构**:
```json
{
  "success": true,
  "data": {
    "enabled_platforms": ["xiaohongshu", "taobao"],
    "all_platforms": ["xiaohongshu", "taobao", "douyin", "kuaishou"],
    "statuses": [
      {"platform": "taobao", "last_run": "2026-07-21T08:00:00", "status": "ok", "total": 120, "success": 115, "failed": 5},
      {"platform": "xiaohongshu", "last_run": "2026-07-21T08:05:00", "status": "ok", "total": 80, "success": 78, "failed": 2}
    ]
  }
}
```

**风险**: 🟡 中 — `crawl_platforms` 在 `settings.py` 中是运行时只读的 list，修改需要更新 settings 实例。建议通过 `AppSettings` 实例直接修改 `crawl_platforms` 字段（pydantic-settings 支持运行时修改但非线程安全）。

#### 3.2.2 启停平台采集

```
POST /admin/platforms/{platform}/toggle
Body: {"enabled": true}
```

**调用 Service**:
- `app.config.settings.get_settings()` — 修改 `crawl_platforms` list（add/remove platform）
- 无 DB 写入（暂不持久化到 DB，重启后恢复 .env 默认值）

**返回结构**:
```json
{"success": true, "data": {"platform": "douyin", "enabled": true}, "message": "平台 douyin 采集已开启"}
```

**风险**: 🔴 高 — 修改全局 settings 实例非线程安全，且重启丢失。**建议 Phase 43.1 仅做内存级修改**，后续 Phase 可持久化到 DB。

---

### 3.3 关键词管理

```
GET  /admin/keywords                          # 列表
POST /admin/keywords                          # 添加
     Body: {"keywords": ["蓝牙耳机", "手机配件"]}
DELETE /admin/keywords/{keyword}              # 删除单个
```

**调用 Service**:
- `app.config.settings.get_settings()` — 读写 `crawl_keywords` list

**返回结构 (GET)**:
```json
{"success": true, "data": {"keywords": ["蓝牙耳机", "手机配件", "家居用品", ...], "count": 7}}
```

**返回结构 (POST/DELETE)**:
```json
{"success": true, "data": {"keywords": [...], "count": 6}, "message": "关键词已添加/删除"}
```

**风险**: 🟡 中 — 与平台采集相同的内存修改问题。当前 `crawl_keywords` 在 settings 中定义，job 执行时读取。如果 scheduler 正在运行中修改，下次 job 执行时生效。可增加去重逻辑。

---

### 3.4 定时任务操控

#### 3.4.1 查看所有 job

```
GET /admin/jobs
```

**调用 Service**:
- `app.api.main._scheduler_instance` → `list_jobs()`

**返回结构**:
```json
{
  "success": true,
  "data": {
    "scheduler_running": true,
    "jobs": [
      {"id": "daily_crawl", "name": "Auto crawl (from settings)", "next_run": "2026-07-22T02:00:00", "trigger": "cron[hour=2, minute=0]"},
      {"id": "daily_selection", "name": "Daily selection", "next_run": "2026-07-22T02:00:00", "trigger": "cron[hour=2, minute=0]"}
    ]
  }
}
```

**风险**: 🟡 中 — `_scheduler_instance` 来自 `app.api.main` 全局变量。耦合但可接受（已有先例：`system.py` 中 `selection/toggle` 也是这样访问的）。可直接复用该模式。

#### 3.4.2 手动触发 job

```
POST /admin/jobs/{job_id}/trigger
```

**调用 Service**:
- `app.api.main._scheduler_instance`
- `app.tasks.jobs.auto_crawl_job` / `app.tasks.daily_selection_task.run_daily_selection_once`

**实现**: 根据 job_id 路由到对应 job 函数，通过 `TaskScheduler.tracked_execute()` 或直接 `asyncio.create_task()` 后台执行

**返回结构**:
```json
{"success": true, "data": {"job_id": "daily_crawl", "triggered_at": "2026-07-21T15:30:00"}, "message": "任务已触发"}
```

**风险**: 🟡 中 — 手动触发可能与定时任务并发执行。需加简易防并发（检查是否有同 job 正在 RUNNING）。用 `TaskExecutionRepository` 查询最近一条同 task_name 的 RUNNING 记录即可。

#### 3.4.3 暂停/恢复 scheduler

```
POST /admin/scheduler/pause
POST /admin/scheduler/resume
```

**调用 Service**: `_scheduler_instance.stop()` / `_scheduler_instance.start()`

**返回**: `{"success": true, "message": "调度器已暂停/恢复", "data": {"running": false/true}}`

**风险**: 🟢 低 — `TaskScheduler` 已有 stop/start 方法。暂停后定时任务不会触发，手动触发仍可用。

---

### 3.5 登录状态总览

```
GET /admin/login-status
```

**调用 Service**:
- `LoginHelper.get_login_status_summary()` — 淘宝 + 1688
- `TaobaoSessionService.get_snapshot()` — 淘宝浏览器会话状态（Phase 42.6）

**返回结构**:
```json
{
  "success": true,
  "data": {
    "taobao": {
      "state_file_exists": true,
      "db_status": "ACTIVE",
      "is_active": true,
      "session": {"state": "logged_in", "is_logged_in": true, "is_blocked": false}
    },
    "1688": {
      "state_file_exists": false,
      "db_status": null,
      "is_active": false,
      "session": null
    }
  }
}
```

**风险**: 🟢 低 — 纯查询，`LoginHelper` 和 `TaobaoSessionService` 均已存在。`LoginHelper` 构造时传 `session=None` 仍可用（仅查文件）。

---

### 3.6 采集日志增强查询

```
GET /admin/crawler-logs?platform=taobao&status=FAILED&limit=50&keyword=海苔
```

**调用 Service**: `CrawlLogRepository.get_logs(limit, platform)`

**与已有 `/crawler/logs` 的区别**:
- 增加 `status` 和 `keyword` 过滤参数
- 返回统一 `{success, data}` 格式

**返回结构**:
```json
{
  "success": true,
  "data": {
    "total": 42,
    "items": [
      {"id": 1, "keyword": "海苔卷", "platform": "taobao", "status": "SUCCESS", "total": 50, "success": 48, "failed": 2, "start_time": "...", "end_time": "..."}
    ]
  }
}
```

**风险**: 🟢 低 — `CrawlLogRepository` 已有基础查询，只需增加过滤参数。若 repository 不支持 `status`/`keyword` 过滤，直接在 API 层用列表推导过滤（数据量小）。

---

### 3.7 失败任务增强查询

```
GET /admin/failed-tasks?status=PENDING&limit=100
```

**调用 Service**: `TaskQueueService.get_failed_tasks(status, limit)`

**与已有 `/tasks/failed` 的区别**:
- 统一返回格式 `{success, data}`
- 增加 `total` 计数
- 增加 `resolved_count` 统计

**风险**: 🟢 低 — 直接复用 `TaskQueueService`。

---

### 3.8 商品统计摘要

```
GET /admin/product-stats
```

**调用 Service**: `ProductService.list_all()` + 聚合计算

**返回结构**:
```json
{
  "success": true,
  "data": {
    "total": 1234,
    "by_platform": {"taobao": 800, "xiaohongshu": 434},
    "by_status": {"ACTIVE": 1200, "INACTIVE": 34},
    "by_lifecycle": {"HOT": 12, "RISING": 34, "STABLE": 500, "DECLINING": 100, "NEW": 588},
    "avg_price": 45.6,
    "avg_ai_score": 62.3
  }
}
```

**风险**: 🟢 低 — 纯 SQL 聚合查询，`Product` 表数据量可控（<10K）。

---

## 4. 接口全景汇总

| # | 方法 | 路径 | 调用已有 Service | 风险 |
|---|------|------|-------------------|------|
| 1 | GET | `/admin/overview` | DashboardService + LoginHelper + ShopService | 🟢 |
| 2 | GET | `/admin/platforms` | CrawlerStatusRepository + Settings | 🟡 |
| 3 | POST | `/admin/platforms/{p}/toggle` | Settings 内存修改 | 🔴 |
| 4 | GET | `/admin/keywords` | Settings.crawl_keywords | 🟡 |
| 5 | POST | `/admin/keywords` | Settings.crawl_keywords 追加 | 🟡 |
| 6 | DELETE | `/admin/keywords/{kw}` | Settings.crawl_keywords 移除 | 🟡 |
| 7 | GET | `/admin/jobs` | _scheduler_instance.list_jobs() | 🟡 |
| 8 | POST | `/admin/jobs/{id}/trigger` | _scheduler_instance + job 函数 | 🟡 |
| 9 | POST | `/admin/scheduler/pause` | _scheduler_instance.stop() | 🟢 |
| 10 | POST | `/admin/scheduler/resume` | _scheduler_instance.start() | 🟢 |
| 11 | GET | `/admin/login-status` | LoginHelper + TaobaoSessionService | 🟢 |
| 12 | GET | `/admin/crawler-logs` | CrawlLogRepository | 🟢 |
| 13 | GET | `/admin/failed-tasks` | TaskQueueService | 🟢 |
| 14 | GET | `/admin/product-stats` | ProductService + SQL 聚合 | 🟢 |

合计: **14 个端点**，全部复用已有 Service，纯编排无业务逻辑。

---

## 5. 需要修改的现有文件

| 文件 | 修改内容 | 必要性 |
|------|----------|--------|
| [app/api/main.py](file:///d:/Projects/xuanpin-ai/app/api/main.py) | 添加 `from app.api.admin import router as admin_router` + `app.include_router(admin_router)` | 🔴 必须 |

> 其他文件**零修改**。所有 admin API 都是对已有 Service 的只读编排。

---

## 6. 风险汇总与缓解

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| Settings 运行时修改非线程安全 | 🔴 | 端点加 `asyncio.Lock`；文档标注"重启后恢复默认" |
| `_scheduler_instance` 全局变量耦合 | 🟡 | 与 `system.py` 中 toggle 采用相同访问模式，保持一致即可 |
| 手动触发与定时任务并发 | 🟡 | 触发前检查 `TaskExecutionRepository` 有无同 task_name 的 RUNNING 记录 |
| CrawlLogRepository 不支持 status/keyword 过滤 | 🟢 | API 层用列表推导过滤（<1K 条数据量） |
| 无认证直接暴露操控端点 | 🔴 | 暂不在此 Phase 加（纳入 Phase 43.2 或独立 Phase） |

---

## 7. 不纳入 Phase 43.1 的范围

| 项目 | 原因 |
|------|------|
| 1688 浏览器会话操控 | 暂无 `AlibabaSessionService`（不同于淘宝的 `TaobaoSessionService`），需独立 Phase |
| 供应链匹配触发 | 属于业务流水线，不是 admin 职责 |
| 数据库备份/恢复 | 运维工具，独立 Phase |
| 用户/权限管理 | 无用户模型，独立 Phase |
| Settings 持久化到 DB | 需新建 `system_config` 表 + migration，独立 Phase |
| 前端 Admin 页面 | Phase 43.2 |

---

*下一步: 用户确认后开始编码。*
