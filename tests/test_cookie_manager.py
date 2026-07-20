"""Tests for CookieManager — Phase 9.2.1."""

import json

import pytest

from app.crawler.base import CookieManager


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def cookie_dir(tmp_path):
    """Return a temporary cookie directory."""
    return tmp_path / "cookies"


@pytest.fixture
def manager(cookie_dir):
    """Return a CookieManager using a temporary directory."""
    return CookieManager(cookie_dir)


SAMPLE_COOKIES = [
    {"name": "session_id", "value": "abc123", "domain": ".example.com"},
    {"name": "token", "value": "xyz789", "domain": ".example.com"},
]


# ── Platform validation ──────────────────────────────────────


class TestPlatformValidation:
    """Invalid platform names must raise ValueError."""

    def test_valid_xiaohongshu(self, manager):
        manager.get_cookie_path("xiaohongshu")

    def test_valid_douyin(self, manager):
        manager.get_cookie_path("douyin")

    def test_valid_kuaishou(self, manager):
        manager.get_cookie_path("kuaishou")

    def test_invalid_platform_raises(self, manager):
        with pytest.raises(ValueError, match="Unsupported platform"):
            manager.get_cookie_path("weibo")

    def test_invalid_empty_string(self, manager):
        with pytest.raises(ValueError):
            manager.save("", [])

    def test_invalid_none_like(self, manager):
        with pytest.raises(ValueError):
            manager.load("instagram")

    def test_invalid_on_exists(self, manager):
        with pytest.raises(ValueError):
            manager.exists("tiktok")

    def test_invalid_on_clear(self, manager):
        with pytest.raises(ValueError):
            manager.clear("facebook")

    def test_invalid_on_save(self, manager):
        with pytest.raises(ValueError):
            manager.save("pinterest", [])

    def test_invalid_on_load(self, manager):
        with pytest.raises(ValueError):
            manager.load("twitter")


# ── save() ────────────────────────────────────────────────────


class TestSave:
    """CookieManager.save() behaviour."""

    def test_save_creates_directory(self, cookie_dir):
        """Directory is auto-created on first save."""
        assert not cookie_dir.exists()
        mgr = CookieManager(cookie_dir)
        mgr.save("xiaohongshu", SAMPLE_COOKIES)
        assert cookie_dir.exists()

    def test_save_writes_json(self, manager):
        manager.save("xiaohongshu", SAMPLE_COOKIES)
        path = manager.get_cookie_path("xiaohongshu")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["name"] == "session_id"

    def test_save_utf8_chinese(self, manager):
        """Chinese characters should be preserved (ensure_ascii=False)."""
        cookies = [{"name": "中文", "value": "测试", "domain": ".xhs.com"}]
        manager.save("xiaohongshu", cookies)
        path = manager.get_cookie_path("xiaohongshu")
        raw = path.read_text(encoding="utf-8")
        assert "中文" in raw
        assert "测试" in raw

    def test_save_indent2(self, manager):
        """Output should be indented with 2 spaces."""
        manager.save("douyin", SAMPLE_COOKIES)
        path = manager.get_cookie_path("douyin")
        raw = path.read_text(encoding="utf-8")
        assert "  " in raw  # at least 2-space indent

    def test_save_overwrites(self, manager):
        """Second save should overwrite the first."""
        manager.save("xiaohongshu", SAMPLE_COOKIES)
        new_cookies = [{"name": "new", "value": "data", "domain": ".xhs.com"}]
        manager.save("xiaohongshu", new_cookies)
        data = manager.load("xiaohongshu")
        assert len(data) == 1
        assert data[0]["name"] == "new"

    def test_save_empty_list(self, manager):
        manager.save("kuaishou", [])
        data = manager.load("kuaishou")
        assert data == []

    def test_save_all_platforms(self, manager):
        """Save to all three platforms independently."""
        for platform in ("xiaohongshu", "douyin", "kuaishou"):
            manager.save(platform, [{"name": platform, "value": "v", "domain": ".d"}])
        for platform in ("xiaohongshu", "douyin", "kuaishou"):
            data = manager.load(platform)
            assert data[0]["name"] == platform


# ── load() ────────────────────────────────────────────────────


class TestLoad:
    """CookieManager.load() behaviour."""

    def test_load_existing(self, manager):
        manager.save("douyin", SAMPLE_COOKIES)
        data = manager.load("douyin")
        assert data == SAMPLE_COOKIES

    def test_load_file_not_exists(self, manager):
        """Missing file returns empty list, no exception."""
        data = manager.load("xiaohongshu")
        assert data == []

    def test_load_corrupt_json(self, manager, cookie_dir):
        """Corrupt JSON file returns empty list with warning."""
        cookie_dir.mkdir(parents=True, exist_ok=True)
        path = cookie_dir / "xiaohongshu.json"
        path.write_text("{bad json!!", encoding="utf-8")
        data = manager.load("xiaohongshu")
        assert data == []

    def test_load_empty_file(self, manager, cookie_dir):
        """Empty JSON array returns empty list."""
        cookie_dir.mkdir(parents=True, exist_ok=True)
        path = cookie_dir / "douyin.json"
        path.write_text("[]", encoding="utf-8")
        data = manager.load("douyin")
        assert data == []

    def test_load_corrupt_encoding(self, manager, cookie_dir):
        """Non-UTF8 bytes should be handled gracefully."""
        cookie_dir.mkdir(parents=True, exist_ok=True)
        path = cookie_dir / "kuaishou.json"
        path.write_bytes(b"\xff\xfe\x80\x81")
        data = manager.load("kuaishou")
        assert data == []


# ── exists() ──────────────────────────────────────────────────


class TestExists:
    """CookieManager.exists() behaviour."""

    def test_exists_false(self, manager):
        assert manager.exists("xiaohongshu") is False

    def test_exists_true(self, manager):
        manager.save("xiaohongshu", SAMPLE_COOKIES)
        assert manager.exists("xiaohongshu") is True

    def test_exists_after_clear(self, manager):
        manager.save("douyin", SAMPLE_COOKIES)
        manager.clear("douyin")
        assert manager.exists("douyin") is False


# ── get_cookie_path() ─────────────────────────────────────────


class TestGetCookiePath:
    """CookieManager.get_cookie_path() behaviour."""

    def test_path_format(self, manager, cookie_dir):
        path = manager.get_cookie_path("xiaohongshu")
        assert path == cookie_dir / "xiaohongshu.json"

    def test_all_platforms(self, manager, cookie_dir):
        assert manager.get_cookie_path("douyin") == cookie_dir / "douyin.json"
        assert manager.get_cookie_path("kuaishou") == cookie_dir / "kuaishou.json"


# ── clear() ───────────────────────────────────────────────────


class TestClear:
    """CookieManager.clear() behaviour."""

    def test_clear_existing(self, manager):
        manager.save("xiaohongshu", SAMPLE_COOKIES)
        assert manager.exists("xiaohongshu")
        manager.clear("xiaohongshu")
        assert not manager.exists("xiaohongshu")

    def test_clear_nonexistent(self, manager):
        """Clearing a non-existent file should not raise."""
        manager.clear("douyin")  # no error

    def test_clear_only_affects_target(self, manager):
        """Clear one platform should not affect others."""
        manager.save("xiaohongshu", SAMPLE_COOKIES)
        manager.save("douyin", SAMPLE_COOKIES)
        manager.clear("xiaohongshu")
        assert not manager.exists("xiaohongshu")
        assert manager.exists("douyin")


# ── clear_all() ───────────────────────────────────────────────


class TestClearAll:
    """CookieManager.clear_all() behaviour."""

    def test_clear_all(self, manager):
        for p in ("xiaohongshu", "douyin", "kuaishou"):
            manager.save(p, SAMPLE_COOKIES)
        manager.clear_all()
        for p in ("xiaohongshu", "douyin", "kuaishou"):
            assert not manager.exists(p)

    def test_clear_all_empty_dir(self, manager):
        """clear_all on non-existent dir should not raise."""
        manager.clear_all()

    def test_clear_all_only_json(self, manager, cookie_dir):
        """clear_all should only remove .json files."""
        cookie_dir.mkdir(parents=True, exist_ok=True)
        (cookie_dir / "readme.txt").write_text("keep me", encoding="utf-8")
        manager.save("xiaohongshu", SAMPLE_COOKIES)
        manager.clear_all()
        assert (cookie_dir / "readme.txt").exists()
        assert not manager.exists("xiaohongshu")


# ── Directory auto-creation ──────────────────────────────────


class TestDirectoryCreation:
    """Cookie directory is auto-created when needed."""

    def test_save_creates_nested_dir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "cookies"
        mgr = CookieManager(nested)
        assert not nested.exists()
        mgr.save("xiaohongshu", SAMPLE_COOKIES)
        assert nested.exists()
        assert mgr.exists("xiaohongshu")

    def test_init_does_not_create_dir(self, tmp_path):
        """CookieManager.__init__ should not create the directory."""
        d = tmp_path / "not_created"
        CookieManager(d)
        assert not d.exists()
