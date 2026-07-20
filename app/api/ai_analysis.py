"""AI Analysis API endpoints — LLM-powered product analysis and report summary."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.ai.llm_client import get_llm_client
from app.database.base import get_async_session_factory
from app.database.product_repository import ProductRepository
from app.database.report_repository import ReportRepository
from app.models.product import Product
from app.services.ai_analysis.product_analyzer import LLMProductAnalyzer
from app.services.ai_analysis.report_summarizer import LLMReportSummarizer

router = APIRouter(prefix="/api/ai-analysis", tags=["ai-analysis"])


@router.get("/status")
async def llm_status() -> dict:
    """检查 LLM 可用性。"""
    client = get_llm_client()
    status = client.status()
    if not status["available"]:
        return {"available": False, "reason": "no_api_key"}
    return status


@router.post("/product/{product_id}")
async def analyze_product(product_id: int) -> dict:
    """使用 LLM 分析单个商品。"""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = ProductRepository(session)
        # 查询商品
        from sqlalchemy import select
        stmt = select(Product).where(Product.id == product_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()

        if product is None:
            raise HTTPException(status_code=404, detail="商品不存在")

        analyzer = LLMProductAnalyzer()
        analysis = await analyzer.analyze(product)

        if analysis is None:
            return {
                "error": "LLM 分析暂不可用",
                "fallback": True,
                "product_id": product_id,
                "product_name": product.name,
                "ai_score": product.ai_score,
            }

        return {
            "product_id": product_id,
            "product_name": product.name,
            "ai_score": product.ai_score,
            "llm_analysis": analysis,
        }


@router.post("/report/{report_id}/summary")
async def summarize_report(report_id: int) -> dict:
    """使用 LLM 生成每日报告摘要。"""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = ReportRepository(session)
        report = await repo.get_report_detail(report_id)

        if report is None:
            raise HTTPException(status_code=404, detail="报告不存在")

        summarizer = LLMReportSummarizer()
        summary = await summarizer.summarize(report)

        if summary is None:
            return {
                "error": "LLM 摘要生成暂不可用",
                "fallback": True,
                "report_id": report_id,
                "report_date": str(report.report_date),
                "total": report.total,
                "average_score": report.average_score,
            }

        return {
            "report_id": report_id,
            "report_date": str(report.report_date),
            "llm_summary": summary,
        }
