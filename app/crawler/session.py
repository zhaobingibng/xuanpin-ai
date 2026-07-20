"""Cookie session management — auto-detect cookie validity."""

from __future__ import annotations

from loguru import logger

from app.crawler.base import BaseCrawler


# Cookie 状态常量
COOKIE_VALID = "COOKIE_VALID"
COOKIE_EXPIRED = "COOKIE_EXPIRED"
COOKIE_MISSING = "COOKIE_MISSING"


async def check_cookie(crawler: BaseCrawler) -> str:
    """检测指定平台爬虫的 Cookie 是否有效。

    流程：
    1. 检查 Cookie 文件是否存在
    2. 启动 Crawler → 调用 check_login() 检测登录状态
    3. 返回状态字符串

    Args:
        crawler: 已初始化的平台 Crawler 实例。

    Returns:
        状态字符串:
        - COOKIE_VALID: Cookie 有效，已登录
        - COOKIE_EXPIRED: Cookie 已过期，需要重新登录
        - COOKIE_MISSING: Cookie 文件不存在
    """
    platform = crawler.PLATFORM

    # 1. Cookie 文件是否存在
    if not crawler.has_cookies():
        logger.info("[{}] Cookie 文件不存在", platform)
        return COOKIE_MISSING

    # 2. 启动 Crawler 检测登录
    try:
        is_logged_in = await crawler.check_login()
        if is_logged_in:
            logger.info("[{}] Cookie 有效", platform)
            return COOKIE_VALID
        else:
            logger.warning("[{}] Cookie 已过期", platform)
            return COOKIE_EXPIRED
    except Exception as e:
        logger.error("[{}] Cookie 检测失败: {}", platform, e)
        return COOKIE_EXPIRED
    finally:
        await crawler.close()
