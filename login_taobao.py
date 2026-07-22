"""淘宝/1688登录脚本 — 打开可见浏览器，登录成功后自动保存状态。

使用方法：
    uv run python login_taobao.py

流程：
    1. 自动打开浏览器窗口（非 headless）
    2. 在浏览器中完成淘宝登录（扫码或手机号均可）
    3. 脚本自动检测登录状态，登录成功后自动保存状态并关闭浏览器
"""

import asyncio
import json
from pathlib import Path

# Use project root directory for consistent paths
PROJECT_ROOT = Path(__file__).parent
STORAGE_DIR = PROJECT_ROOT / "storage"
TAOBAO_STATE_PATH = STORAGE_DIR / "taobao_state.json"
ALIBABA_STATE_PATH = STORAGE_DIR / "alibaba_state.json"


# 淘宝登录Cookie关键字段
TAOBAO_LOGIN_COOKIES = {
    "_nk_",       # 用户名
    "cookie2",    # 登录标识
    "sn",         # 序列号
    "lid",        # 登录ID
}

# 1688登录Cookie关键字段
ALIBABA_LOGIN_COOKIES = {
    "cna",        # 设备标识
    "lid",        # 登录ID
    "login_current_pk",  # 当前登录用户
}


async def login_taobao():
    """淘宝登录流程。"""
    from playwright.async_api import async_playwright

    # Debug: Print paths
    print(f"\n[Debug] 项目根目录: {PROJECT_ROOT.absolute()}")
    print(f"[Debug] 淘宝state将保存到: {TAOBAO_STATE_PATH.absolute()}")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = await context.new_page()

    print("\n" + "=" * 60)
    print("淘宝登录")
    print("=" * 60)
    print("\n[1/4] 正在打开淘宝...")
    await page.goto("https://login.taobao.com/member/login.jhtml", wait_until="domcontentloaded")
    print("[2/4] 页面已加载，请在浏览器中完成登录")
    print()
    print("-" * 60)
    print("  请在浏览器窗口中完成登录")
    print("  （扫码登录或手机号登录均可）")
    print("  脚本会自动检测登录状态并保存Cookie")
    print("  浏览器不会自动关闭，请手动按回车键继续")
    print("-" * 60)
    print()

    # Minimum wait time: 60 seconds
    MIN_WAIT_SECONDS = 60
    print(f"  最少等待 {MIN_WAIT_SECONDS} 秒，请扫码登录...")
    
    # Wait minimum time first
    for i in range(MIN_WAIT_SECONDS):
        await asyncio.sleep(1)
        if (i + 1) % 10 == 0:
            print(f"  等待中... ({i + 1}/{MIN_WAIT_SECONDS}s)")
    
    print(f"\n  已等待 {MIN_WAIT_SECONDS} 秒，开始检测登录状态...")

    # Poll for login cookies after minimum wait
    saved = False
    max_attempts = 120  # Additional 2 minutes after minimum wait
    
    for attempt in range(max_attempts):
        await asyncio.sleep(1)
        cookies = await context.cookies()
        cookie_names = {c["name"] for c in cookies}
        found = cookie_names & TAOBAO_LOGIN_COOKIES

        if found:
            print(f"\n[3/4] 检测到登录态 Cookie: {found}")

            # Wait a moment for all cookies to settle
            await asyncio.sleep(2)
            cookies = await context.cookies()

            # Save state
            state = await context.storage_state()
            state_path = TAOBAO_STATE_PATH
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # Extract username
            username = ""
            for cookie in cookies:
                if cookie["name"] == "_nk_":
                    from urllib.parse import unquote
                    username = unquote(cookie["value"])
                    break

            print(f"[4/4] 状态已保存: {state_path}")
            print(f"  Cookie 数量: {len(cookies)}")
            print(f"  用户名: {username or 'N/A'}")
            print(f"  登录态: {[c['name'] for c in cookies if c['name'] in TAOBAO_LOGIN_COOKIES]}")
            saved = True
            break

        # Show progress every 10 seconds
        if attempt > 0 and attempt % 10 == 0:
            print(f"  继续等待登录... ({attempt}s)")

    if not saved:
        print("\n" + "=" * 60)
        print("未检测到登录状态")
        print("=" * 60)
        print("\n请重新操作：")
        print("  1. 在浏览器中刷新页面")
        print("  2. 重新扫码登录")
        print("  3. 或者关闭浏览器后重新运行脚本")
        print()
        input("按回车键关闭浏览器...")

    await browser.close()
    await pw.stop()
    print("浏览器已关闭。")
    return saved


async def login_alibaba():
    """1688登录流程。"""
    from playwright.async_api import async_playwright

    # Debug: Print paths
    print(f"\n[Debug] 项目根目录: {PROJECT_ROOT.absolute()}")
    print(f"[Debug] 1688 state将保存到: {ALIBABA_STATE_PATH.absolute()}")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = await context.new_page()

    print("\n" + "=" * 60)
    print("1688登录")
    print("=" * 60)
    print("\n[1/4] 正在打开1688...")
    await page.goto("https://login.1688.com/member/signin.htm", wait_until="domcontentloaded")
    print("[2/4] 页面已加载，请在浏览器中完成登录")
    print()
    print("-" * 60)
    print("  请在浏览器窗口中完成登录")
    print("  （扫码登录或手机号登录均可）")
    print("  脚本会自动检测登录状态并保存Cookie")
    print("  浏览器不会自动关闭，请手动按回车键继续")
    print("-" * 60)
    print()

    # Minimum wait time: 60 seconds
    MIN_WAIT_SECONDS = 60
    print(f"  最少等待 {MIN_WAIT_SECONDS} 秒，请扫码登录...")
    
    # Wait minimum time first
    for i in range(MIN_WAIT_SECONDS):
        await asyncio.sleep(1)
        if (i + 1) % 10 == 0:
            print(f"  等待中... ({i + 1}/{MIN_WAIT_SECONDS}s)")
    
    print(f"\n  已等待 {MIN_WAIT_SECONDS} 秒，开始检测登录状态...")

    # Poll for login cookies after minimum wait
    saved = False
    max_attempts = 120  # Additional 2 minutes after minimum wait
    
    for attempt in range(max_attempts):
        await asyncio.sleep(1)
        cookies = await context.cookies()
        cookie_names = {c["name"] for c in cookies}
        found = cookie_names & ALIBABA_LOGIN_COOKIES

        if found:
            print(f"\n[3/4] 检测到登录态 Cookie: {found}")

            # Wait a moment for all cookies to settle
            await asyncio.sleep(2)
            cookies = await context.cookies()

            # Save state
            state = await context.storage_state()
            state_path = ALIBABA_STATE_PATH
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # Extract username
            username = ""
            for cookie in cookies:
                if cookie["name"] == "login_current_pk":
                    from urllib.parse import unquote
                    username = unquote(cookie["value"])
                    break

            print(f"[4/4] 状态已保存: {state_path}")
            print(f"  Cookie 数量: {len(cookies)}")
            print(f"  用户名: {username or 'N/A'}")
            print(f"  登录态: {[c['name'] for c in cookies if c['name'] in ALIBABA_LOGIN_COOKIES]}")
            saved = True
            break

        # Show progress every 10 seconds
        if attempt > 0 and attempt % 10 == 0:
            print(f"  继续等待登录... ({attempt}s)")

    if not saved:
        print("\n" + "=" * 60)
        print("未检测到登录状态")
        print("=" * 60)
        print("\n请重新操作：")
        print("  1. 在浏览器中刷新页面")
        print("  2. 重新扫码登录")
        print("  3. 或者关闭浏览器后重新运行脚本")
        print()
        input("按回车键关闭浏览器...")

    await browser.close()
    await pw.stop()
    print("浏览器已关闭。")
    return saved


async def main():
    """主入口。"""
    print("\n" + "=" * 60)
    print("淘宝/1688 登录工具")
    print("=" * 60)
    print("\n请选择登录平台：")
    print("  1. 淘宝")
    print("  2. 1688")
    print("  3. 两者都登录")
    print("  0. 退出")
    print()

    choice = input("请输入选项 (0-3): ").strip()

    if choice == "1":
        await login_taobao()
    elif choice == "2":
        await login_alibaba()
    elif choice == "3":
        print("\n先登录淘宝...")
        await login_taobao()
        print("\n再登录1688...")
        await login_alibaba()
    else:
        print("已退出。")


if __name__ == "__main__":
    asyncio.run(main())
