"""Phase 16.5 真实运行验证脚本。

运行完整 Pipeline 并收集统计数据：
1. 淘宝真实采集
2. 清洗 + 评分
3. 供应链匹配（Mock + 真实尝试）
4. 日报生成
5. 统计报告
"""

import asyncio
import json
from datetime import datetime

from loguru import logger


async def run_validation():
    """运行完整验证流程。"""
    from app.database.base import get_async_session_factory, get_async_engine, Base
    from app.crawler.taobao import TaobaoCrawler
    from app.crawler.models.schemas import RawProduct
    from app.services.cleaner.pipeline import ProductCleanPipeline
    from app.ai.analyzer import ProductAnalyzer
    from app.services.product_service import ProductService
    from app.services.supply_chain.matcher import SupplyChainMatcher
    from app.services.supply_chain.provider import SupplyChainProvider
    from app.services.report.daily_selection_report import DailySelectionReportService
    from sqlalchemy import select
    from app.models.product import Product

    print("=" * 60)
    print("Phase 16.5 真实运行验证")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 初始化数据库表
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 检查并添加可能缺失的列（数据库迁移）
        from sqlalchemy import text, inspect
        def check_columns(connection):
            inspector = inspect(connection)
            columns = [c['name'] for c in inspector.get_columns('products')]
            return columns
        columns = await conn.run_sync(check_columns)
        # 添加缺失的列
        missing_cols = [
            ('category', 'VARCHAR(100)'),
            ('url', 'TEXT'),
            ('lifecycle_stage', "VARCHAR(20) DEFAULT 'NEW'"),
            ('status', "VARCHAR(20) DEFAULT 'ACTIVE'"),
        ]
        for col_name, col_type in missing_cols:
            if col_name not in columns:
                await conn.execute(text(f'ALTER TABLE products ADD COLUMN {col_name} {col_type}'))
                print(f"[迁移] 添加 products.{col_name} 列")
    print("[初始化] 数据库表已创建\n")

    stats = {
        "started_at": datetime.now().isoformat(),
        "crawl": {"total": 0, "taobao": 0},
        "clean": {"total": 0, "passed": 0},
        "score": {"avg": 0, "max": 0, "min": 0},
        "save": {"new": 0, "updated": 0},
        "supply_chain": {"matched": 0, "total": 0, "rate": 0, "avg_margin": 0},
        "report": {"new_products": 0, "top_picks": 0},
    }

    # ── Step 1: 淘宝真实采集 ──────────────────────────────────
    print("[Step 1] 淘宝真实采集...")
    keyword = "蓝牙耳机"
    crawler = TaobaoCrawler()

    try:
        # 尝试登录检查
        logged_in = await crawler.check_login()
        print(f"  登录状态: {'已登录' if logged_in else '未登录'}")

        if not logged_in:
            print("  [警告] 未登录淘宝，尝试无登录采集...")

        # 采集数据
        products = await crawler.crawl(keyword=keyword, max_pages=1, limit=10)
        stats["crawl"]["total"] = len(products)
        stats["crawl"]["taobao"] = len(products)
        print(f"  采集到 {len(products)} 个商品")

        if products:
            for i, p in enumerate(products[:3]):
                print(f"    [{i+1}] {p.name[:30]}... RMB {p.price}")
    except Exception as e:
        print(f"  [错误] 采集失败: {e}")
        products = []
    finally:
        await crawler.close()

    # 如果没有真实数据，使用 Mock 数据继续
    if not products:
        print("\n[Mock] 使用 Mock 数据继续验证...")
        products = [
            RawProduct(
                name="无线蓝牙耳机入耳式降噪运动超长续航2024新款",
                platform="taobao", shop="数码旗舰店", price=128.0,
                sales_24h=1500, image="https://img.alicdn.com/earphone1.jpg",
            ),
            RawProduct(
                name="蓝牙耳机真无线降噪入耳式超长续航",
                platform="taobao", shop="音频专营", price=89.9,
                sales_24h=800, image="https://img.alicdn.com/earphone2.jpg",
            ),
            RawProduct(
                name="夏季碎花连衣裙女2024新款法式复古",
                platform="taobao", shop="时尚女装店", price=89.0,
                sales_24h=600, image="https://img.alicdn.com/dress1.jpg",
            ),
            RawProduct(
                name="手机壳iPhone15透明防摔保护套",
                platform="taobao", shop="手机配件专营", price=19.9,
                sales_24h=5000, image="https://img.alicdn.com/case1.jpg",
            ),
            RawProduct(
                name="充电宝20000毫安大容量快充移动电源",
                platform="taobao", shop="数码配件城", price=79.0,
                sales_24h=2000, image="https://img.alicdn.com/power1.jpg",
            ),
        ]
        stats["crawl"]["total"] = len(products)
        print(f"  Mock 数据: {len(products)} 个商品")

    # ── Step 2: 清洗 ──────────────────────────────────────────
    print(f"\n[Step 2] 数据清洗...")
    cleaner = ProductCleanPipeline()
    cleaned = cleaner.process_batch(products)
    stats["clean"]["total"] = len(products)
    stats["clean"]["passed"] = len(cleaned)
    print(f"  清洗结果: {len(cleaned)}/{len(products)} 通过")

    # ── Step 3: 评分 ──────────────────────────────────────────
    print(f"\n[Step 3] AI 评分...")
    analyzer = ProductAnalyzer()
    ranked = analyzer.rank(cleaned)

    if ranked:
        scores = [r["ai_score"] for r in ranked]
        stats["score"]["avg"] = round(sum(scores) / len(scores), 1)
        stats["score"]["max"] = max(scores)
        stats["score"]["min"] = min(scores)
        print(f"  评分结果: 平均={stats['score']['avg']}, 最高={stats['score']['max']}, 最低={stats['score']['min']}")

        print("\n  TOP 5 商品:")
        for i, item in enumerate(ranked[:5], 1):
            p = item["product"]
            print(f"    [{i}] {p.name[:25]}... RMB {p.price} | 评分: {item['ai_score']:.1f}")

    # ── Step 4: 保存入库 ──────────────────────────────────────
    print(f"\n[Step 4] 保存到数据库...")
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        svc = ProductService(session)
        save_result = await svc.save_raw_products(products)
        stats["save"]["new"] = save_result.get("new_count", 0)
        stats["save"]["updated"] = save_result.get("updated_count", 0)
        print(f"  保存结果: 新增={stats['save']['new']}, 更新={stats['save']['updated']}")

    # ── Step 5: 供应链匹配 ────────────────────────────────────
    print(f"\n[Step 5] 供应链匹配...")
    async with session_factory() as session:
        # 获取已保存的淘宝商品
        stmt = (
            select(Product)
            .where(Product.platform == "taobao", Product.status == "ACTIVE")
            .order_by(Product.ai_score.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        taobao_products = list(result.scalars().all())

        stats["supply_chain"]["total"] = len(taobao_products)
        print(f"  待匹配商品: {len(taobao_products)}")

        # 使用 Mock Provider
        provider = SupplyChainProvider()  # 默认 Mock 模式
        matcher = SupplyChainMatcher(session, provider=provider)

        matches = []
        for product in taobao_products:
            match = await matcher.match_product(product)
            if match:
                matches.append(match)

        stats["supply_chain"]["matched"] = len(matches)
        if taobao_products:
            stats["supply_chain"]["rate"] = round(len(matches) / len(taobao_products) * 100, 1)

        if matches:
            margins = [m.profit_margin for m in matches]
            stats["supply_chain"]["avg_margin"] = round(sum(margins) / len(margins), 1)
            print(f"  匹配结果: {len(matches)}/{len(taobao_products)} ({stats['supply_chain']['rate']}%)")
            print(f"  平均利润率: {stats['supply_chain']['avg_margin']}%")

            print("\n  匹配详情:")
            for m in matches[:5]:
                print(f"    - {m.product_id}: 匹配分={m.match_score:.2f}, 利润率={m.profit_margin:.1f}%")

    # ── Step 6: 日报生成 ──────────────────────────────────────
    print(f"\n[Step 6] 生成选品日报...")
    async with session_factory() as session:
        report_svc = DailySelectionReportService(session)
        report = await report_svc.generate(limit=20)

        stats["report"]["new_products"] = report["summary"]["new_products_count"]
        stats["report"]["top_picks"] = len(report["top_picks"])
        stats["report"]["date"] = report["date"]

        print(f"  日报日期: {report['date']}")
        print(f"  新品数量: {stats['report']['new_products']}")
        print(f"  匹配数量: {report['summary']['matched_count']}")
        print(f"  TOP 精选: {stats['report']['top_picks']}")

        if report["top_picks"]:
            print("\n  TOP 10 推荐商品:")
            for i, pick in enumerate(report["top_picks"][:10], 1):
                margin_str = f"{pick['profit_margin']:.1f}%" if pick.get("profit_margin") else "N/A"
                print(f"    [{i}] {pick['product_name'][:25]}... | 利润率: {margin_str} | 原因: {pick['selection_reason']}")

    # ── 汇总报告 ──────────────────────────────────────────────
    stats["finished_at"] = datetime.now().isoformat()

    print("\n" + "=" * 60)
    print("验证报告汇总")
    print("=" * 60)
    print(f"""
┌─────────────────────────────────────────────────────────────┐
│ 采集统计                                                     │
│   总商品数: {stats['crawl']['total']:<45} │
│   淘宝: {stats['crawl']['taobao']:<51} │
├─────────────────────────────────────────────────────────────┤
│ 清洗统计                                                     │
│   通过/总数: {stats['clean']['passed']}/{stats['clean']['total']:<40} │
├─────────────────────────────────────────────────────────────┤
│ 评分统计                                                     │
│   平均分: {stats['score']['avg']:<20} 最高: {stats['score']['max']:<15} │
├─────────────────────────────────────────────────────────────┤
│ 供应链匹配                                                   │
│   匹配率: {stats['supply_chain']['rate']}% ({stats['supply_chain']['matched']}/{stats['supply_chain']['total']}){' ' * 35} │
│   平均利润率: {stats['supply_chain']['avg_margin']}%{' ' * 40} │
├─────────────────────────────────────────────────────────────┤
│ 日报统计                                                     │
│   新品数: {stats['report']['new_products']:<20} TOP精选: {stats['report']['top_picks']:<15} │
└─────────────────────────────────────────────────────────────┘
""")

    # 保存 JSON 报告
    report_path = "storage/phase16_5_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"详细报告已保存: {report_path}")

    return stats


if __name__ == "__main__":
    asyncio.run(run_validation())
