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


if __name__ == "__main__":
    main()
