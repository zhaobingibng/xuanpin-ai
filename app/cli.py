"""XuanPin AI — CLI tool for batch product analysis.

Usage::

    # Full pipeline: crawl → clean → score → rank
    uv run python -m app.cli run -k 防晒霜 -p xiaohongshu douyin

    # Demo mode (sample data, no crawling)
    uv run python -m app.cli demo

    # Score a single product
    uv run python -m app.cli score --sales 5000 --viewers 10000 --price 99.9

    # Full pipeline + save to database
    uv run python -m app.cli run -k 蓝牙耳机 -p xiaohongshu --save
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.ai.analyzer import ProductAnalyzer
from app.ai.scorer import ProductScorer
from app.crawler import CrawlerManager, DouyinCrawler, KuaishouCrawler, XiaohongshuCrawler
from app.crawler.models.schemas import RawProduct
from app.services.cleaner.pipeline import CleanedProduct, ProductCleanPipeline

console = Console(legacy_windows=False)

# ── Platform → Crawler mapping ────────────────────────────────

PLATFORM_CRAWLERS = {
    "xiaohongshu": XiaohongshuCrawler,
    "douyin": DouyinCrawler,
    "kuaishou": KuaishouCrawler,
}


# ── Display helpers ───────────────────────────────────────────


def _score_color(score: float) -> str:
    """Return rich color name based on score."""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    if score >= 40:
        return "bright_yellow"
    return "red"


def _truncate(text: str, max_len: int = 30) -> str:
    """Truncate text with ellipsis."""
    return text[:max_len] + "…" if len(text) > max_len else text


def display_results(ranked: list[dict], title: str = "爆款排行榜") -> None:
    """Display ranked products in a rich table."""
    table = Table(title=title, show_lines=True)

    table.add_column("#", style="bold", width=4, justify="right")
    table.add_column("商品名称", style="white", max_width=32)
    table.add_column("平台", style="cyan", width=12)
    table.add_column("店铺", style="magenta", width=14)
    table.add_column("价格", style="green", width=8, justify="right")
    table.add_column("销量", style="blue", width=8, justify="right")
    table.add_column("浏览", style="blue", width=8, justify="right")
    table.add_column("分类", style="yellow", width=6)
    table.add_column("AI评分", style="bold", width=8, justify="right")

    for i, item in enumerate(ranked, 1):
        p: CleanedProduct = item["product"]
        score = item["ai_score"]
        color = _score_color(score)

        table.add_row(
            str(i),
            _truncate(p.name),
            p.platform,
            _truncate(p.shop, 14),
            f"￥{p.price:.1f}",
            str(p.sales_24h),
            str(p.viewers),
            p.category,
            f"[{color}]{score:.1f}[/{color}]",
        )

    console.print(table)


def display_summary(stats: dict) -> None:
    """Display summary statistics."""
    dist = stats["score_distribution"]
    panel_text = (
        f"商品总数: {stats['count']}\n"
        f"平均分:   [bold]{stats['avg_score']:.1f}[/bold]\n"
        f"最高分:   [green]{stats['max_score']:.1f}[/green]\n"
        f"最低分:   [red]{stats['min_score']:.1f}[/red]\n"
        f"\n"
        f"分数分布:\n"
        f"  80-100 (爆款): {dist.get('80-100', 0)}\n"
        f"  60-80  (潜力): {dist.get('60-80', 0)}\n"
        f"  40-60  (一般): {dist.get('40-60', 0)}\n"
        f"  20-40  (偏低): {dist.get('20-40', 0)}\n"
        f"  0-20   (冷门): {dist.get('0-20', 0)}"
    )
    console.print(Panel(panel_text, title="分析摘要", border_style="blue"))


# ── Demo data ─────────────────────────────────────────────────


def _demo_products() -> list[RawProduct]:
    """Generate sample data for demo mode."""
    return [
        RawProduct(name="🔥爆款蓝牙耳机降噪无线运动", platform="xiaohongshu", shop="数码旗舰店", price=99.9, viewers=52000, sales_24h=12000),
        RawProduct(name="秒杀手机壳iPhone15防摔", platform="xiaohongshu", shop="手机配件城", price=19.9, viewers=8000, sales_24h=3500),
        RawProduct(name="新款充电宝20000毫安快充", platform="douyin", shop="移动电源专卖", price=129.0, viewers=35000, sales_24h=8000),
        RawProduct(name="包邮保温水杯500ml不锈钢", platform="kuaishou", shop="家居生活馆", price=49.9, viewers=15000, sales_24h=6000),
        RawProduct(name="机械键盘青轴87键RGB", platform="douyin", shop="外设天堂", price=259.0, viewers=28000, sales_24h=4500),
        RawProduct(name="清仓竹凉席1.8米双人", platform="xiaohongshu", shop="夏日家居", price=89.0, viewers=3000, sales_24h=800),
        RawProduct(name="运动鞋男透气跑步鞋轻便", platform="kuaishou", shop="运动装备库", price=199.0, viewers=22000, sales_24h=5500),
        RawProduct(name="抽纸巾大包装家庭装30包", platform="kuaishou", shop="日用百货", price=29.9, viewers=45000, sales_24h=15000),
        RawProduct(name="高端真皮斜挎包男士", platform="xiaohongshu", shop="皮具工坊", price=459.0, viewers=6000, sales_24h=200),
        RawProduct(name="收纳盒桌面整理多层", platform="douyin", shop="整理达人", price=39.9, viewers=18000, sales_24h=7000),
        RawProduct(name="无线耳机保护套卡通", platform="xiaohongshu", shop="手机配件城", price=9.9, viewers=2000, sales_24h=150),
        RawProduct(name="夏季防晒衣女薄款透气", platform="douyin", shop="时尚女装", price=79.0, viewers=40000, sales_24h=9500),
    ]


# ── Commands ──────────────────────────────────────────────────


async def cmd_run(args: argparse.Namespace) -> None:
    """Full pipeline: crawl → clean → score → rank → (optionally) save."""
    keyword = args.keyword
    platforms = args.platforms or ["xiaohongshu", "douyin", "kuaishou"]
    max_pages = args.pages

    console.print(f"\n[bold blue]XuanPin AI[/] — 搜索: [cyan]{keyword}[/] | 平台: {', '.join(platforms)}\n")

    # Step 1: Crawl
    console.print("[bold]Step 1/4:[/] 采集商品数据…")
    manager = CrawlerManager()
    for platform in platforms:
        cls = PLATFORM_CRAWLERS.get(platform)
        if cls:
            manager.register(cls())

    all_raw: list[RawProduct] = []
    for platform in platforms:
        products = await manager.crawl(platform, keyword=keyword, max_pages=max_pages)
        all_raw.extend(products)
        console.print(f"  [{platform}] 采集到 {len(products)} 个商品")

    if not all_raw:
        console.print("[yellow]未采集到数据，请检查关键词或登录状态[/]")
        await manager.close_all()
        return

    # Step 2: Clean
    console.print(f"\n[bold]Step 2/4:[/] 清洗 {len(all_raw)} 个商品…")
    pipeline = ProductCleanPipeline()
    cleaned = pipeline.process_batch(all_raw)
    console.print(f"  清洗后保留 {len(cleaned)}/{len(all_raw)} 个商品")

    # Step 3: Score + Rank
    console.print("\n[bold]Step 3/4:[/] AI 评分…")
    analyzer = ProductAnalyzer()
    ranked = analyzer.rank(cleaned)

    # Step 4: Display
    console.print("\n[bold]Step 4/4:[/] 展示结果\n")
    display_results(ranked, title=f"「{keyword}」爆款排行榜")
    stats = analyzer.summary(cleaned)
    display_summary(stats)

    # Optional: Save to DB
    if args.save:
        console.print("\n[bold]保存入库…[/]")
        from app.database.base import get_async_session_factory
        from app.services.product_service import ProductService

        engine_factory = get_async_session_factory()
        async with engine_factory() as session:
            saved = await manager.save_to_db(
                [RawProduct(**{k: v for k, v in vars(r["product"]).items() if k != "category"}) for r in ranked],
                session,
            )
        console.print(f"[green]已保存 {saved} 个商品到数据库[/]")

    await manager.close_all()


async def cmd_demo(args: argparse.Namespace) -> None:
    """Demo mode: analyze sample data without crawling."""
    console.print("\n[bold blue]XuanPin AI[/] — Demo 模式（示例数据）\n")

    raw_products = _demo_products()
    console.print(f"[bold]Step 1/3:[/] 加载 {len(raw_products)} 个示例商品…")

    # Clean
    console.print("[bold]Step 2/3:[/] 清洗 + 标准化…")
    pipeline = ProductCleanPipeline()
    cleaned = pipeline.process_batch(raw_products)
    console.print(f"  清洗后: {len(cleaned)}/{len(raw_products)} 个商品")

    # Score + Rank
    console.print("[bold]Step 3/3:[/] AI 评分 + 排名\n")
    analyzer = ProductAnalyzer()
    ranked = analyzer.rank(cleaned)

    display_results(ranked, title="Demo 爆款排行榜")
    stats = analyzer.summary(cleaned)
    display_summary(stats)


async def cmd_score(args: argparse.Namespace) -> None:
    """Score a single product from CLI args."""
    scorer = ProductScorer()
    breakdown = scorer.breakdown(
        sales_24h=args.sales,
        viewers=args.viewers,
        price=args.price,
    )

    console.print(f"\n[bold blue]XuanPin AI[/] — 单品评分\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("维度", style="white")
    table.add_column("原始值", style="cyan")
    table.add_column("得分", style="bold")

    table.add_row("销量 (40%)", str(args.sales), f"{breakdown['sales']:.1f}")
    table.add_row("浏览 (35%)", str(args.viewers), f"{breakdown['viewers']:.1f}")
    table.add_row("价格 (25%)", f"￥{args.price:.2f}", f"{breakdown['price']:.1f}")
    table.add_row("", "", "")

    color = _score_color(breakdown["total"])
    table.add_row("[bold]综合评分[/]", "", f"[bold {color}]{breakdown['total']:.1f}[/]")

    console.print(table)
    console.print()


async def cmd_daily(args: argparse.Namespace) -> None:
    """一键执行今日选品全流程。

    串联：采集 → AI评分 → 推荐池 → 供应商匹配 → 自动发布 → 日报生成。
    全部复用已有模块，无新增抽象。
    """
    from datetime import date as dt_date
    from datetime import datetime

    from app.database.base import get_async_session_factory
    from app.models.recommendation_status import PoolStatus
    from app.services.product_service import ProductService
    from app.services.recommendation.daily_recommendation import (
        DailyRecommendationService,
    )
    from app.services.recommendation.pool_initializer import (
        RecommendationPoolInitializer,
    )
    from app.services.recommendation.pool_service import (
        RecommendationPoolService,
    )
    from app.services.recommendation.publish_service import (
        RecommendationPublishService,
    )
    from app.services.selection.daily_selection_pipeline import (
        DailySelectionPipeline,
    )
    from app.tasks.crawler_jobs import crawl_all_platforms
    from app.tasks.daily_selection_task import save_result_to_storage

    start = datetime.now()
    session_factory = get_async_session_factory()

    STEPS = 7
    step_ok = [False] * (STEPS + 1)  # 1-based

    console.print("\n[bold blue]XuanPin AI[/] — 今日选品流程\n")

    # ────────────────────────────────────────────────────────────
    def _step_label(n: int, label: str) -> str:
        return f"[bold][{n}/{STEPS}][/] {label}"

    def _mark(n: int, ok: bool) -> str:
        return "[green]✅[/]" if ok else "[red]❌[/]"

    # ════════════════════════════════════════════════════════════
    # Step 1: 商品采集
    # ════════════════════════════════════════════════════════════
    collect_count = 0
    console.print(f"{_step_label(1, '商品采集')}…", end="")
    try:
        raw = await crawl_all_platforms()
        collect_count = len(raw)
        step_ok[1] = True
        console.print(f"\r{_step_label(1, '商品采集')}  {_mark(1, True)} ({collect_count} 条)")
    except Exception as e:
        raw = []
        console.print(f"\r{_step_label(1, '商品采集')}  {_mark(1, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # Step 2: AI评分（清洗入库 + 评分排序 + 推荐写入）
    # ════════════════════════════════════════════════════════════
    recommend_items: list[dict] = []
    console.print(f"{_step_label(2, 'AI评分')}…", end="")
    try:
        async with session_factory() as session:
            # 2a: 新采集数据入库 + 评分写入
            if raw:
                save_result = await ProductService(session).save_raw_products(raw)
                from app.services.product_scoring import ProductScoringService
                scoring_svc = ProductScoringService()
                for product in save_result.get("saved_products", []):
                    score_record = scoring_svc.create_score_record(product)
                    product.ai_score = score_record.total_score
                    session.add(score_record)
                await session.commit()
                for product in save_result.get("saved_products", []):
                    await session.refresh(product)

            # 2b: 评分 + 排序 + 推荐
            report = await DailyRecommendationService(session).generate()
            recommend_items = report.get("items", []) or []
            rec_total = report.get("total", len(recommend_items))

        step_ok[2] = True
        console.print(f"\r{_step_label(2, 'AI评分')}  {_mark(2, True)} ({rec_total} 个)")
    except Exception as e:
        console.print(f"\r{_step_label(2, 'AI评分')}  {_mark(2, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # Step 3: 推荐池同步
    # ════════════════════════════════════════════════════════════
    pool_synced = 0
    console.print(f"{_step_label(3, '推荐池同步')}…", end="")
    try:
        if not recommend_items:
            console.print(f"\r{_step_label(3, '推荐池同步')}  {_mark(3, True)} (无推荐商品，跳过)")
            step_ok[3] = True
        else:
            async with session_factory() as session:
                today = dt_date.today()
                pool_ret = await RecommendationPoolInitializer(session).sync(today)
                pool_synced = pool_ret.get("synced", 0)
            step_ok[3] = True
            console.print(f"\r{_step_label(3, '推荐池同步')}  {_mark(3, True)} ({pool_synced} 个)")
    except Exception as e:
        console.print(f"\r{_step_label(3, '推荐池同步')}  {_mark(3, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # Step 4: 供应商匹配
    # ════════════════════════════════════════════════════════════
    pipeline_result: dict[str, object] = {"status": "error"}
    match_count = 0
    console.print(f"{_step_label(4, '供应商匹配')}…", end="")
    try:
        async with session_factory() as session:
            pipeline = DailySelectionPipeline()
            pipeline_result = await pipeline.run(
                session, limit=20, top_k=3, track=True,
            )
            s = pipeline_result.get("stats", {})
            match_count = s.get("matched_products", 0)
        step_ok[4] = True
        console.print(
            f"\r{_step_label(4, '供应商匹配')}  {_mark(4, True)} "
            f"(商品 {s.get('total_products', 0)}, 匹配 {match_count})",
        )
    except Exception as e:
        console.print(f"\r{_step_label(4, '供应商匹配')}  {_mark(4, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # Step 5: 自动发布
    # ════════════════════════════════════════════════════════════
    publish_ok = 0
    publish_fail = 0
    console.print(f"{_step_label(5, '自动发布')}…", end="")
    try:
        if not recommend_items:
            console.print(f"\r{_step_label(5, '自动发布')}  {_mark(5, True)} (无商品，跳过)")
            step_ok[5] = True
        else:
            publish_limit = 3  # 只发 Top3
            async with session_factory() as session:
                pool_svc = RecommendationPoolService(session)
                pub_svc = RecommendationPublishService(session)
                for item in recommend_items[:publish_limit]:
                    pid = item["product_id"]
                    try:
                        await pool_svc.update_status(pid, PoolStatus.APPROVED)
                        result = await pub_svc.publish(pid)
                        if result.get("success"):
                            publish_ok += 1
                        else:
                            publish_fail += 1
                    except Exception as e_inner:
                        publish_fail += 1
                        logger.warning("[auto-publish] {} 发布失败: {}", pid, e_inner)
            step_ok[5] = publish_ok > 0 or publish_fail == 0
            console.print(
                f"\r{_step_label(5, '自动发布')}  {_mark(5, step_ok[5])} "
                f"(成功 {publish_ok}, 失败 {publish_fail})",
            )
    except Exception as e:
        console.print(f"\r{_step_label(5, '自动发布')}  {_mark(5, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # Step 6: 日报生成
    # ════════════════════════════════════════════════════════════
    console.print(f"{_step_label(6, '日报生成')}…", end="")
    try:
        if pipeline_result.get("status") == "success":
            save_result_to_storage(pipeline_result)  # type: ignore[arg-type]
        step_ok[6] = True
        console.print(f"\r{_step_label(6, '日报生成')}  {_mark(6, True)}")
    except Exception as e:
        console.print(f"\r{_step_label(6, '日报生成')}  {_mark(6, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # Step 7: 店铺监控扫描
    # ════════════════════════════════════════════════════════════
    shop_new_total = 0
    shop_results_list: list[tuple[str, int]] = []
    console.print(f"{_step_label(7, '店铺扫描')}…", end="")
    try:
        from app.crawler.taobao import TaobaoCrawler
        from app.services.shop_service import ShopService
        from app.services.discovery.new_product_detector import NewProductDetector

        async with session_factory() as session:
            svc = ShopService(session)
            shops = await svc.list_enabled_shops(platform="taobao")
            if shops:
                crawler = TaobaoCrawler()
                for shop in shops:
                    if not shop.shop_url:
                        continue
                    prods = await crawler.crawl_shop(
                        shop_url=shop.shop_url,
                        shop_name=shop.shop_name,
                        max_pages=2,
                        limit=30,
                    )
                    if prods:
                        await ProductService(session).save_raw_products(prods)
                    detector = NewProductDetector(session)
                    result = await detector.detect_shop_new_products(shop.id)
                    shop_new_total += result["new_count"]
                    if result["new_count"] > 0:
                        shop_results_list.append((shop.shop_name, result["new_count"]))
                await crawler.close()
            step_ok[7] = True
            detail = f"{len(shops)} 个店铺"
            if shop_new_total > 0:
                detail += f", 新增 {shop_new_total}"
            console.print(f"\r{_step_label(7, '店铺扫描')}  {_mark(7, True)} ({detail})")
    except Exception as e:
        console.print(f"\r{_step_label(7, '店铺扫描')}  {_mark(7, False)} — {e}")

    # ════════════════════════════════════════════════════════════
    # 总耗时
    # ════════════════════════════════════════════════════════════
    duration = (datetime.now() - start).total_seconds()

    all_ok = all(step_ok[1:])
    status_line = (
        "[bold green]✅ 今日任务完成[/]" if all_ok
        else "[bold yellow]⚠️ 部分步骤失败[/]"
    )

    console.print()
    console.print(f"─" * 40)
    console.print(status_line)
    console.print()
    console.print(f"  采集: {collect_count}")
    console.print(f"  推荐: {len(recommend_items)}")
    console.print(f"  发布: {publish_ok}")
    console.print(f"  店铺: {len(shop_results_list)} 个有新品")
    for name, count in shop_results_list:
        console.print(f"    {name}: 新增 {count}")
    console.print(f"  耗时: {duration:.0f} 秒")

    # ════════════════════════════════════════════════════════════
    # 关注商品变化监控（只读分析，不修改数据）
    # ════════════════════════════════════════════════════════════
    watching_changes: list[dict[str, object]] = []
    try:
        async with session_factory() as session:
            from app.database.history_repository import HistoryRepository
            from app.models.product import Product
            from sqlalchemy import select

            stmt = select(Product).where(Product.lifecycle_stage == "WATCHING")
            result = await session.execute(stmt)
            watching_products = result.scalars().all()

            if watching_products:
                for product in watching_products:
                    history_repo = HistoryRepository(session)
                    history = list(await history_repo.get_history(product.id, limit=2))
                    if len(history) < 2:
                        continue

                    latest, previous = history[0], history[1]

                    price_pct = (latest.price - previous.price) / previous.price * 100 if previous.price else 0.0
                    sales_pct = (latest.sales_24h - previous.sales_24h) / previous.sales_24h * 100 if previous.sales_24h else 0.0
                    viewers_pct = (latest.viewers - previous.viewers) / previous.viewers * 100 if previous.viewers else 0.0

                    watching_changes.append({
                        "name": product.name,
                        "shop": product.shop,
                        "price_old": previous.price,
                        "price_new": latest.price,
                        "price_pct": price_pct,
                        "sales_old": previous.sales_24h,
                        "sales_new": latest.sales_24h,
                        "sales_pct": sales_pct,
                        "viewers_old": previous.viewers,
                        "viewers_new": latest.viewers,
                        "viewers_pct": viewers_pct,
                    })
    except Exception as e:
        logger.warning("[watching] 商品池监控失败: {}", e)

    if watching_changes:
        console.print()
        console.print("━" * 40)
        console.print("[bold]商品池变化[/]")
        for wc in watching_changes:
            trend = "上涨 📈" if wc["sales_pct"] > 0 else "下降 📉"
            console.print(f"\n  [bold]{wc['name']}[/]")
            console.print(f"  店铺: {wc['shop']}")
            console.print(f"  销量: {wc['sales_old']} → {wc['sales_new']} ({wc['sales_pct']:+g}%)")
            console.print(f"  价格: ￥{wc['price_old']:.0f} → ￥{wc['price_new']:.0f} ({wc['price_pct']:+g}%)")
            console.print(f"  浏览: {wc['viewers_old']} → {wc['viewers_new']} ({wc['viewers_pct']:+g}%)")
            console.print(f"  趋势: {trend}")
        console.print()

    # ════════════════════════════════════════════════════════════
    # 商品资产汇总
    # ════════════════════════════════════════════════════════════
    try:
        from sqlalchemy import func as sa_func
        from app.models.product import Product
        from app.models.supplier_match import SupplierMatch
        from app.services.shop_service import ShopService

        async with session_factory() as session:
            # 累计商品
            total_stmt = select(sa_func.count(Product.id)).where(Product.status == "ACTIVE")
            total_products = (await session.execute(total_stmt)).scalar() or 0

            # 今日新增
            from datetime import datetime as dt_dt
            today_start = dt_dt.now().replace(hour=0, minute=0, second=0, microsecond=0)
            new_today = (
                await session.execute(
                    select(sa_func.count(Product.id)).where(Product.first_seen_time >= today_start)
                )
            ).scalar() or 0

            # 关注商品
            watching_count = (
                await session.execute(
                    select(sa_func.count(Product.id)).where(Product.lifecycle_stage == "WATCHING")
                )
            ).scalar() or 0

            # 新增重点商品（今日发现且评分 >= 75）
            new_key_today = (
                await session.execute(
                    select(sa_func.count(Product.id)).where(
                        Product.first_seen_time >= today_start,
                        Product.ai_score >= 75,
                    )
                )
            ).scalar() or 0

            # 高分商品（累计评分 >= 75）
            high_score_total = (
                await session.execute(
                    select(sa_func.count(Product.id)).where(
                        Product.status == "ACTIVE",
                        Product.ai_score >= 75,
                    )
                )
            ).scalar() or 0

            # 供应链匹配
            match_count = (
                await session.execute(select(sa_func.count(SupplierMatch.id)))
            ).scalar() or 0

            # 累计店铺
            shop_svc = ShopService(session)
            shops = await shop_svc.list_enabled_shops()
            total_shops = len(shops)

        console.print()
        console.print("=" * 24)
        console.print("[bold]今日商品资产[/]")
        console.print()
        console.print(f"今日采集：{collect_count}")
        console.print(f"新增商品：{new_today}")
        console.print(f"累计商品：{total_products}")
        console.print(f"高分商品：{high_score_total}")
        console.print(f"新增重点商品：{new_key_today}")
        console.print(f"累计关注商品：{watching_count}")
        console.print(f"累计店铺：{total_shops}")
        console.print(f"供应链匹配：{match_count}")
        console.print()
        console.print("=" * 24)
    except Exception as e:
        logger.warning("[asset] 商品资产汇总失败: {}", e)

    if not all_ok:
        console.print()
        console.print("[yellow]失败步骤:[/]")
        for i in range(1, STEPS + 1):
            labels = ["", "商品采集", "AI评分", "推荐池同步", "供应商匹配", "自动发布", "日报生成", "店铺扫描"]
            if not step_ok[i]:
                console.print(f"  [{i}/{STEPS}] {labels[i]}")


# ── Shop commands ──────────────────────────────────────────────


async def cmd_shop(args: argparse.Namespace) -> None:
    """管理监控店铺。"""
    from app.database.base import get_async_session_factory
    from app.services.shop_service import ShopService

    factory = get_async_session_factory()

    if args.shop_action == "list":
        async with factory() as session:
            svc = ShopService(session)
            shops = await svc.list_enabled_shops()
            if not shops:
                console.print("[yellow]暂无监控店铺[/]")
                return
            table = Table(title="监控店铺列表")
            table.add_column("ID", style="bold")
            table.add_column("店铺名称", style="white")
            table.add_column("平台", style="cyan")
            table.add_column("优先级", style="yellow")
            table.add_column("状态", style="green")
            for s in shops:
                status = "✅" if s.enabled else "⏸"
                table.add_row(str(s.id), s.shop_name, s.platform, str(s.priority), status)
            console.print(table)

    elif args.shop_action == "add":
        if not args.name or not args.url:
            console.print("[red]请提供 --name 和 --url[/]")
            return
        import hashlib
        shop_id = hashlib.md5(args.url.encode()).hexdigest()[:16]
        async with factory() as session:
            svc = ShopService(session)
            shop = await svc.create_shop(
                platform=args.platform or "taobao",
                shop_id=shop_id,
                shop_name=args.name,
                shop_url=args.url,
                priority=args.priority or 1,
            )
        console.print(f"[green]已添加店铺: {shop.shop_name} (ID={shop.id})[/]")

    elif args.shop_action == "remove":
        if not args.shop_id:
            console.print("[red]请提供店铺 ID[/]")
            return
        async with factory() as session:
            svc = ShopService(session)
            ok = await svc.delete_shop(args.shop_id)
        if ok:
            console.print(f"[green]已删除店铺 ID={args.shop_id}[/]")
        else:
            console.print(f"[red]店铺 ID={args.shop_id} 不存在[/]")

    elif args.shop_action == "scan":
        from app.crawler.taobao import TaobaoCrawler
        from app.services.product_service import ProductService
        from app.services.discovery.new_product_detector import NewProductDetector

        async with factory() as session:
            svc = ShopService(session)
            shops = await svc.list_enabled_shops(platform="taobao")
            if not shops:
                console.print("[yellow]无监控店铺[/]")
                return
            crawler = TaobaoCrawler()
            total_new = 0
            for shop in shops:
                if not shop.shop_url:
                    console.print(f"  [yellow]⏭ {shop.shop_name}: 无 shop_url[/]")
                    continue
                console.print(f"  {shop.shop_name}…", end="")
                products = await crawler.crawl_shop(
                    shop_url=shop.shop_url,
                    shop_name=shop.shop_name,
                    max_pages=2,
                    limit=30,
                )
                if products:
                    await ProductService(session).save_raw_products(products)
                detector = NewProductDetector(session)
                result = await detector.detect_shop_new_products(shop.id)
                console.print(f"\r  {shop.shop_name}: {result['new_count']} 个新品")
                total_new += result["new_count"]
            await crawler.close()
            console.print(f"[green]扫描完成，共 {total_new} 个新品[/]")


# ── Product commands ──────────────────────────────────────────


async def cmd_product(args: argparse.Namespace) -> None:
    """管理商品。"""
    from app.database.base import get_async_session_factory
    from app.models.product import Product

    factory = get_async_session_factory()

    if args.product_action == "watch":
        async with factory() as session:
            product = await session.get(Product, args.product_id)
            if not product:
                console.print(f"[red]商品 ID={args.product_id} 不存在[/]")
                return
            product.lifecycle_stage = "WATCHING"
            await session.commit()
            console.print(f"[green]已关注商品: {product.name} (ID={product.id})[/]")


# ── Entry point ───────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xuanpin",
        description="XuanPin AI — 爆款商品分析工具",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run
    run_parser = subparsers.add_parser("run", help="全流程: 采集→清洗→评分→排名")
    run_parser.add_argument("-k", "--keyword", required=True, help="搜索关键词")
    run_parser.add_argument("-p", "--platforms", nargs="+", help="平台 (xiaohongshu/douyin/kuaishou)")
    run_parser.add_argument("-n", "--pages", type=int, default=3, help="每平台最大页数")
    run_parser.add_argument("--save", action="store_true", help="结果保存到数据库")

    # demo
    subparsers.add_parser("demo", help="Demo: 示例数据分析")

    # score
    score_parser = subparsers.add_parser("score", help="单品评分")
    score_parser.add_argument("--sales", type=int, default=0, help="24h销量")
    score_parser.add_argument("--viewers", type=int, default=0, help="浏览人数")
    score_parser.add_argument("--price", type=float, default=0.0, help="价格")

    # daily
    subparsers.add_parser("daily", help="一键执行今日选品流程（采集→入库→推荐→匹配→日报）")

    # shop
    shop_parser = subparsers.add_parser("shop", help="店铺管理")
    shop_sub = shop_parser.add_subparsers(dest="shop_action", help="店铺操作")

    shop_list = shop_sub.add_parser("list", help="列出监控店铺")

    shop_add = shop_sub.add_parser("add", help="添加监控店铺")
    shop_add.add_argument("--name", required=True, help="店铺名称")
    shop_add.add_argument("--url", required=True, help="店铺链接")
    shop_add.add_argument("--platform", default="taobao", help="平台")
    shop_add.add_argument("--priority", type=int, default=1, help="优先级 1-3")

    shop_remove = shop_sub.add_parser("remove", help="删除监控店铺")
    shop_remove.add_argument("shop_id", type=int, help="店铺 ID")

    shop_sub.add_parser("scan", help="扫描所有监控店铺新品")

    # product
    product_parser = subparsers.add_parser("product", help="商品管理")
    product_sub = product_parser.add_subparsers(dest="product_action", help="商品操作")
    product_watch = product_sub.add_parser("watch", help="关注商品")
    product_watch.add_argument("product_id", type=int, help="商品 ID")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Suppress loguru output in CLI mode (use rich console instead)
    logger.disable("app")

    if args.command == "demo":
        asyncio.run(cmd_demo(args))
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "score":
        asyncio.run(cmd_score(args))
    elif args.command == "daily":
        asyncio.run(cmd_daily(args))
    elif args.command == "shop":
        asyncio.run(cmd_shop(args))
    elif args.command == "product":
        asyncio.run(cmd_product(args))


if __name__ == "__main__":
    main()
