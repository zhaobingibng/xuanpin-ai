"""Safe schema migration — 增量补全缺失列/表，保留已有数据 (Phase 46.2.1).

用法:
    python -m app.database.migrate
    python -m app.database.migrate --dry-run    # 仅预览，不执行

安全保证:
    - 所有操作使用 ALTER TABLE ADD COLUMN / CREATE TABLE IF NOT EXISTS
    - 每步 try/except 容错（列/表已存在则跳过）
    - 不删除任何列或表
    - 不修改现有数据
    - --dry-run 模式可预览变更
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "storage" / "xuanpin.db"


# ═══════════════════════════════════════════════════════════════
# Migration definitions
# ═══════════════════════════════════════════════════════════════

MIGRATIONS = [
    # ── supplier_matches: 补全 Phase 44 ProductMatcher 多维评分 + FK ──
    {
        "description": "supplier_matches: 新增 supplier_product_id (FK → supplier_products)",
        "sql": """ALTER TABLE supplier_matches
                    ADD COLUMN supplier_product_id INTEGER
                    REFERENCES supplier_products(id)""",
    },
    {
        "description": "supplier_matches: 新增 text_score (文本相似度)",
        "sql": "ALTER TABLE supplier_matches ADD COLUMN text_score FLOAT",
    },
    {
        "description": "supplier_matches: 新增 feature_score (特征匹配评分)",
        "sql": "ALTER TABLE supplier_matches ADD COLUMN feature_score FLOAT",
    },
    {
        "description": "supplier_matches: 新增 image_score (图片相似度)",
        "sql": "ALTER TABLE supplier_matches ADD COLUMN image_score FLOAT",
    },
    {
        "description": "supplier_matches: 新增 rank (匹配排名)",
        "sql": "ALTER TABLE supplier_matches ADD COLUMN rank INTEGER",
    },
    # ── supplier_products: 创建新表 ──
    {
        "description": "supplier_products: 创建 1688 供应商商品表",
        "sql": """CREATE TABLE IF NOT EXISTS supplier_products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      VARCHAR(50)   NOT NULL DEFAULT '1688',
            offer_id    VARCHAR(100)  NOT NULL UNIQUE,
            title       VARCHAR(500)  NOT NULL DEFAULT '',
            price       FLOAT         NOT NULL DEFAULT 0.0,
            sales       INTEGER       NOT NULL DEFAULT 0,
            shop_name   VARCHAR(200)  NOT NULL DEFAULT '',
            url         TEXT,
            image       TEXT,
            created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""",
    },
    # ── recommendation_status: 创建新表 ──
    {
        "description": "recommendation_status: 创建推荐池审核状态表",
        "sql": """CREATE TABLE IF NOT EXISTS recommendation_status (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id      INTEGER      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            report_date     DATE         NOT NULL,
            status          VARCHAR(20)  NOT NULL DEFAULT 'NEW',
            review_notes    TEXT,
            reviewed_at     DATETIME,
            created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(product_id, report_date)
        )""",
    },
    # ── 索引 ──
    {
        "description": "recommendation_status: idx on product_id",
        "sql": "CREATE INDEX IF NOT EXISTS idx_rs_product_id ON recommendation_status(product_id)",
    },
    {
        "description": "recommendation_status: idx on report_date",
        "sql": "CREATE INDEX IF NOT EXISTS idx_rs_report_date ON recommendation_status(report_date)",
    },
    {
        "description": "supplier_matches: idx on supplier_product_id",
        "sql": "CREATE INDEX IF NOT EXISTS idx_sm_supplier_product ON supplier_matches(supplier_product_id)",
    },
]


# ═══════════════════════════════════════════════════════════════
# Migration engine
# ═══════════════════════════════════════════════════════════════


def run_migrations(db_path: Path, dry_run: bool = False) -> int:
    """执行所有迁移，返回成功数量。"""
    if not db_path.exists():
        logger.error("数据库不存在: {}", db_path)
        return 0

    conn = sqlite3.connect(str(db_path))
    applied = 0
    skipped = 0
    failed = 0

    for m in MIGRATIONS:
        desc = m["description"]
        sql = m["sql"]

        if dry_run:
            logger.info("[DRY-RUN]  {}", desc)
            continue

        try:
            conn.execute(sql)
            conn.commit()
            logger.success("✓ {}", desc)
            applied += 1
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            if "duplicate column" in err_msg or "already exists" in err_msg or "duplicate" in err_msg:
                logger.info("⊙ {} (已存在，跳过)", desc)
                skipped += 1
            else:
                logger.error("✗ {} — {}", desc, e)
                failed += 1
                conn.rollback()
        except Exception as e:
            logger.error("✗ {} — {}", desc, e)
            failed += 1
            conn.rollback()

    conn.close()

    if dry_run:
        logger.info("[DRY-RUN] 预览完成：{} 条待执行", len(MIGRATIONS))
    else:
        logger.info(
            "迁移完成: {} applied, {} skipped, {} failed (total {})",
            applied,
            skipped,
            failed,
            len(MIGRATIONS),
        )
        if failed > 0:
            logger.warning("存在失败项，请检查日志。")

    return applied


def verify_schema(db_path: Path) -> bool:
    """迁移后验证 ORM 可以正常反射数据库。"""
    from sqlalchemy import inspect
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    inspector = inspect(engine)

    required_tables = {"supplier_matches", "supplier_products", "recommendation_status"}
    existing_tables = set(inspector.get_table_names())

    missing = required_tables - existing_tables
    if missing:
        logger.error("验证失败 — 缺失表: {}", missing)
        return False

    # 验证 supplier_matches 列完整
    sm_cols = {c["name"] for c in inspector.get_columns("supplier_matches")}
    required_sm_cols = {
        "supplier_product_id", "text_score", "feature_score",
        "image_score", "rank",
    }
    missing_sm = required_sm_cols - sm_cols
    if missing_sm:
        logger.error("验证失败 — supplier_matches 缺失列: {}", missing_sm)
        return False

    logger.success("Schema 验证通过 — 所有表和列均已就绪")
    engine.dispose()
    return True


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe schema migration")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览变更，不执行",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DB_PATH),
        help="数据库路径 (默认: storage/xuanpin.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    logger.info("数据库: {}", db_path)

    run_migrations(db_path, dry_run=args.dry_run)

    if not args.dry_run:
        verify_schema(db_path)


if __name__ == "__main__":
    main()
