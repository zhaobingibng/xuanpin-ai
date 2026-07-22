"""淘宝登录恢复脚本。

功能：
1. 检查当前登录状态（复用 TaobaoCrawler.check_login）
2. 打开可见浏览器供用户手动登录
3. 登录成功后保存 storage/taobao_state.json（AuthManager 标准路径）
4. 自动验证登录状态

用法:
    python scripts/login_taobao.py          # 检查登录状态，未登录则引导登录
    python scripts/login_taobao.py --force  # 强制重新登录（忽略已有 cookies）

依赖:
    - 复用 app/crawler/taobao.py 的 TaobaoCrawler (check_login / save_cookies)
    - 复用 app/crawler/auth_manager.py 的 AuthManager (extract_username)
    - 不修改 DailySelectionPipeline 和其他业务模块
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from loguru import logger

# ── Windows GBK 兼容: 强制 stdout 使用 UTF-8 ────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Project root ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# AuthManager / LoginHelper 期望的标准路径
TAOBAO_STATE_PATH = PROJECT_ROOT / "storage" / "taobao_state.json"
# TaobaoCrawler 内部使用的 storage_state 路径
TAOBAO_STORAGE_STATE_PATH = (
    PROJECT_ROOT / "storage" / "cookies" / "taobao_storage_state.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="淘宝登录恢复工具 — 打开浏览器完成手动登录并保存认证状态",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新登录，即使已有 cookies / storage_state",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅检查登录状态，不执行登录",
    )
    return parser.parse_args()


# ── Helpers ─────────────────────────────────────────────────────


def _extract_username(state: dict) -> str | None:
    """从 storage_state cookies 中提取淘宝用户名。"""
    for cookie in state.get("cookies", []):
        name = cookie.get("name", "")
        if name in ("_nk_", "snk", "nick", "login_current_pk"):
            value = cookie.get("value", "")
            if value and value not in ("登录", "亲，请登录"):
                try:
                    decoded = unquote(value)
                    if decoded and decoded not in ("登录", "亲，请登录"):
                        return decoded
                except Exception:
                    return value
    return None


async def _do_manual_login(crawler) -> dict | None:
    """打开可见浏览器，等待用户手动登录，返回 storage_state。

    Returns:
        Dict with storage_state data, or None on failure.
    """
    print("\n" + "─" * 50)
    print("  请在浏览器中完成淘宝登录。")
    print("  支持：账号密码 / 扫码 / 短信验证")
    print("  登录成功后，回到此处按 Enter 继续...")
    print("─" * 50)

    context = None
    page = None
    try:
        context = await crawler._new_context()
        page = await context.new_page()

        await page.goto(
            crawler.BASE_URL,
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_timeout(1000)

        # 等待用户完成登录
        input("\n  👆 登录完成后按 Enter...")

        # 保存 cookies（通过 CookieManager → storage/cookies/taobao.json）
        await crawler.save_cookies(context)
        logger.info("[login_taobao] Cookies saved via CookieManager")

        # 获取完整 storage_state
        state = await context.storage_state()
        logger.info("[login_taobao] Storage state captured ({} cookies)", len(state.get("cookies", [])))

        return state

    except Exception as e:
        logger.error("[login_taobao] Manual login failed: {}", e)
        print(f"\n  ❌ 登录失败: {e}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


def _save_state_files(state: dict) -> None:
    """Save storage_state to both AuthManager path and TaobaoCrawler path."""
    state_json = json.dumps(state, ensure_ascii=False, indent=2)

    # 主路径: AuthManager / LoginHelper 期望的路径
    TAOBAO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TAOBAO_STATE_PATH.write_text(state_json, encoding="utf-8")
    print(f"  ✅ storage/taobao_state.json 已保存 ({len(state_json)} 字节)")

    # 副路径: TaobaoCrawler 内部路径 (向后兼容)
    TAOBAO_STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TAOBAO_STORAGE_STATE_PATH.write_text(state_json, encoding="utf-8")
    print(f"  ✅ cookies/taobao_storage_state.json 已保存")


async def _verify_login(crawler) -> tuple[bool, str | None]:
    """验证登录状态并返回 (是否已登录, 用户名)。"""
    try:
        is_logged_in = await crawler.check_login()
        if is_logged_in:
            state = crawler.auth_manager.load_storage_state_data("taobao")
            username = _extract_username(state) if state else None
            return True, username
        return False, None
    except Exception as e:
        logger.warning("[login_taobao] Verification failed: {}", e)
        return False, None


# ── Main ────────────────────────────────────────────────────────


async def main() -> int:
    args = parse_args()
    print("=" * 55)
    print("  淘宝登录恢复工具  —  Phase 42.2")
    print("=" * 55)
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  状态文件: {TAOBAO_STATE_PATH}")

    # 延迟导入以支持测试 mock
    from app.crawler.taobao import TaobaoCrawler

    crawler = TaobaoCrawler()

    # 强制非 headless 模式（用户需要看到浏览器窗口）
    crawler._settings.browser_headless = False

    try:
        # ── Step 1: 检查现有登录状态 ─────────────────────────
        print("\n[Step 1] 检查当前登录状态...")

        if args.force:
            print("  🔄 --force: 跳过状态检查，强制重新登录")
        else:
            # 先快速检查（无浏览器）
            has_state = TAOBAO_STATE_PATH.exists() and TAOBAO_STATE_PATH.stat().st_size > 0
            has_cookies = crawler.has_cookies()

            if not has_state and not has_cookies:
                print("  ⚠️ 未发现任何登录凭据（无 state 文件，无 cookies）")
            elif has_state and has_cookies:
                print("  ℹ️ 发现 storage_state + cookies，尝试验证...")
            elif has_state:
                print("  ℹ️ 发现 storage_state，尝试验证...")
            else:
                print("  ℹ️ 发现 cookies，尝试验证...")

        # ── Step 1b: check-only 模式 ─────────────────────────
        if args.check_only:
            is_ok, username = await _verify_login(crawler)
            if is_ok:
                print(f"\n  ✅ 登录状态有效！用户名: {username or 'N/A'}")
                print("  无需重新登录。")
                return 0
            else:
                print("\n  ❌ 登录状态无效或已过期。")
                print("  请运行: python scripts/login_taobao.py")
                return 1

        # ── Step 2: 登录（如需） ─────────────────────────────
        need_login = args.force
        if not need_login:
            # 快速检查：有状态文件时尝试验证
            if has_state or has_cookies:
                try:
                    is_ok, username = await _verify_login(crawler)
                    if is_ok:
                        print(f"\n  ✅ 登录状态有效！用户名: {username or 'N/A'}")
                        print("  无需重新登录。使用 --force 可强制重新登录。")
                        return 0
                    else:
                        print("  ⚠️ 现有凭据已失效，需要重新登录。")
                        need_login = True
                except Exception as e:
                    logger.warning("[login_taobao] Pre-check failed: {}", e)
                    need_login = True
            else:
                need_login = True

        if not need_login:
            print("\n  无需执行登录操作。")
            return 0

        # ── Step 3: 手动登录 ────────────────────────────────
        print("\n[Step 2] 打开浏览器进行手动登录...")
        state = await _do_manual_login(crawler)

        if state is None:
            print("\n  ❌ 登录失败，未获取到登录状态。")
            return 1

        # ── Step 4: 保存状态文件 ────────────────────────────
        print("\n[Step 3] 保存登录状态...")
        _save_state_files(state)

        # 提取并显示用户名
        username = _extract_username(state)
        if username:
            print(f"  👤 检测到用户名: {username}")
        else:
            logger.info("[login_taobao] No username found in cookies")

        # ── Step 5: 验证 ────────────────────────────────────
        print("\n[Step 4] 验证登录状态...")
        is_verified, verified_user = await _verify_login(crawler)
        if is_verified:
            print(f"  ✅ 登录验证成功！用户名: {verified_user or username or 'N/A'}")
        else:
            print("  ⚠️ 状态文件已保存但实时验证未通过。")
            print("  可能是验证时浏览器配置不同导致的，")
            print("  请稍后运行 --check-only 再确认。")

        # ── Summary ─────────────────────────────────────────
        print("\n" + "=" * 55)
        print("  登录恢复完成")
        print("=" * 55)
        print(f"  storage/taobao_state.json:     {'✅ 已保存' if TAOBAO_STATE_PATH.exists() else '❌ 未生成'}")
        print(f"  cookies/taobao.json:           {'✅ 已保存' if crawler.has_cookies() else '❌ 未生成'}")
        print(f"  cookies/taobao_storage_state:  {'✅ 已保存' if TAOBAO_STORAGE_STATE_PATH.exists() else '❌ 未生成'}")
        print(f"  用户名:                         {username or 'N/A'}")

        return 0 if is_verified else 2

    finally:
        await crawler.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
