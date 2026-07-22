# Phase 43 — Web/API 架构全面调研报告

> 生成时间: 2026-07-21 | 目标: 为新增 admin 控制台做架构准备

---

## 1. FastAPI 主入口

### 入口文件

| 项目 | 详情 |
|------|------|
| 文件 | [app/api/main.py](file:///d:/Projects/xuanpin-ai/app/api/main.py) |
| 启动方式 | `python main.py api` → `uvicorn.run("app.api.main:app", host=..., port=8000)` |
| App 实例 | `FastAPI(title="xuanpin-ai API", lifespan=lifespan)` |

### Lifespan

```
startup → 创建 TaskScheduler → 注册 auto_crawl + daily_selection → scheduler.start()
shutdown → scheduler.stop()
```

### Middleware

| Middleware | 配置 |
|------------|------|
| CORS | `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]` |
| 其他 | 无（无认证、无限流、无日志中间件） |

### Router 注册方式

所有 router 在 `main.py` 通过 `app.include_router(router)` 全局注册，**无统一 prefix**。各 router 内部自行定义 prefix（如 `/api/ai-analysis`、`/api/shops`、`/api/selection`），其余使用扁平路径。

---

## 2. 当前 API 路由全景

共 **18 个 Router**，合计 **~60 个端点**。

### 路由清单

| # | Router 文件 | 自行声明的 prefix | 端点 | 功能 |
|---|-------------|-------------------|------|------|
| 1 | `assistant.py` | (无) | `POST /assistant/ask`<br>`GET /assistant/history` | AI 选品问答 |
| 2 | `ai_analysis.py` | `/api/ai-analysis` | `GET /api/ai-analysis/status`<br>`POST /api/ai-analysis/product/{id}`<br>`POST /api/ai-analysis/report/{id}/summary` | LLM 商品分析 + 报告摘要 |
| 3 | `crawler.py` | (无) | `GET /crawler/status`<br>`GET /crawler/logs` | 采集状态 + 日志 |
| 4 | **`dashboard.py`** | (无) | `GET /dashboard/overview`<br>`GET /dashboard/system`<br>`GET /dashboard/tasks`<br>`GET /dashboard/notifications`<br>`GET /dashboard/logs`<br>`GET /dashboard/crawler-status`<br>`GET /dashboard/taobao/status`<br>`POST /dashboard/taobao/start`<br>`POST /dashboard/taobao/stop`<br>`POST /dashboard/taobao/check`<br>`POST /dashboard/taobao/crawl`<br>`POST /dashboard/taobao/wait-human` | 运营面板 + 淘宝操控台 |
| 5 | `knowledge.py` | (无) | `GET /knowledge/tags`<br>`GET /knowledge/products/{id}`<br>`POST /knowledge/learn` | 知识库标签 |
| 6 | `learning.py` | (无) | `GET /learning/config`<br>`POST /learning/optimize`<br>`GET /learning/history` | 评分权重学习 |
| 7 | `products.py` | (无) | `GET /products`<br>`GET /products/categories`<br>`GET /products/recommendations`<br>`GET /products/{id}/trend`<br>`GET /products/{id}/detail`<br>`GET /products/{id}` | 商品 CRUD + 趋势 |
| 8 | `ranking.py` | (无) | `GET /ranking/top100` | 综合排行榜 |
| 9 | `recommendations.py` | (无) | `GET /recommendations/today`<br>`GET /recommendations/daily`<br>`GET /recommendations/stats`<br>`GET /recommendations/opportunities` | 今日推荐 + 机会分析 |
| 10 | `reports.py` | (无) | `GET /reports/daily`<br>`GET /reports/history`<br>`GET /reports/lifecycle/hot`<br>`GET /reports/lifecycle/rising`<br>`GET /reports/{id}` | 日报生成 + 生命周期 |
| 11 | `reviews.py` | (无) | `GET /reviews/latest`<br>`GET /reviews/accuracy` | 推荐复盘 + 准确率 |
| 12 | `stats.py` | (无) | `GET /stats/category`<br>`GET /stats/platform` | 分类/平台统计 |
| 13 | `strategy.py` | (无) | `POST /strategy/generate`<br>`GET /strategy/{product_id}` | AI 运营方案 |
| 14 | `system.py` | (无) | `GET /system/health`<br>`GET /system/selection/status`<br>`POST /system/selection/toggle` | 系统健康 + 开关 |
| 15 | `metrics.py` | (无) | `GET /metrics` | Prometheus 指标 |
| 16 | `tasks.py` | (无) | `GET /tasks/failed`<br>`GET /tasks/{id}`<br>`POST /tasks/{id}/retry` | 失败任务管理 |
| 17 | `selection.py` | `/api/selection` | `GET /api/selection/daily` | 缓存选品报告 |
| 18 | `shops.py` | (无) | `GET /api/shops`<br>`POST /api/shops`<br>`PATCH /api/shops/{pk}`<br>`DELETE /api/shops/{pk}` | 店铺注册表 CRUD |

### 返回格式特征

- **成功**: 直接返回 `dict`/`list[dict]`，无统一 `{code, data, message}` 包装
- **失败**: `HTTPException(status_code=500/404, detail="...")` 抛出
- **少量端点**使用了 `response_model=` 做 Pydantic 校验（如 `reports.py`）
- **无分页标准**：各端点自行处理（`limit`/`offset` Query 参数）

---

## 3. 前端项目现状

### **存在成熟前端项目**

| 项目 | 详情 |
|------|------|
| 目录 | `xuanpin-dashboard/` |
| 技术栈 | Vue 3.5 + TypeScript 5.7 + Vite 6 + Element Plus 2.9 + ECharts 5.6 + vue-router 4.5 + Axios |
| 构建 | `npm run dev` / `npm run build` / `npm run preview` |
| API 基址 | `http://127.0.0.1:8000` (硬编码在 `src/api/index.ts`) |

### 已有页面 (6 个)

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` | [Dashboard.vue](file:///d:/Projects/xuanpin-ai/xuanpin-dashboard/src/views/Dashboard.vue) (531行) | 健康状态、分类/平台图表、AI选品入口、淘宝操控台、TOP100 |
| `/products/:id` | [ProductDetail.vue](file:///d:/Projects/xuanpin-ai/xuanpin-dashboard/src/views/ProductDetail.vue) | 商品详情 + 趋势 |
| `/workbench` | [Workbench.vue](file:///d:/Projects/xuanpin-ai/xuanpin-dashboard/src/views/Workbench.vue) | 运营工作台 |
| `/reports/daily` | [DailyReport.vue](file:///d:/Projects/xuanpin-ai/xuanpin-dashboard/src/views/DailyReport.vue) | 每日选品报告 |
| `/shops` | [ShopRegistry.vue](file:///d:/Projects/xuanpin-ai/xuanpin-dashboard/src/views/ShopRegistry.vue) | 店铺注册管理 |
| `/ai-analysis` | [AIAnalysis.vue](file:///d:/Projects/xuanpin-ai/xuanpin-dashboard/src/views/AIAnalysis.vue) | AI 分析面板 |

### 已有组件 (9 个)

AIAssistant, CategoryChart, PlatformChart, TopRankingTable, TrendChart, RecommendationList, OpportunityTable, StrategyPanel, LLMInsightCard

### 结论

**不需要创建新的前端项目**。当前 `xuanpin-dashboard` 功能已相当完整，admin 控制台应该在此项目中**新增页面**而非另起炉灶。无 `templates/`、`static/`、Jinja2 模板等后端渲染方式。

---

## 4. Dashboard/Report 能力盘点

### 已有 Dashboard 能力

| 端点 | 能力 | Service |
|------|------|---------|
| `/dashboard/overview` | 商品总数、今日采集、HOT/RISING 商品数、今日推荐、平台/分类分布 | [DashboardService](file:///d:/Projects/xuanpin-ai/app/services/dashboard/service.py) |
| `/dashboard/system` | 健康状态、uptime、任务统计 (成功率)、采集器/调度器状态 | DashboardService |
| `/dashboard/tasks` | 最近任务执行记录 (名称/时间/状态/耗时/错误) | DashboardService → TaskExecutionRepository |
| `/dashboard/notifications` | 通知历史 (存入内存列表) | DashboardService → `_notification_history` |
| `/dashboard/logs` | 读取 app/error/crawler 日志文件 | DashboardService → 文件系统 |
| `/dashboard/crawler-status` | 各平台最近采集状态 | CrawlerStatusRepository |
| `/dashboard/taobao/*` | 淘宝浏览器会话操控 (启动/停止/检测/采集/等待人工) | [TaobaoSessionService](file:///d:/Projects/xuanpin-ai/app/services/taobao_session_service.py) |

### 已有 Report 能力

| 端点 | 能力 |
|------|------|
| `/reports/daily` | 生成每日选品日报 (TOP N，含评分/生命周期/决策) |
| `/reports/history` | 历史日报列表 |
| `/reports/lifecycle/hot` | HOT 生命周期商品 |
| `/reports/lifecycle/rising` | RISING 生命周期商品 |
| `/reports/{id}` | 日报详情 (含所有条目) |
| `/api/selection/daily` | 缓存版选品日报 (含 AI 分析、供应链匹配) |

### 缺失的 Admin 能力 (待补充)

- ❌ 平台采集开关 (按平台独立控制)
- ❌ 关键词管理 (增删改查)
- ❌ 定时任务管理 (查看/触发/暂停/修改 cron)
- ❌ 系统配置面板 (可视化修改 .env 等效参数)
- ❌ 商品批量操作 (批量下架/删除/导出)
- ❌ 用户/权限管理
- ❌ 操作审计日志

---

## 5. 现有服务层全景

### 核心服务 (按功能域)

| 服务 | 文件 | 注入方式 | 职责 |
|------|------|----------|------|
| **ProductService** | [app/services/product_service.py](file:///d:/Projects/xuanpin-ai/app/services/product_service.py) | `AsyncSession` | 商品 CRUD + 批量入库 (清洗→upsert→历史快照) |
| **DashboardService** | [app/services/dashboard/service.py](file:///d:/Projects/xuanpin-ai/app/services/dashboard/service.py) | `AsyncSession` | 系统统计聚合 |
| **ShopService** | [app/services/shop_service.py](file:///d:/Projects/xuanpin-ai/app/services/shop_service.py) | `AsyncSession` | 店铺注册表 CRUD + 扫描调度 |
| **TaskQueueService** | [app/services/task_queue/service.py](file:///d:/Projects/xuanpin-ai/app/services/task_queue/service.py) | `AsyncSession` | 失败任务队列 (记录/重试/状态流转) |
| **DailyReportService** | [app/services/report/daily_report.py](file:///d:/Projects/xuanpin-ai/app/services/report/daily_report.py) | `AsyncSession` | 日报生成 + 持久化 |
| **DailySelectionPipeline** | [app/services/selection/daily_selection_pipeline.py](file:///d:/Projects/xuanpin-ai/app/services/selection/daily_selection_pipeline.py) | 依赖注入 (无状态) | 选品流水线编排 (候选→匹配→评分→报告→AI) |
| **TaobaoSessionService** | [app/services/taobao_session_service.py](file:///d:/Projects/xuanpin-ai/app/services/taobao_session_service.py) | 全局单例 | 淘宝浏览器会话管理 |
| **HealthService** | [app/services/health/service.py](file:///d:/Projects/xuanpin-ai/app/services/health/service.py) | `AsyncSession` | 系统健康检查 |
| **MetricsService** | [app/services/metrics/service.py](file:///d:/Projects/xuanpin-ai/app/services/metrics/service.py) | 静态方法 | Prometheus 指标 |
| **NotificationService** | [app/services/notification/service.py](file:///d:/Projects/xuanpin-ai/app/services/notification/service.py) | 无状态 | 通知推送 + 飞书 |
| **ScoringOptimizer** | [app/services/learning/optimizer.py](file:///d:/Projects/xuanpin-ai/app/services/learning/optimizer.py) | `AsyncSession` | 评分权重学习优化 |
| **RecommendationRanker** | [app/services/recommendation/ranker.py](file:///d:/Projects/xuanpin-ai/app/services/recommendation/ranker.py) | 无状态 | 推荐排序 |
| **ProductScorer** | [app/services/scoring/product_scorer.py](file:///d:/Projects/xuanpin-ai/app/services/scoring/product_scorer.py) | 无状态 | 商品综合评分 |
| **SupplierMatchingService** | [app/services/supplier_matching.py](file:///d:/Projects/xuanpin-ai/app/services/supplier_matching.py) | 无状态 | 供应链匹配 |
| **SelectionAssistant** | [app/services/assistant/assistant.py](file:///d:/Projects/xuanpin-ai/app/services/assistant/assistant.py) | `AsyncSession` | AI 选品问答 |

### Service 设计模式总结

- **统一注入**: 绝大多数 service 以 `AsyncSession` 构造，在 API 层通过 `get_async_session_factory()` 获取 session
- **全局单例**: `TaobaoSessionService` 使用 `get_taobao_session()` 全局单例
- **无状态工具**: `ProductScorer`、`RecommendationRanker`、`OpportunityScorer` 等无 session 依赖
- **延迟导入**: 很多 service 在端点函数内部 `from app.services.xxx import` 来避免循环依赖

---

## 6. Admin 控制台推荐方案

### 6.1 新增 Admin 最合理位置

```
┌─────────────────────────────────────────────────┐
│  后端                                           │
│  app/api/admin.py          ← NEW 统一 admin 路由 │
│  app/services/admin/       ← NEW admin 服务层    │
│    ├── __init__.py                               │
│    ├── config_service.py   ← 系统配置读写         │
│    ├── keyword_service.py  ← 关键词管理           │
│    └── platform_service.py ← 平台开关控制         │
│                                                  │
│  app/api/main.py           ← 注册 admin router   │
├─────────────────────────────────────────────────┤
│  前端                                           │
│  xuanpin-dashboard/src/                         │
│    views/Admin.vue         ← NEW 管理中心主页     │
│    views/admin/            ← NEW 子页面目录       │
│      ConfigPanel.vue                             │
│      KeywordManager.vue                          │
│      JobScheduler.vue                            │
│    api/index.ts            ← 新增 admin API 函数  │
│    router/index.ts         ← 新增 /admin 路由     │
│    types/admin.ts          ← NEW 类型定义         │
└─────────────────────────────────────────────────┘
```

### 6.2 推荐方案

#### 方案: 后端 Admin API + 前端 Admin 页面 (最小可行)

**Phase 43.1 — 后端 Admin API**

1. 新建 `app/api/admin.py`，包含:
   - `GET /admin/overview` — admin 专属总览 (合并 dashboard + system)
   - `GET /admin/platforms` — 各平台采集状态 + 开关控制
   - `POST /admin/platforms/{name}/toggle` — 开启/关闭某平台采集
   - `GET /admin/keywords` — 关键词列表
   - `POST /admin/keywords` — 添加关键词
   - `DELETE /admin/keywords/{id}` — 删除关键词
   - `GET /admin/jobs` — 定时任务列表 (Scheduler)
   - `POST /admin/jobs/{id}/trigger` — 手动触发任务

2. 提取关键词管理到数据库 (当前在 `settings.py` 中是硬编码 list)

**Phase 43.2 — 前端 Admin 页面**

3. 在 `xuanpin-dashboard` 中新增 `/admin` 路由 + `Admin.vue`
4. 复用现有 Element Plus 组件体系

### 6.3 需要新增的文件

| 文件 | 说明 |
|------|------|
| `app/api/admin.py` | Admin REST API (统一入口，~200行) |
| `app/services/admin/__init__.py` | Admin 服务层包 |
| `app/services/admin/platform_service.py` | 平台开关管理 |
| `app/services/admin/keyword_service.py` | 关键词 CRUD |
| `app/models/keyword.py` | 关键词 ORM 模型 (可选，用 settings 也行) |
| `xuanpin-dashboard/src/views/Admin.vue` | Admin 主页面 |
| `xuanpin-dashboard/src/views/admin/ConfigPanel.vue` | 平台配置面板 |
| `xuanpin-dashboard/src/views/admin/KeywordManager.vue` | 关键词管理面板 |
| `xuanpin-dashboard/src/views/admin/JobScheduler.vue` | 任务调度面板 |
| `xuanpin-dashboard/src/types/admin.ts` | Admin 类型定义 |
| `tests/test_admin_api.py` | Admin API 测试 |

### 6.4 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `app/api/main.py` | 添加 `from app.api.admin import router as admin_router` + `app.include_router(admin_router)` |
| `app/api/dashboard.py` | 可选：将 `/dashboard/taobao/*` 移入 admin 或保持现状 |
| `app/config/settings.py` | 可选：将 `crawl_platforms` / `crawl_keywords` 改为可运行时修改 |
| `xuanpin-dashboard/src/api/index.ts` | 新增 admin API 函数 |
| `xuanpin-dashboard/src/router/index.ts` | 新增 `/admin` 路由 |
| `xuanpin-dashboard/src/App.vue` | 可选：添加导航栏 |

### 6.5 风险点

| 风险 | 等级 | 说明 | 缓解措施 |
|------|------|------|----------|
| **无认证机制** | 🔴 高 | 当前 API 零认证，admin 控制台暴露后任何人可操控系统 | 至少加一个简单的 API Key / Token 认证中间件 |
| **Scheduler 状态依赖** | 🟡 中 | `admin/jobs` 需读取 `_scheduler_instance`（main.py 全局变量），耦合较强 | 将 scheduler 实例提取为可注入的单例 |
| **前端 API baseURL 硬编码** | 🟡 中 | `http://127.0.0.1:8000` 写死在 `api/index.ts`，部署时需改代码 | 使用 Vite 环境变量 `import.meta.env.VITE_API_BASE` |
| **SQLite 并发写入** | 🟡 中 | 多个 admin 操作同时修改 settings/关键词时可能锁冲突 | 使用 WAL 模式 (已启用) + 操作串行化 |
| **TaobaoSessionService 全局单例** | 🟢 低 | admin 中启动/停止淘宝会话需访问全局单例，测试困难 | 已有 `get_taobao_session()` 封装，可 mock |
| **前端路由无权限控制** | 🟢 低 | 当前所有页面公开访问，无角色区分 | 短期可接受，后续加路由守卫 |
| **dashboard.py 端点膨胀** | 🟢 低 | Phase 42.6 的 Taobao 端点已塞入 dashboard.py (228行) | Admin 端点放入独立 `admin.py` 避免进一步膨胀 |
| **关键词硬编码** | 🟡 中 | `crawl_keywords` 在 `settings.py` 中是硬编码 list，运行时不可修改 | 可先做内存级修改 (影响 scheduler)，后续入库 |
| **CORS allow_origins=["*"]** | 🟡 中 | 生产环境存在安全风险 | 生产部署时改为具体域名 |

---

## 附录 A: 项目目录速览

```
xuanpin-ai/
├── app/
│   ├── api/           ← 18 个路由文件 + schemas/
│   │   └── main.py    ← FastAPI app + lifespan + CORS
│   ├── services/      ← 23 个服务目录/文件
│   ├── models/        ← ORM 模型
│   ├── database/      ← Repository 层 + base.py
│   ├── crawler/       ← 爬虫实现 (taobao, xiaohongshu, base, browser)
│   ├── tasks/         ← APScheduler 调度
│   ├── config/        ← settings.py (pydantic-settings)
│   ├── ai/            ← LLM client + prompts
│   └── utils/
├── xuanpin-dashboard/ ← Vue 3 前端 (Vite + Element Plus)
│   └── src/
│       ├── views/     ← 6 个页面
│       ├── components/← 9 个组件
│       ├── api/       ← axios 封装
│       ├── router/    ← vue-router 配置
│       └── types/     ← TypeScript 类型
├── tests/             ← ~70 个测试文件
├── storage/           ← SQLite DB + browser profile + cookies
├── main.py            ← CLI 入口 (main / start_api)
└── pyproject.toml     ← Python 依赖 (FastAPI, SQLAlchemy, Playwright, APScheduler...)
```

## 附录 B: 数据库层要点

| 项目 | 详情 |
|------|------|
| 引擎 | SQLite + aiosqlite (async) |
| WAL 模式 | ✅ 已启用 (`PRAGMA journal_mode=WAL`) |
| 外键 | ✅ 已启用 (`PRAGMA foreign_keys=ON`) |
| Session 获取 | `get_async_session_factory()` 返回 `async_sessionmaker[AsyncSession]` |
| Repository 模式 | 每个模型有对应 Repository (如 `ProductRepository`, `ReportRepository`) |
| 同步支持 | `get_session_factory()` 提供同步 session (少量旧端点使用) |
