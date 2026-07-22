"""Tests for Phase 21 Task 2: Database Initialization Service."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.database.init_db import (
    init_database,
    init_database_sync,
    verify_database,
    REQUIRED_TABLES,
)


# ── Sync Initialization Tests ──────────────────────────────────


class TestSyncInitialization:
    """Test synchronous database initialization."""

    def test_init_database_sync_success(self):
        """Test successful sync initialization."""
        with patch("app.database.init_db.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            # Mock connection for table check
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = [
                ("products",),
                ("product_scores",),
                ("login_sessions",),
            ]
            mock_engine.connect.return_value.__enter__.return_value = mock_conn

            result = init_database_sync()

            assert result["success"] is True
            assert result["error"] is None

    def test_init_database_sync_error(self):
        """Test sync initialization with error."""
        with patch("app.database.init_db.get_engine") as mock_get_engine:
            mock_get_engine.side_effect = Exception("Connection failed")

            result = init_database_sync()

            assert result["success"] is False
            assert result["error"] is not None


# ── Async Initialization Tests ─────────────────────────────────


class TestAsyncInitialization:
    """Test asynchronous database initialization."""

    @pytest.mark.asyncio
    async def test_init_database_success(self):
        """Test successful async initialization."""
        with patch("app.database.init_db.get_async_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.begin = MagicMock()
            mock_engine.begin.return_value.__aenter__ = AsyncMock()
            mock_engine.begin.return_value.__aexit__ = AsyncMock()
            mock_engine.dispose = AsyncMock()

            # Mock connection for table check
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("products",),
                ("product_scores",),
            ]
            mock_conn.execute = AsyncMock(return_value=mock_result)
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock()

            mock_get_engine.return_value = mock_engine

            # Mock run_sync
            with patch("app.database.init_db.Base") as mock_base:
                mock_base.metadata.create_all = MagicMock()

                result = await init_database()

            assert result["success"] is True
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_init_database_error(self):
        """Test async initialization with error."""
        with patch("app.database.init_db.get_async_engine") as mock_get_engine:
            mock_get_engine.side_effect = Exception("Connection failed")

            result = await init_database()

            assert result["success"] is False
            assert "error" in result


# ── Verification Tests ─────────────────────────────────────────


class TestVerification:
    """Test database verification."""

    @pytest.mark.asyncio
    async def test_verify_database_all_present(self):
        """Test verification with all tables present."""
        with patch("app.database.init_db.get_async_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dispose = AsyncMock()

            # Mock connection
            mock_conn = MagicMock()
            mock_result = MagicMock()
            # Return all required tables
            mock_result.fetchall.return_value = [(table,) for table in REQUIRED_TABLES]
            mock_conn.execute = AsyncMock(return_value=mock_result)
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock()

            mock_get_engine.return_value = mock_engine

            result = await verify_database()

            assert result["connected"] is True
            assert result["all_present"] is True
            assert len(result["tables_missing"]) == 0

    @pytest.mark.asyncio
    async def test_verify_database_missing_tables(self):
        """Test verification with missing tables."""
        with patch("app.database.init_db.get_async_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dispose = AsyncMock()

            # Mock connection with only some tables
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [("products",), ("product_scores",)]
            mock_conn.execute = AsyncMock(return_value=mock_result)
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock()

            mock_get_engine.return_value = mock_engine

            result = await verify_database()

            assert result["connected"] is True
            assert result["all_present"] is False
            assert len(result["tables_missing"]) > 0

    @pytest.mark.asyncio
    async def test_verify_database_connection_error(self):
        """Test verification with connection error."""
        with patch("app.database.init_db.get_async_engine") as mock_get_engine:
            mock_get_engine.side_effect = Exception("Connection failed")

            result = await verify_database()

            assert result["connected"] is False
            assert "error" in result


# ── Required Tables Tests ──────────────────────────────────────


class TestRequiredTables:
    """Test required tables configuration."""

    def test_required_tables_defined(self):
        """Test that required tables are defined."""
        assert len(REQUIRED_TABLES) > 0
        assert "products" in REQUIRED_TABLES
        assert "product_scores" in REQUIRED_TABLES
        assert "supplier_matches" in REQUIRED_TABLES
        assert "opportunity_scores" in REQUIRED_TABLES
        assert "login_sessions" in REQUIRED_TABLES
        assert "daily_task_logs" in REQUIRED_TABLES

    def test_required_tables_unique(self):
        """Test that required tables are unique."""
        assert len(REQUIRED_TABLES) == len(set(REQUIRED_TABLES))


# ── Idempotency Tests ──────────────────────────────────────────


class TestIdempotency:
    """Test that initialization is idempotent (safe to run multiple times)."""

    @pytest.mark.asyncio
    async def test_init_multiple_times(self):
        """Test that initialization can be run multiple times safely."""
        with patch("app.database.init_db.get_async_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.begin = MagicMock()
            mock_engine.begin.return_value.__aenter__ = AsyncMock()
            mock_engine.begin.return_value.__aexit__ = AsyncMock()
            mock_engine.dispose = AsyncMock()

            # Mock connection
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [(table,) for table in REQUIRED_TABLES]
            mock_conn.execute = AsyncMock(return_value=mock_result)
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock()

            mock_get_engine.return_value = mock_engine

            # Run initialization multiple times
            result1 = await init_database()
            result2 = await init_database()
            result3 = await init_database()

            # All should succeed
            assert result1["success"] is True
            assert result2["success"] is True
            assert result3["success"] is True
