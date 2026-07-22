"""Tests for app/services/taobao_session_service.py — 淘宝会话服务。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.taobao_session_service import (
    SessionState,
    SessionInfo,
    TaobaoSessionService,
    get_taobao_session,
    _taobao_session,
)


# ── SessionState ───────────────────────────────────────────────


class TestSessionState:
    """验证 SessionState 枚举。"""

    def test_all_states_defined(self):
        """应包含所有预期状态。"""
        assert SessionState.IDLE.value == "idle"
        assert SessionState.LOGGED_IN.value == "logged_in"
        assert SessionState.CRAWLING.value == "crawling"
        assert SessionState.BLOCKED.value == "blocked"
        assert SessionState.WAITING_HUMAN.value == "waiting_human"
        assert SessionState.ERROR.value == "error"


# ── SessionInfo ────────────────────────────────────────────────


class TestSessionInfo:
    """验证 SessionInfo 数据类。"""

    def test_defaults(self):
        info = SessionInfo()
        assert info.state == SessionState.IDLE
        assert info.is_logged_in is False
        assert info.is_blocked is False
        assert info.block_reason == ""

    def test_logged_in(self):
        # is_logged_in is derived in get_snapshot(), not from state alone
        svc = TaobaoSessionService()
        svc._state = SessionState.LOGGED_IN
        info = svc.get_snapshot()
        assert info.is_logged_in is True


# ── TaobaoSessionService ───────────────────────────────────────


class TestTaobaoSessionService:
    """验证 TaobaoSessionService 核心逻辑。"""

    def test_initial_snapshot(self):
        svc = TaobaoSessionService()
        info = svc.get_snapshot()
        assert info.state == SessionState.IDLE
        assert info.is_logged_in is False
        assert info.message == ""

    def test_get_snapshot_reflects_state(self):
        svc = TaobaoSessionService()
        svc._state = SessionState.LOGGED_IN
        svc._message = "ready"
        info = svc.get_snapshot()
        assert info.state == SessionState.LOGGED_IN
        assert info.message == "ready"
        assert info.is_logged_in is True

    # ── Block detection (static) ───────────────────────────────

    def test_detect_block_sec_taobao(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<meta http-equiv="refresh" content="0;url=https://sec.taobao.com/query">'
        )
        assert blocked is True
        assert "sec.taobao.com" in reason.lower()

    def test_detect_block_punish(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<div class="punish-container">punish</div>'
        )
        assert blocked is True
        assert "punish" in reason.lower()

    def test_detect_block_verify_code(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<div>请输入验证码</div>'
        )
        assert blocked is True
        assert "验证码" in reason

    def test_detect_block_slider(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<div>滑块验证</div>'
        )
        assert blocked is True

    def test_detect_block_baxia(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<script src="https://cfg.sec.taobao.com/baxia"></script>'
        )
        assert blocked is True

    def test_detect_block_login_required(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<span>亲，请登录</span>'
        )
        assert blocked is True

    def test_detect_block_normal_page(self):
        blocked, reason = TaobaoSessionService._detect_block_static(
            '<html><body><div class="J_ItemList">products</div></body></html>'
        )
        assert blocked is False
        assert reason == ""

    # ── Lock prevents concurrent start ─────────────────────────

    @pytest.mark.asyncio
    async def test_start_when_not_idle(self):
        svc = TaobaoSessionService()
        svc._state = SessionState.LOGGED_IN
        info = await svc.start_session()
        assert "已在" in info.message

    # ── Crawl when not logged in ──────────────────────────────

    @pytest.mark.asyncio
    async def test_crawl_when_not_logged_in(self):
        svc = TaobaoSessionService()
        result = await svc.crawl("海苔卷", limit=5)
        assert result["success"] is False
        assert "无法采集" in result["message"]

    # ── stop_session resets to IDLE ────────────────────────────

    @pytest.mark.asyncio
    async def test_stop_session_resets(self):
        svc = TaobaoSessionService()
        svc._state = SessionState.LOGGED_IN
        info = await svc.stop_session()
        assert info.state == SessionState.IDLE
        assert "已关闭" in info.message

    # ── check_status when idle ────────────────────────────────

    @pytest.mark.asyncio
    async def test_check_status_when_idle(self):
        svc = TaobaoSessionService()
        info = await svc.check_status()
        assert info.state == SessionState.IDLE
        assert "无活跃" in info.message

    # ── check_status when no page ─────────────────────────────

    @pytest.mark.asyncio
    async def test_check_status_no_page(self):
        svc = TaobaoSessionService()
        svc._state = SessionState.LOGGED_IN
        svc._page = None
        info = await svc.check_status()
        assert info.state == SessionState.ERROR
        assert "页面不存在" in info.message

    # ── stop_session handles Nones ────────────────────────────

    @pytest.mark.asyncio
    async def test_stop_session_handles_none_page_context(self):
        svc = TaobaoSessionService()
        svc._page = None
        svc._context = None
        svc._crawler = None
        info = await svc.stop_session()
        assert info.state == SessionState.IDLE

    # ── wait_for_human when not blocked ───────────────────────

    @pytest.mark.asyncio
    async def test_wait_for_human_not_blocked_returns_quickly(self):
        svc = TaobaoSessionService()
        svc._state = SessionState.BLOCKED
        svc._page = AsyncMock()
        # Return HTML with login indicator → not blocked after check
        svc._page.content = AsyncMock(return_value=(
            '<html><body>'
            '<span class="member-nick">已登录用户</span>'
            '<div class="J_ItemList">products</div>'
            '</body></html>'
        ))

        info = await svc.wait_for_human(poll_interval=0.1, max_wait=5.0)
        assert not info.is_blocked
        assert "已解除" in info.message


# ── Global singleton ──────────────────────────────────────────


class TestGlobalSingleton:
    """验证全局单例。"""

    def test_get_taobao_session_returns_singleton(self):
        # Save original
        import app.services.taobao_session_service as mod
        orig = mod._taobao_session
        mod._taobao_session = None
        try:
            s1 = get_taobao_session()
            s2 = get_taobao_session()
            assert s1 is s2
        finally:
            mod._taobao_session = orig


# ── Mocked start_session ──────────────────────────────────────


class TestStartSessionMocked:
    """用 mock 验证 start_session 流程。"""

    @pytest.mark.asyncio
    async def test_start_session_logged_in(self):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.content = AsyncMock(return_value=(
            '<html><body>'
            '<span class="member-nick">测试用户</span>'
            '</body></html>'
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler.BASE_URL = "https://www.taobao.com"
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)

        svc = TaobaoSessionService()
        with patch(
            "app.crawler.taobao.TaobaoCrawler",
            return_value=mock_crawler,
        ):
            info = await svc.start_session()

        assert info.state == SessionState.LOGGED_IN
        assert info.is_logged_in is True

    @pytest.mark.asyncio
    async def test_start_session_blocked(self):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.content = AsyncMock(return_value=(
            '<html><body>'
            '<div>punish 滑块验证</div>'
            '</body></html>'
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_crawler = MagicMock()
        mock_crawler.BASE_URL = "https://www.taobao.com"
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)

        svc = TaobaoSessionService()
        with patch(
            "app.crawler.taobao.TaobaoCrawler",
            return_value=mock_crawler,
        ):
            info = await svc.start_session()

        assert info.state == SessionState.BLOCKED
        assert info.is_blocked is True

    @pytest.mark.asyncio
    async def test_start_session_crawl_success(self):
        """启动后采集成功。"""
        # Setup page for start_session (login detected)
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.content = AsyncMock(return_value=(
            '<html><body>'
            '<span class="member-nick">测试用户</span>'
            '</body></html>'
        ))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        # Create mock products
        from app.crawler.base import RawProduct
        mock_products = [
            RawProduct(name="海苔卷A", platform="taobao", shop="店铺1", price="9.9", url="https://item.taobao.com/1"),
            RawProduct(name="海苔卷B", platform="taobao", shop="店铺2", price="12.9", url="https://item.taobao.com/2"),
        ]

        mock_crawler = MagicMock()
        mock_crawler.BASE_URL = "https://www.taobao.com"
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(return_value=mock_products)

        svc = TaobaoSessionService()
        with patch(
            "app.crawler.taobao.TaobaoCrawler",
            return_value=mock_crawler,
        ):
            # Start
            info = await svc.start_session()
            assert info.state == SessionState.LOGGED_IN

            # Crawl
            result = await svc.crawl("海苔卷", limit=2)

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["products"]) == 2
        assert result["products"][0]["name"] == "海苔卷A"

    @pytest.mark.asyncio
    async def test_start_session_crawl_captcha_after(self):
        """采集后触发风控检测。"""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        # start_session 内 _detect_login + _detect_block 各调 1 次 content() = 2 次
        # crawl 后检测再调 1 次 = 第 3 次
        mock_page.content = AsyncMock(side_effect=[
            # call 1 & 2: 登录成功 (start_session)
            '<html><body><span class="member-nick">测试用户</span></body></html>',
            '<html><body><span class="member-nick">测试用户</span></body></html>',
            # call 3: 采集后触发风控
            '<html><body>滑块验证 sec.taobao.com punish</body></html>',
        ])

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        from app.crawler.base import RawProduct
        mock_products = [RawProduct(name="test", platform="taobao", shop="s", price="1", url="")]

        mock_crawler = MagicMock()
        mock_crawler.BASE_URL = "https://www.taobao.com"
        mock_crawler._new_context = AsyncMock(return_value=mock_context)
        mock_crawler.load_cookies = AsyncMock()
        mock_crawler.load_storage_state = AsyncMock(return_value=True)
        mock_crawler.crawl = AsyncMock(return_value=mock_products)

        svc = TaobaoSessionService()
        with patch(
            "app.crawler.taobao.TaobaoCrawler",
            return_value=mock_crawler,
        ):
            await svc.start_session()
            result = await svc.crawl("海苔卷", limit=1)

        # Crawl succeeded but captcha detected after
        assert result["success"] is True
        assert "风控" in result["message"]
        assert result["state"] == SessionState.BLOCKED.value
