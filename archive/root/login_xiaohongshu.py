"""小红书登录脚本（自动检测版）— 打开可见浏览器，登录成功后自动保存 Cookie。

使用方法：
    uv run python login_xiaohongshu.py

流程：
    1. 自动打开浏览器窗口（非 headless）
    2. 在浏览器中完成小红书登录（扫码或手机号均可）
    3. 脚本自动检测登录状态，登录成功后自动保存 Cookie 并关闭浏览器
"""

import asyncio
import json
from pathlib import Path


LOGIN_COOKIE_NAMES = {
    "web_session",
    "customer-sso-sid",
    "galaxy_creator_session_id",
    "access-token-creator",
}


async def login():
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = await context.new_page()

    print("[1/4] 正在打开小红书...")
    await page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded")
    print("[2/4] 页面已加载，请在浏览器中完成登录")
    print()
    print("=" * 50)
    print("  请在浏览器窗口中完成登录")
    print("  （扫码登录或手机号登录均可）")
    print("  脚本会自动检测登录状态并保存 Cookie")
    print("=" * 50)
    print()

    # Poll for login cookies
    saved = False
    for attempt in range(180):  # Wait up to 3 minutes
        await asyncio.sleep(1)
        cookies = await context.cookies()
        cookie_names = {c["name"] for c in cookies}
        found = cookie_names & LOGIN_COOKIE_NAMES

        if found:
            print(f"\n[3/4] 检测到登录态 Cookie: {found}")

            # Wait a moment for all cookies to settle
            await asyncio.sleep(2)
            cookies = await context.cookies()

            # Save cookies
            cookie_dir = Path("storage/cookies")
            cookie_dir.mkdir(parents=True, exist_ok=True)
            cookie_file = cookie_dir / "xiaohongshu.json"
            cookie_file.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))

            print(f"[4/4] Cookie 已保存: {cookie_file}")
            print(f"  Cookie 数量: {len(cookies)}")
            print(f"  登录态: {[c['name'] for c in cookies if c['name'] in LOGIN_COOKIE_NAMES]}")
            saved = True
            break

        # Show progress every 10 seconds
        if attempt > 0 and attempt % 10 == 0:
            print(f"  等待登录中... ({attempt}s)")

    if not saved:
        print("\n超时（3分钟），未检测到登录。")

    await browser.close()
    await pw.stop()
    print("浏览器已关闭。")


if __name__ == "__main__":
    asyncio.run(login())
