"""淘宝人工辅助采集会话服务。

管理 Taobao 浏览器会话生命周期：
- 启动可见浏览器（headless=False）
- 检测登录态 / 风控页面
- 风控时等待人工处理
- 执行关键词采集

不修改 TaobaoCrawler 核心解析逻辑 —— 仅在其外层包装会话管理。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from loguru import logger


class SessionState(str, Enum):
    """会话状态枚举。"""
    IDLE = "idle"
    STARTING = "starting"
    LOGGED_IN = "logged_in"
    CRAWLING = "crawling"
    BLOCKED = "blocked"              # 风控/验证码
    WAITING_HUMAN = "waiting_human"  # 等待人工解除风控
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class SessionInfo:
    """会话快照 — 用于 API 返回。"""
    state: SessionState = SessionState.IDLE
    is_logged_in: bool = False
    is_blocked: bool = False
    block_reason: str = ""
    last_check: datetime | None = None
    last_crawl: datetime | None = None
    last_crawl_keyword: str = ""
    last_crawl_count: int = 0
    session_started: datetime | None = None
    message: str = ""


class TaobaoSessionService:
    """淘宝浏览器会话服务。

    Usage:
        svc = TaobaoSessionService()
        status = await svc.get_status()
        await svc.start_session()
        result = await svc.crawl("海苔卷", limit=10)
    """

    def __init__(self) -> None:
        self._state = SessionState.IDLE
        self._lock = asyncio.Lock()
        self._crawler = None           # TaobaoCrawler 实例（懒加载）
        self._context = None           # 浏览器上下文
        self._page = None              # 当前 page（用于人工交互）
        self._last_check: datetime | None = None
        self._last_crawl: datetime | None = None
        self._last_keyword: str = ""
        self._last_count: int = 0
        self._session_started: datetime | None = None
        self._message: str = ""
        self._block_reason: str = ""

    # ── Public API ──────────────────────────────────────────

    def get_snapshot(self) -> SessionInfo:
        """线程安全的状态快照。"""
        return SessionInfo(
            state=self._state,
            is_logged_in=self._state in (SessionState.LOGGED_IN, SessionState.CRAWLING),
            is_blocked=self._state in (SessionState.BLOCKED, SessionState.WAITING_HUMAN),
            block_reason=self._block_reason,
            last_check=self._last_check,
            last_crawl=self._last_crawl,
            last_crawl_keyword=self._last_keyword,
            last_crawl_count=self._last_count,
            session_started=self._session_started,
            message=self._message,
        )

    async def start_session(self) -> SessionInfo:
        """启动淘宝浏览器会话（可见窗口 + persistent profile）。"""
        async with self._lock:
            if self._state not in (SessionState.IDLE, SessionState.ERROR, SessionState.STOPPING):
                self._message = f"会话已在 {self._state.value} 状态，无法重新启动"
                return self.get_snapshot()

            self._state = SessionState.STARTING
            self._message = "正在启动浏览器..."
            self._session_started = datetime.now()

        try:
            from app.crawler.taobao import TaobaoCrawler

            self._crawler = TaobaoCrawler()
            self._context = await self._crawler._new_context()
            await self._crawler.load_cookies(self._context)
            await self._crawler.load_storage_state(self._context)

            # 打开首页，检测登录状态
            self._page = await self._context.new_page()
            await self._page.goto(
                self._crawler.BASE_URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await self._page.wait_for_timeout(3000)

            # 检测登录
            logged_in = await self._detect_login(self._page)
            blocked, reason = await self._detect_block(self._page)

            if blocked:
                self._state = SessionState.BLOCKED
                self._block_reason = reason
                self._message = f"检测到风控: {reason} — 请在浏览器中手动操作"
                logger.warning("[TaobaoSession] Blocked: {}", reason)
            elif logged_in:
                self._state = SessionState.LOGGED_IN
                self._message = "已登录，可以开始采集"
                logger.info("[TaobaoSession] Logged in")
            else:
                self._state = SessionState.BLOCKED
                self._block_reason = "未检测到登录状态"
                self._message = "未登录 — 请在浏览器中手动登录"
                logger.warning("[TaobaoSession] Not logged in")

            self._last_check = datetime.now()
            return self.get_snapshot()

        except Exception as e:
            self._state = SessionState.ERROR
            self._message = f"启动失败: {e}"
            logger.error("[TaobaoSession] Start failed: {}", e)
            return self.get_snapshot()

    async def check_status(self) -> SessionInfo:
        """检测当前页面登录和风控状态。"""
        if self._state in (SessionState.IDLE, SessionState.ERROR):
            self._message = "无活跃会话"
            return self.get_snapshot()

        async with self._lock:
            if self._page is None:
                self._state = SessionState.ERROR
                self._message = "浏览器页面不存在"
                return self.get_snapshot()

            try:
                html = await self._page.content()
                logged_in = await self._detect_login(self._page)
                blocked, reason = self._detect_block_from_html(html)

                if blocked:
                    if self._state != SessionState.WAITING_HUMAN:
                        self._state = SessionState.BLOCKED
                        self._block_reason = reason
                        self._message = f"风控检测: {reason}"
                elif logged_in:
                    if self._state in (SessionState.BLOCKED, SessionState.WAITING_HUMAN):
                        self._message = "风控已解除，可以继续采集"
                    self._state = SessionState.LOGGED_IN
                    self._block_reason = ""
                else:
                    self._state = SessionState.BLOCKED
                    self._block_reason = "登录态丢失"
                    self._message = "登录态丢失"

                self._last_check = datetime.now()
                return self.get_snapshot()

            except Exception as e:
                logger.warning("[TaobaoSession] Status check failed: {}", e)
                self._message = f"状态检测异常: {e}"
                return self.get_snapshot()

    async def wait_for_human(self, poll_interval: float = 3.0, max_wait: float = 300.0) -> SessionInfo:
        """等待人工解除风控（轮询检测）。"""
        self._state = SessionState.WAITING_HUMAN
        self._message = "等待人工处理风控..."

        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            info = await self.check_status()
            if not info.is_blocked:
                self._message = f"风控已解除（等待 {elapsed:.0f}s）"
                return info

            self._message = f"等待人工处理中... ({elapsed:.0f}s/{max_wait:.0f}s)"

        self._message = f"等待超时（{max_wait:.0f}s），风控仍未解除"
        return self.get_snapshot()

    async def crawl(self, keyword: str, limit: int = 10) -> dict:
        """执行淘宝关键词采集。

        Returns:
            dict with keys: success, count, products, message, state.
        """
        if self._state not in (SessionState.LOGGED_IN,):
            return {
                "success": False,
                "count": 0,
                "products": [],
                "message": f"无法采集: 当前状态 {self._state.value}",
                "state": self._state.value,
            }

        async with self._lock:
            self._state = SessionState.CRAWLING
            self._last_keyword = keyword
            self._message = f"正在采集: {keyword}..."

        try:
            products = await self._crawler.crawl(
                keyword=keyword,
                max_pages=1,
                limit=limit,
            )

            count = len(products)
            result = {
                "success": count > 0,
                "count": count,
                "products": [
                    {
                        "name": p.name,
                        "shop": p.shop,
                        "price": p.price,
                        "url": p.url,
                    }
                    for p in products
                ],
                "message": f"采集完成: {count} 条商品",
                "state": SessionState.LOGGED_IN.value,
            }

            self._last_count = count
            self._last_crawl = datetime.now()

            # 检测采集后是否触发风控
            if self._page:
                html = await self._page.content()
                blocked, reason = self._detect_block_from_html(html)
                if blocked:
                    self._state = SessionState.BLOCKED
                    self._block_reason = reason
                    result["message"] += f" [!!] 采集后触发风控: {reason}"
                    result["state"] = SessionState.BLOCKED.value
                else:
                    self._state = SessionState.LOGGED_IN
            else:
                self._state = SessionState.LOGGED_IN

            self._message = result["message"]
            return result

        except Exception as e:
            self._state = SessionState.ERROR
            self._message = f"采集异常: {e}"
            logger.error("[TaobaoSession] Crawl failed: {}", e)
            return {
                "success": False,
                "count": 0,
                "products": [],
                "message": str(e),
                "state": SessionState.ERROR.value,
            }

    async def stop_session(self) -> SessionInfo:
        """关闭浏览器会话。"""
        async with self._lock:
            self._state = SessionState.STOPPING
            self._message = "正在关闭会话..."

            if self._page:
                try:
                    await self._page.close()
                except Exception:
                    pass
                self._page = None

            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None

            if self._crawler:
                try:
                    await self._crawler.close()
                except Exception:
                    pass
                self._crawler = None

            self._state = SessionState.IDLE
            self._message = "会话已关闭"
            self._session_started = None
            return self.get_snapshot()

    # ── Internal ──────────────────────────────────────────

    async def _detect_login(self, page) -> bool:
        """检测页面是否为已登录状态。"""
        try:
            html = await page.content()
            # 如果有用户昵称元素且不是"登录"文字 → 已登录
            login_selectors = [
                r'class="[^"]*nick[^"]*"[^>]*>([^<]+)',
                r'member-nick[^>]*>([^<]+)',
            ]
            for pat in login_selectors:
                m = re.search(pat, html)
                if m:
                    text = m.group(1).strip()
                    if text and text not in ("登录", "亲，请登录"):
                        return True

            # 登录链接存在 → 未登录
            if "login.taobao.com" in html or "site-nav-login" in html:
                return False

            return False
        except Exception:
            return False

    def _detect_block_from_html(self, html: str) -> tuple[bool, str]:
        """从 HTML 检测风控/验证码。"""
        return self._detect_block_static(html)

    async def _detect_block(self, page) -> tuple[bool, str]:
        """通过页面对象检测风控（异步版）。"""
        try:
            html = await page.content()
            return self._detect_block_static(html)
        except Exception:
            return False, ""

    @staticmethod
    def _detect_block_static(html: str) -> tuple[bool, str]:
        """静态检测风控关键词（同步，可在 _detect_block_from_html 中复用）。"""
        blockers = [
            ("sec.taobao.com", "跳转到安全页面 (sec.taobao.com)"),
            ("punish", "检测到 punishment 风控标记"),
            ("验证码", "出现验证码"),
            ("滑块验证", "出现滑块验证"),
            ("baxia", "Baxia 风控拦截"),
            ("亲，请登录", "需要登录"),
        ]
        for keyword, reason in blockers:
            if keyword.lower() in html.lower():
                return True, reason
        return False, ""


# ── Global singleton ─────────────────────────────────────

_taobao_session: TaobaoSessionService | None = None


def get_taobao_session() -> TaobaoSessionService:
    """获取全局 TaobaoSessionService 单例。"""
    global _taobao_session
    if _taobao_session is None:
        _taobao_session = TaobaoSessionService()
    return _taobao_session
