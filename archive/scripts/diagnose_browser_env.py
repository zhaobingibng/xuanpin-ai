"""浏览器环境诊断脚本 — 全面检查 BrowserManager 配置的浏览器指纹。

功能：
1. 复用 TaobaoCrawler 打开浏览器上下文
2. 通过 page.evaluate 检查：
   - headless 状态（配置值 + 实际检测）
   - user agent（配置值 vs 真实 navigator.userAgent）
   - webdriver 特征（navigator.webdriver 等反自动化检测信号）
   - viewport（screen / window / devicePixelRatio）
   - locale（navigator.language / languages）
   - timezone（Intl.DateTimeFormat）
   - 其他指纹（plugins、hardwareConcurrency、chrome 对象等）
3. 导航到淘宝搜索页，检查最终页面类型
4. 截图保存到 storage/taobao_debug/
5. 输出诊断报告

用法:
    python scripts/diagnose_browser_env.py
    python scripts/diagnose_browser_env.py --no-navigate  # 跳过导航，仅检查浏览器指纹
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Windows GBK 兼容 ──────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Project root ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEBUG_DIR = PROJECT_ROOT / "storage" / "taobao_debug"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="浏览器环境诊断")
    parser.add_argument(
        "--no-navigate",
        action="store_true",
        help="跳过淘宝页面导航，仅检查浏览器指纹",
    )
    parser.add_argument(
        "--keyword",
        default="海苔卷",
        help="搜索关键词 (默认: 海苔卷)",
    )
    return parser.parse_args(argv)


# ── Section printer ─────────────────────────────────────────────


def _hdr(title: str) -> None:
    print(f"\n{'─' * 62}")
    print(f"  {title}")
    print(f"{'─' * 62}")


# ── JS diagnostic script ────────────────────────────────────────


BROWSER_FINGERPRINT_JS = """
() => {
    const info = {};

    // ── Navigator core ──
    info.userAgent = navigator.userAgent;
    info.appVersion = navigator.appVersion;
    info.platform = navigator.platform;
    info.vendor = navigator.vendor;
    info.productSub = navigator.productSub;

    // ── WebDriver detection ──
    info.webdriver = navigator.webdriver;

    // ── Languages ──
    info.language = navigator.language;
    info.languages = Array.from(navigator.languages || []);

    // ── Plugins ──
    info.pluginCount = navigator.plugins ? navigator.plugins.length : -1;
    info.pluginNames = [];
    if (navigator.plugins) {
        for (let i = 0; i < Math.min(navigator.plugins.length, 5); i++) {
            info.pluginNames.push(navigator.plugins[i].name);
        }
    }
    info.mimeTypesCount = navigator.mimeTypes ? navigator.mimeTypes.length : -1;

    // ── Hardware ──
    info.hardwareConcurrency = navigator.hardwareConcurrency;
    info.deviceMemory = navigator.deviceMemory || 'unknown';
    info.maxTouchPoints = navigator.maxTouchPoints;

    // ── Screen / viewport ──
    info.screenWidth = screen.width;
    info.screenHeight = screen.height;
    info.screenAvailWidth = screen.availWidth;
    info.screenAvailHeight = screen.availHeight;
    info.screenColorDepth = screen.colorDepth;
    info.screenPixelDepth = screen.pixelDepth;
    info.innerWidth = window.innerWidth;
    info.innerHeight = window.innerHeight;
    info.outerWidth = window.outerWidth;
    info.outerHeight = window.outerHeight;
    info.devicePixelRatio = window.devicePixelRatio;

    // ── Timezone ──
    try {
        info.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch(e) { info.timezone = 'error'; }
    info.timezoneOffset = new Date().getTimezoneOffset();

    // ── Chrome-specific ──
    info.hasChrome = typeof chrome !== 'undefined';
    info.hasChromeRuntime = (typeof chrome !== 'undefined' && chrome.runtime) ? true : false;

    // ── Permissions ──
    info.permissionsAvailable = typeof navigator.permissions !== 'undefined';

    // ── Blink features ──
    info.documentHidden = document.hidden;
    info.visibilityState = document.visibilityState;

    // ── Connection ──
    if (navigator.connection) {
        info.connectionType = navigator.connection.effectiveType || 'unknown';
        info.connectionDownlink = navigator.connection.downlink || 0;
        info.connectionRtt = navigator.connection.rtt || 0;
    } else {
        info.connectionType = 'not available';
    }

    // ── Cookie enabled ──
    info.cookieEnabled = navigator.cookieEnabled;

    // ── Do Not Track ──
    info.doNotTrack = navigator.doNotTrack || 'unspecified';

    // ── Touch support ──
    info.ontouchstart = ('ontouchstart' in window);

    // ── Canvas fingerprint (light) ──
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (ctx) {
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillStyle = '#f60';
            ctx.fillRect(0, 0, 100, 20);
            ctx.fillStyle = '#069';
            ctx.fillText('canvas fingerprint test 🪿', 2, 2);
            info.canvasHash = canvas.toDataURL().length;
        } else {
            info.canvasHash = 'no 2d context';
        }
    } catch(e) {
        info.canvasHash = 'error: ' + e.message;
    }

    // ── WebGL ──
    try {
        const glCanvas = document.createElement('canvas');
        const gl = glCanvas.getContext('webgl') || glCanvas.getContext('experimental-webgl');
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                info.webglVendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
                info.webglRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
            }
        } else {
            info.webglVendor = 'no webgl';
        }
    } catch(e) {
        info.webglVendor = 'error: ' + e.message;
    }

    return info;
}
"""

PAGE_TYPE_JS = """
() => {
    const info = {};
    info.url = location.href;
    info.title = document.title;
    info.bodyText = (document.body ? document.body.innerText.slice(0, 500) : '');

    // Detect page type
    info.hasJItemList = !!document.querySelector('.J_ItemList');
    info.hasLoginPrompt = !!document.querySelector(
        'a[href*="login.taobao.com"], .site-nav-login, .login-form'
    );
    info.hasCaptcha = !!document.querySelector(
        '[id*="captcha"], [class*="captcha"], [id*="nc_1"], .baxia-dialog'
    );

    // Count product cards via multiple selectors
    const selectors = [
        '.J_ItemList [data-nid]',
        '.m-itemlist .item',
        '.grid-item',
        '[data-spm-anchor-id] a[href*="item.taobao.com"]',
        'a[href*="item.taobao.com"]',
        'a[href*="detail.tmall.com"]',
    ];
    const counts = {};
    for (const sel of selectors) {
        counts[sel] = document.querySelectorAll(sel).length;
    }
    info.cardCounts = counts;

    // Overall
    info.totalElements = document.querySelectorAll('*').length;

    return info;
}
"""


# ── Diagnostic runners ──────────────────────────────────────────


def _print_fingerprint(fp: dict) -> None:
    """Print fingerprint results in sections."""
    print(f"\n  userAgent      : {fp.get('userAgent', '?')[:100]}")
    print(f"  platform        : {fp.get('platform', '?')}")
    print(f"  vendor          : {fp.get('vendor', '?')}")

    print(f"\n  ── WebDriver ──")
    wd = fp.get("webdriver", None)
    wd_label = f"{wd} {'[!!] 反自动化标志已暴露' if wd else '[OK] 未暴露'}"
    print(f"  navigator.webdriver: {wd_label}")

    print(f"\n  ── Locale ──")
    print(f"  language         : {fp.get('language', '?')}")
    print(f"  languages        : {fp.get('languages', [])}")

    print(f"\n  ── Timezone ──")
    print(f"  timezone         : {fp.get('timezone', '?')}")
    print(f"  timezoneOffset   : {fp.get('timezoneOffset', '?')} min")

    print(f"\n  ── Viewport ──")
    print(f"  screen           : {fp.get('screenWidth', '?')}x{fp.get('screenHeight', '?')} (avail: {fp.get('screenAvailWidth', '?')}x{fp.get('screenAvailHeight', '?')})")
    print(f"  window.inner     : {fp.get('innerWidth', '?')}x{fp.get('innerHeight', '?')}")
    print(f"  window.outer     : {fp.get('outerWidth', '?')}x{fp.get('outerHeight', '?')}")
    print(f"  devicePixelRatio : {fp.get('devicePixelRatio', '?')}")
    print(f"  colorDepth       : {fp.get('screenColorDepth', '?')}")
    print(f"  maxTouchPoints   : {fp.get('maxTouchPoints', '?')}")

    print(f"\n  ── Hardware ──")
    print(f"  concurrency      : {fp.get('hardwareConcurrency', '?')}")
    print(f"  deviceMemory     : {fp.get('deviceMemory', '?')} GB")
    print(f"  connection       : {fp.get('connectionType', '?')}")

    print(f"\n  ── Plugins ──")
    print(f"  pluginCount      : {fp.get('pluginCount', -1)}")
    print(f"  mimeTypesCount   : {fp.get('mimeTypesCount', -1)}")
    names = fp.get("pluginNames", [])
    if names:
        print(f"  first 5 plugins  : {names}")

    print(f"\n  ── Chrome ──")
    print(f"  window.chrome    : {fp.get('hasChrome', False)}")
    print(f"  chrome.runtime   : {fp.get('hasChromeRuntime', False)}")

    print(f"\n  ── Other ──")
    print(f"  cookieEnabled    : {fp.get('cookieEnabled', '?')}")
    print(f"  doNotTrack       : {fp.get('doNotTrack', '?')}")
    print(f"  permissions API  : {fp.get('permissionsAvailable', False)}")
    print(f"  document.hidden  : {fp.get('documentHidden', '?')}")
    print(f"  visibilityState  : {fp.get('visibilityState', '?')}")
    print(f"  ontouchstart     : {fp.get('ontouchstart', False)}")

    print(f"\n  ── Canvas/WebGL ──")
    print(f"  canvas hash len  : {fp.get('canvasHash', '?')}")
    print(f"  webgl vendor     : {fp.get('webglVendor', '?')}")
    print(f"  webgl renderer   : {fp.get('webglRenderer', '?')}")


def _print_page_type(pt: dict) -> None:
    """Print page type analysis."""
    print(f"\n  URL              : {pt.get('url', '?')[:120]}")
    print(f"  标题             : {pt.get('title', '?')[:80]}")
    print(f"  总元素数         : {pt.get('totalElements', '?')}")

    print(f"\n  ── 页面类型判断 ──")
    has_items = pt.get("hasJItemList", False)
    has_login = pt.get("hasLoginPrompt", False)
    has_captcha = pt.get("hasCaptcha", False)

    if has_captcha:
        page_type = "验证码/风控页面 [!!]"
    elif has_login:
        page_type = "登录页面 [!!]"
    elif has_items:
        page_type = "搜索结果页 [OK]"
    else:
        page_type = "未知/空白页面 [??]"

    print(f"  判定             : {page_type}")
    print(f"  J_ItemList       : {'有' if has_items else '无'}")
    print(f"  登录提示         : {'有 [!!]' if has_login else '无'}")
    print(f"  验证码           : {'有 [!!]' if has_captcha else '无'}")

    print(f"\n  ── 商品卡片计数 ──")
    for sel, count in pt.get("cardCounts", {}).items():
        if count > 0:
            print(f"  {sel:<50} {count}")

    # Show body text snippet
    body = pt.get("bodyText", "").strip()
    if body:
        print(f"\n  ── Body 文本 (前 300 字) ──")
        print(f"  {body[:300]}")


# ── Main ────────────────────────────────────────────────────────


async def main() -> int:
    args = parse_args()
    from app.config.settings import get_settings
    settings = get_settings()

    print(f"\n  浏览器环境诊断")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Config summary ──────────────────────────────────────────
    _hdr("配置摘要")
    print(f"  browser_headless      : {settings.browser_headless}")
    print(f"  browser_persistent    : {settings.browser_persistent}")
    print(f"  browser_user_data_dir : {settings.browser_user_data_dir}")
    print(f"  browser_user_agent    : {settings.browser_user_agent[:70]}...")
    print(f"  browser_timeout       : {settings.browser_timeout}ms")
    print(f"  login_check_timeout   : {settings.login_check_timeout}s")
    print(f"  crawler_headless      : {settings.crawler_headless}")
    print(f"  crawler_user_agent    : {settings.crawler_user_agent}")

    from app.crawler.taobao import TaobaoCrawler

    crawler = TaobaoCrawler()
    context = None
    page = None
    start = datetime.now()

    try:
        # ── Step 1: Open context ────────────────────────────────
        _hdr("Step 1: 创建浏览器上下文")
        context = await crawler._new_context()
        await crawler.load_cookies(context)
        await crawler.load_storage_state(context)

        # Check actual headless state
        bm = crawler._browser_manager
        print(f"  persistent 模式     : {bm._persistent}")
        print(f"  persistent_ctx 存在  : {bm._persistent_ctx is not None}")
        print(f"  browser 存在         : {bm._browser is not None}")
        print(f"  user_data_dir        : {bm._user_data_dir}")

        # ── Step 2: Open page ───────────────────────────────────
        _hdr("Step 2: 创建页面并注入诊断脚本")
        page = await context.new_page()

        # Navigate to a neutral page first for fingerprint check
        await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
        print("  [OK] 空白页已加载，开始指纹采集...")

        # ── Step 3: Fingerprint ─────────────────────────────────
        _hdr("Step 3: 浏览器指纹")
        fp: dict[str, Any] = await page.evaluate(BROWSER_FINGERPRINT_JS)
        _print_fingerprint(fp)

        # ── Step 4: Taobao navigation (optional) ────────────────
        if not args.no_navigate:
            keyword = args.keyword
            url = f"https://s.taobao.com/search?q={keyword}"
            _hdr(f"Step 4: 导航到淘宝搜索页")
            print(f"  URL: {url}")

            # Navigate with longer timeout
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                print("  [OK] domcontentloaded")
            except Exception as e:
                print(f"  [!!] 导航异常: {e}")

            # Wait for JS rendering
            wait_ms = 10_000
            print(f"  等待 JS 渲染 {wait_ms // 1000}s...")
            await page.wait_for_timeout(wait_ms)

            # ── Step 5: Page type ────────────────────────────────
            _hdr("Step 5: 页面类型分析")
            pt: dict[str, Any] = await page.evaluate(PAGE_TYPE_JS)
            _print_page_type(pt)

            # Screenshot
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            shot_path = DEBUG_DIR / f"browser_env_{keyword}.png"
            await page.screenshot(path=str(shot_path), full_page=False)
            print(f"\n  截图已保存: {shot_path}")

            # Save full report JSON
            report = {
                "timestamp": datetime.now().isoformat(),
                "config": {
                    "browser_headless": settings.browser_headless,
                    "browser_persistent": settings.browser_persistent,
                    "browser_user_data_dir": settings.browser_user_data_dir,
                    "browser_user_agent": settings.browser_user_agent,
                },
                "fingerprint": fp,
                "page_type": pt,
            }
            report_path = DEBUG_DIR / f"browser_env_report_{keyword}.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  报告已保存: {report_path}")

        # ── Summary ──────────────────────────────────────────────
        elapsed = (datetime.now() - start).total_seconds()
        _hdr("诊断总结")
        print(f"  耗时                : {elapsed:.1f}s")
        print(f"  模式                : {'persistent' if bm._persistent else 'standard'}")
        print(f"  headless 配置       : {settings.browser_headless}")
        print(f"  webdriver 暴露      : {fp.get('webdriver', '?')}")
        print(f"  viewport            : {fp.get('innerWidth', '?')}x{fp.get('innerHeight', '?')}")
        print(f"  locale              : {fp.get('language', '?')}")
        print(f"  timezone            : {fp.get('timezone', '?')}")
        print(f"  userAgent contains 'Headless' : {'Headless' in fp.get('userAgent', '')}")

        if "Headless" in fp.get("userAgent", ""):
            print(f"  [!!] UA 中包含 'Headless' — 强烈建议修复")
        if fp.get("webdriver"):
            print(f"  [!!] navigator.webdriver=true — 反自动化标志暴露")
        if fp.get("pluginCount", 1) == 0:
            print(f"  [!!] plugins=0 — 典型 headless 特征")
        if fp.get("webglVendor", "").startswith("Google") and "SwiftShader" in fp.get("webglRenderer", ""):
            print(f"  [!!] WebGL 使用 SwiftShader — headless 特征")

        print(f"\n  输出目录: {DEBUG_DIR}")
        return 0

    except Exception as e:
        print(f"\n  [ERROR] 诊断失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        if page:
            await page.close()
        if context:
            await context.close()
        await crawler.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
