"""DailySelectionPipeline — 自动选品流水线编排层 (Phase 37.1).

将已有模块串联为一条完整的每日选品流程，本层**只负责编排**，
不重复实现、不修改任何核心业务逻辑：

    1. 获取候选商品      ← ProductService.list_all()
    2. 供应链匹配        ← SupplierMatchingService.match_products_with_matcher()
    3. 机会评分          ← OpportunityScorer.calculate()
    4. 生成选品日报      ← DailySelectionReportGenerator.generate()
    5. AI 分析（可选）   ← DailySelectionAnalyzer.analyze()
    6. 记录执行结果      ← TaskExecutionRepository (RUNNING → SUCCESS/FAILED)
    7. 返回结构化报告

设计原则：
    - **依赖注入**：所有下游 service 均可注入，内部不硬编码具体实例。
      未注入时才按需以传入的 session 构造默认实现。
    - **无状态**：单次 ``run()`` 的全部中间数据均为局部变量，
      实例不在多次运行间累积任何状态，可安全复用/并发。
    - **异步**：``run()`` 为 async，编排异步 service 调用。
    - **健壮**：单商品匹配异常被隔离（跳过并计数），
      致命阶段（取商品 / 生成报告）异常返回明确的 error 结构，
      并将 TaskExecution 标记为 FAILED。
    - **无侵入**：不改动任何现有 service / 模型。
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from app.services.opportunity.scorer import OpportunityScorer
from app.services.report.daily_selection_report_generator import (
    DailySelectionReportGenerator,
)


# ── 常量 ────────────────────────────────────────────────────────

TASK_NAME = "daily_selection_pipeline"

# 候选商品拉取上限（防止一次性拉爆内存）
DEFAULT_CANDIDATE_LIMIT = 1000


class DailySelectionPipeline:
    """自动选品流水线编排器。

    Usage::

        # 默认实现（生产环境）
        pipeline = DailySelectionPipeline()
        result = await pipeline.run(session, limit=20, top_k=3)

        # 依赖注入（测试 / 定制）
        pipeline = DailySelectionPipeline(
            product_service=my_product_service,
            matching_service=my_matching_service,
            scorer=my_scorer,
            report_generator=my_generator,
            task_repo=my_task_repo,
            ai_analyzer=my_ai_analyzer,       # optional
        )
        result = await pipeline.run(session)

    返回结构（成功）::

        {
            "status": "success",
            "task": "daily_selection_pipeline",
            "report": {...},              # DailySelectionReportGenerator 输出
            "stats": {
                "total_products": int,
                "matched_products": int,
                "total_matches": int,
                "match_errors": int,
                "duration": float,
            },
            "task_execution_id": int | None,
        }

    返回结构（失败）::

        {
            "status": "error",
            "task": "daily_selection_pipeline",
            "stage": "acquire" | "report" | "pipeline",
            "error": "...",
            "report": None,
            "stats": {...},
            "task_execution_id": int | None,
        }
    """

    TASK_NAME = TASK_NAME

    def __init__(
        self,
        *,
        product_service: Any = None,
        matching_service: Any = None,
        scorer: OpportunityScorer | None = None,
        report_generator: DailySelectionReportGenerator | None = None,
        task_repo: Any = None,
        ai_analyzer: Any = None,
    ) -> None:
        """初始化编排器。

        Args:
            product_service: 提供 ``async list_all(...)`` 的商品服务。
                None → 运行时以 session 构造 ``ProductService``。
            matching_service: 提供
                ``async match_products_with_matcher(session, product, top_k)``
                的匹配服务。None → 运行时构造 ``SupplierMatchingService``。
            scorer: OpportunityScorer 实例（无需 session）。None → 默认实例。
            report_generator: DailySelectionReportGenerator 实例（无需 session）。
                None → 默认实例。
            task_repo: 提供 ``async create(record)`` / ``async finish(...)``
                的执行记录仓库。None → 运行时以 session 构造
                ``TaskExecutionRepository``。
            ai_analyzer: 提供 ``async analyze(report: dict) -> dict``
                的 AI 分析器（如 DailySelectionAnalyzer）。None → 跳过 AI 分析。
                AI 异常自动降级，不影响日报生成。
        """
        # 无 session 依赖的组件可直接持有默认实例（无状态、可复用）。
        self._scorer = scorer or OpportunityScorer()
        self._report_generator = report_generator or DailySelectionReportGenerator()
        self._ai_analyzer = ai_analyzer

        # 有 session 依赖的组件保存注入值；None 时在 run() 内按需构造。
        self._product_service = product_service
        self._matching_service = matching_service
        self._task_repo = task_repo

    # ── Public API ──────────────────────────────────────────────

    async def run(
        self,
        session: Any,
        *,
        limit: int = 20,
        top_k: int = 3,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
        track: bool = True,
    ) -> dict[str, Any]:
        """执行一次完整的自动选品流水线。

        Args:
            session: 异步数据库会话，透传给下游 session-依赖 service。
            limit: 日报中 TOP 商品数量上限。
            top_k: 每个商品匹配的供应商数量。
            candidate_limit: 候选商品拉取上限。
            track: 是否记录 TaskExecution（生产 True；纯单测可 False）。

        Returns:
            结构化结果 dict（见类文档）。异常不外抛，均转为 error 结构。
        """
        started = time.monotonic()
        stats: dict[str, Any] = {
            "total_products": 0,
            "matched_products": 0,
            "total_matches": 0,
            "match_errors": 0,
            "duration": 0.0,
        }

        # ── 开始执行记录 ────────────────────────────────────────
        record_id = await self._start_tracking(session) if track else None

        try:
            # ── 1. 获取候选商品 ────────────────────────────────
            try:
                product_service = self._product_service or self._build_product_service(session)
                products = list(await product_service.list_all(limit=candidate_limit))
            except Exception as e:  # noqa: BLE001 — 致命阶段，转 error 结构
                logger.error("[SelectionPipeline] 获取候选商品失败: {}", e)
                return await self._fail(
                    session, record_id, started, stats, stage="acquire", error=e,
                )

            stats["total_products"] = len(products)

            # 空商品：直接产出空日报（成功语义）。
            if not products:
                logger.info("[SelectionPipeline] 无候选商品，生成空日报")
                report = self._report_generator.generate([], [], [], limit=limit)
                return await self._succeed(
                    session, record_id, started, stats, report,
                )

            # ── 2-3. 逐商品：供应链匹配 + 机会评分 ─────────────
            matching_service = self._matching_service or self._build_matching_service()

            product_dicts: list[dict[str, Any]] = []
            match_dicts: list[dict[str, Any]] = []
            score_dicts: list[dict[str, Any]] = []

            for product in products:
                pid = self._get_product_id(product)
                product_dicts.append(self._product_to_dict(product))

                # 单商品匹配异常隔离：跳过该商品匹配，流程继续。
                try:
                    raw_matches = await matching_service.match_products_with_matcher(
                        session, product, top_k=top_k,
                    )
                    raw_matches = list(raw_matches or [])
                except Exception as e:  # noqa: BLE001 — 单点容错
                    stats["match_errors"] += 1
                    logger.warning(
                        "[SelectionPipeline] 商品匹配异常 product_id={}: {}", pid, e,
                    )
                    raw_matches = []

                pid_matches = [self._match_to_dict(pid, m) for m in raw_matches]
                if pid_matches:
                    stats["matched_products"] += 1
                    stats["total_matches"] += len(pid_matches)
                match_dicts.extend(pid_matches)

                # 机会评分（scorer 支持 ORM/dict 双输入）。
                score_result = self._scorer.calculate(product, pid_matches)
                score_dicts.append({
                    "product_id": pid,
                    "score": score_result["score"],
                })

            # ── 4. 生成选品日报 ────────────────────────────────
            try:
                report = self._report_generator.generate(
                    product_dicts, match_dicts, score_dicts, limit=limit,
                )
            except Exception as e:  # noqa: BLE001 — 致命阶段
                logger.error("[SelectionPipeline] 生成日报失败: {}", e)
                return await self._fail(
                    session, record_id, started, stats, stage="report", error=e,
                )

            # ── 5. AI 分析（可选，自动降级）───────────────────
            await self._run_ai_analysis(report)

            # ── 6. 记录成功 + 返回 ───────────────────────────
            return await self._succeed(session, record_id, started, stats, report)

        except Exception as e:  # noqa: BLE001 — 兜底，绝不外抛
            logger.exception("[SelectionPipeline] 未预期异常: {}", e)
            return await self._fail(
                session, record_id, started, stats, stage="pipeline", error=e,
            )

    # ── AI 分析 ───────────────────────────────────────────────

    async def _run_ai_analysis(self, report: dict[str, Any]) -> None:
        """对报告执行 AI 分析（可选步骤）。

        AI 分析器存在且可用时调用 ``ai_analyzer.analyze(report)``，
        将结果写入 ``report["ai_insights"]``。

        任何异常均自动降级：记录警告日志，将降级标记写入 report，
        不阻断主流程，日报正常返回。
        """
        if self._ai_analyzer is None:
            return

        try:
            ai_insights = await self._ai_analyzer.analyze(report)
            report["ai_insights"] = ai_insights
            logger.info(
                "[SelectionPipeline] AI 分析完成: available={}",
                ai_insights.get("ai_available", False),
            )
        except Exception as e:  # noqa: BLE001 — AI 失败只告警，不阻断
            logger.warning("[SelectionPipeline] AI 分析失败（自动降级）: {}", e)
            report["ai_insights"] = {
                "ai_available": False,
                "error": f"{type(e).__name__}: {e}",
            }

    # ── 执行记录（TaskExecution）────────────────────────────────

    async def _start_tracking(self, session: Any) -> int | None:
        """创建 RUNNING 执行记录，返回 record id（失败返回 None，不阻断主流程）。"""
        try:
            from app.models.task_execution import TaskExecution

            repo = self._task_repo or self._build_task_repo(session)
            record = TaskExecution(task_name=self.TASK_NAME, status="RUNNING")
            created = await repo.create(record)
            await self._maybe_commit(session)
            return getattr(created, "id", None)
        except Exception as e:  # noqa: BLE001 — 记录失败不影响业务
            logger.warning("[SelectionPipeline] 记录任务开始失败: {}", e)
            return None

    async def _finish_tracking(
        self,
        session: Any,
        record_id: int | None,
        *,
        status: str,
        duration: float,
        error: str | None = None,
    ) -> None:
        """更新执行记录为终态（失败仅告警，不阻断返回）。"""
        if record_id is None:
            return
        try:
            repo = self._task_repo or self._build_task_repo(session)
            await repo.finish(
                record_id, status=status, duration=duration, error=error,
            )
            await self._maybe_commit(session)
        except Exception as e:  # noqa: BLE001
            logger.warning("[SelectionPipeline] 记录任务结束失败: {}", e)

    # ── 结果构造 ────────────────────────────────────────────────

    async def _succeed(
        self,
        session: Any,
        record_id: int | None,
        started: float,
        stats: dict[str, Any],
        report: dict[str, Any],
    ) -> dict[str, Any]:
        duration = round(time.monotonic() - started, 3)
        stats["duration"] = duration
        await self._finish_tracking(
            session, record_id, status="SUCCESS", duration=duration,
        )
        logger.info(
            "[SelectionPipeline] 完成: products={}, matched={}, matches={}, "
            "errors={}, duration={}s",
            stats["total_products"], stats["matched_products"],
            stats["total_matches"], stats["match_errors"], duration,
        )
        return {
            "status": "success",
            "task": self.TASK_NAME,
            "report": report,
            "stats": stats,
            "task_execution_id": record_id,
        }

    async def _fail(
        self,
        session: Any,
        record_id: int | None,
        started: float,
        stats: dict[str, Any],
        *,
        stage: str,
        error: Exception,
    ) -> dict[str, Any]:
        duration = round(time.monotonic() - started, 3)
        stats["duration"] = duration
        error_msg = f"{type(error).__name__}: {error}"
        await self._finish_tracking(
            session, record_id, status="FAILED", duration=duration, error=error_msg,
        )
        return {
            "status": "error",
            "task": self.TASK_NAME,
            "stage": stage,
            "error": error_msg,
            "report": None,
            "stats": stats,
            "task_execution_id": record_id,
        }

    # ── 默认依赖构造（仅在未注入时调用）─────────────────────────

    @staticmethod
    def _build_product_service(session: Any) -> Any:
        from app.services.product_service import ProductService
        return ProductService(session)

    @staticmethod
    def _build_matching_service() -> Any:
        from app.services.supplier_matching import SupplierMatchingService
        return SupplierMatchingService()

    @staticmethod
    def _build_task_repo(session: Any) -> Any:
        from app.database.task_execution_repository import TaskExecutionRepository
        return TaskExecutionRepository(session)

    # ── 数据转换工具 ────────────────────────────────────────────

    @staticmethod
    async def _maybe_commit(session: Any) -> None:
        """尽力提交 session（若支持）。Mock session 亦安全。"""
        commit = getattr(session, "commit", None)
        if commit is None:
            return
        result = commit()
        if hasattr(result, "__await__"):
            await result

    @staticmethod
    def _get_product_id(product: Any) -> Any:
        if isinstance(product, dict):
            return product.get("product_id") or product.get("id")
        return getattr(product, "id", None)

    @staticmethod
    def _product_to_dict(product: Any) -> dict[str, Any]:
        """归一化商品为报告生成器所需 dict 结构。"""
        if isinstance(product, dict):
            d = dict(product)
            d.setdefault("product_id", d.get("id"))
            return d

        name = getattr(product, "name", "") or getattr(product, "title", "") or ""
        return {
            "product_id": getattr(product, "id", None),
            "title": name,
            "name": name,
            "price": getattr(product, "price", 0) or 0,
            "viewers": getattr(product, "viewers", 0) or 0,
            "sales_24h": getattr(product, "sales_24h", 0) or 0,
            "platform": getattr(product, "platform", None),
            "shop": getattr(product, "shop", None),
            "image": getattr(product, "image", None) or "",
        }

    @staticmethod
    def _match_to_dict(product_id: Any, match: Any) -> dict[str, Any]:
        """归一化匹配结果为下游所需 dict（similarity_score → final_score）。"""
        if isinstance(match, dict):
            d = dict(match)
            d.setdefault("product_id", product_id)
            if d.get("final_score") is None:
                d["final_score"] = d.get("similarity_score", 0) or 0
            return d

        final_score = (
            getattr(match, "final_score", None)
            if getattr(match, "final_score", None) is not None
            else getattr(match, "similarity_score", 0)
        )
        return {
            "product_id": product_id,
            "final_score": final_score or 0,
            "profit_margin": getattr(match, "profit_margin", 0) or 0,
            "supplier_title": getattr(match, "supplier_title", "") or "",
            "title": getattr(match, "supplier_title", "") or "",
            "supplier_price": getattr(match, "supplier_price", None),
            "supplier_product_id": getattr(match, "supplier_product_id", None),
            "supplier_url": getattr(match, "supplier_url", None),
            "estimated_profit": getattr(match, "estimated_profit", None),
        }
