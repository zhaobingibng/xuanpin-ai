"""Tests for ProductCleaner."""

from app.services.cleaner.product_cleaner import ProductCleaner


class TestCleanName:
    """Product name cleaning tests."""

    def setup_method(self):
        self.cleaner = ProductCleaner()

    def test_remove_emoji(self):
        """Emojis should be stripped from names."""
        assert self.cleaner.clean_name("🔥超值手机壳") == "超值手机壳"
        assert self.cleaner.clean_name("好看的包👍🎉") == "好看的包"

    def test_remove_special_symbols(self):
        """Special symbols should be removed, but / - . kept."""
        assert self.cleaner.clean_name("【限时】蓝牙耳机") == "限时蓝牙耳机"
        assert self.cleaner.clean_name("手机壳@#$%") == "手机壳"
        assert self.cleaner.clean_name("USB-A/Type-C线") == "USB-A/Type-C线"

    def test_remove_ad_words(self):
        """Ad words should be stripped."""
        assert self.cleaner.clean_name("包邮蓝牙耳机") == "蓝牙耳机"
        assert self.cleaner.clean_name("秒杀手机壳") == "手机壳"
        assert self.cleaner.clean_name("清仓收纳盒") == "收纳盒"
        assert self.cleaner.clean_name("爆款新款水杯") == "水杯"

    def test_collapse_whitespace(self):
        """Multiple spaces should collapse to one."""
        assert self.cleaner.clean_name("蓝牙   耳机   降噪") == "蓝牙 耳机 降噪"
        assert self.cleaner.clean_name("  手机壳  ") == "手机壳"

    def test_empty_input(self):
        """Empty or None-like input returns empty string."""
        assert self.cleaner.clean_name("") == ""

    def test_clean_name_preserves_chinese(self):
        """Chinese characters should be fully preserved."""
        assert self.cleaner.clean_name("华为Mate60手机壳") == "华为Mate60手机壳"


class TestClassify:
    """Product classification tests."""

    def setup_method(self):
        self.cleaner = ProductCleaner()

    def test_digital_category(self):
        """数码 keywords should classify correctly."""
        assert self.cleaner.classify("华为手机壳") == "数码"
        assert self.cleaner.classify("蓝牙耳机降噪") == "数码"
        assert self.cleaner.classify("20000毫安充电宝") == "数码"
        assert self.cleaner.classify("机械键盘青轴") == "数码"

    def test_home_category(self):
        """家居 keywords should classify correctly."""
        assert self.cleaner.classify("保温水杯500ml") == "家居"
        assert self.cleaner.classify("竹凉席1.8米") == "家居"
        assert self.cleaner.classify("桌面收纳盒") == "家居"
        assert self.cleaner.classify("抽纸巾大包装") == "家居"

    def test_clothing_category(self):
        """服饰 keywords should classify correctly."""
        assert self.cleaner.classify("夏季衣服男") == "服饰"
        assert self.cleaner.classify("运动鞋跑步鞋") == "服饰"
        assert self.cleaner.classify("单肩包斜挎包") == "服饰"

    def test_other_category(self):
        """No keyword match should return Other."""
        assert self.cleaner.classify("神秘商品XYZ") == "Other"
        assert self.cleaner.classify("") == "Other"

    def test_first_match_wins(self):
        """When multiple categories could match, first match wins."""
        # 手机(数码) appears before 包(服饰) in CATEGORY_MAP
        assert self.cleaner.classify("手机包") == "数码"


class TestDeduplicate:
    """Product deduplication tests."""

    def setup_method(self):
        self.cleaner = ProductCleaner()

    def test_first_seen_not_duplicate(self):
        """First occurrence should return False (not a duplicate)."""
        assert self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "xiaohongshu") is False

    def test_second_seen_is_duplicate(self):
        """Same name+shop+platform should return True (duplicate)."""
        self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "xiaohongshu")
        assert self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "xiaohongshu") is True

    def test_different_shop_not_duplicate(self):
        """Same name but different shop is not a duplicate."""
        self.cleaner.deduplicate("蓝牙耳机", "店铺A", "xiaohongshu")
        assert self.cleaner.deduplicate("蓝牙耳机", "店铺B", "xiaohongshu") is False

    def test_different_platform_not_duplicate(self):
        """Same name+shop but different platform is not a duplicate."""
        self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "xiaohongshu")
        assert self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "douyin") is False

    def test_reset_clears_history(self):
        """After reset, previously seen products are no longer duplicates."""
        self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "xiaohongshu")
        self.cleaner.reset()
        assert self.cleaner.deduplicate("蓝牙耳机", "数码旗舰店", "xiaohongshu") is False
