"""Tests for ProductCleanPipeline."""

from app.crawler.models.schemas import RawProduct
from app.services.cleaner.pipeline import CleanedProduct, ProductCleanPipeline


def _make_raw(**overrides) -> RawProduct:
    """Helper to build a RawProduct with sensible defaults."""
    defaults = {
        "name": "🔥爆款蓝牙耳机降噪",
        "platform": "xiaohongshu",
        "shop": "数码旗舰店",
        "price": 99.9,
        "viewers": 1200,
        "sales_24h": 350,
        "image": "https://img.example.com/earphone.jpg",
    }
    defaults.update(overrides)
    return RawProduct(**defaults)


class TestProcessSingle:
    """Test pipeline.process() on a single RawProduct."""

    def setup_method(self):
        self.pipeline = ProductCleanPipeline()

    def test_full_cleaning(self):
        """Name should be cleaned, price/sales normalized, category assigned."""
        raw = _make_raw(name="🔥爆款蓝牙耳机降噪 ¥199")
        result = self.pipeline.process(raw)

        assert result is not None
        assert result.name == "蓝牙耳机降噪 199"  # emoji + 爆款 + ¥ removed, digits kept
        assert result.price == 99.9
        assert result.sales_24h == 350
        assert result.viewers == 1200
        assert result.category == "数码"
        assert result.platform == "xiaohongshu"
        assert result.shop == "数码旗舰店"
        assert result.image == "https://img.example.com/earphone.jpg"

    def test_empty_name_dropped(self):
        """Product with only ad words should be dropped (empty name)."""
        raw = _make_raw(name="包邮秒杀清仓爆款新款")
        result = self.pipeline.process(raw)
        assert result is None

    def test_price_string_normalized(self):
        """Price passed as string should be normalized."""
        raw = _make_raw(price="¥199.9")
        # price_normalize handles strings, but RawProduct expects float
        # so we create manually
        raw_obj = RawProduct(
            name="水杯保温",
            platform="douyin",
            shop="家居店",
            price="¥199.9",  # type: ignore[arg-type]
            viewers=100,
            sales_24h=50,
        )
        result = self.pipeline.process(raw_obj)
        assert result is not None
        assert result.price == 199.9

    def test_sales_string_normalized(self):
        """Sales as string like '1.2万' should be normalized."""
        raw_obj = RawProduct(
            name="手机壳保护套",
            platform="kuaishou",
            shop="手机配件",
            price=19.9,
            viewers=500,
            sales_24h="1.2万",  # type: ignore[arg-type]
        )
        result = self.pipeline.process(raw_obj)
        assert result is not None
        assert result.sales_24h == 12000
        assert result.category == "数码"


class TestProcessBatch:
    """Test pipeline.process_batch() with deduplication."""

    def setup_method(self):
        self.pipeline = ProductCleanPipeline()

    def test_batch_deduplication(self):
        """Identical products (after cleaning) should be deduplicated."""
        raws = [
            _make_raw(name="🔥蓝牙耳机", shop="店A", platform="xiaohongshu"),
            _make_raw(name="蓝牙耳机", shop="店A", platform="xiaohongshu"),  # same after clean
            _make_raw(name="蓝牙耳机", shop="店B", platform="xiaohongshu"),  # different shop
        ]
        results = self.pipeline.process_batch(raws)
        assert len(results) == 2  # second is deduped, third passes (different shop)

    def test_batch_filters_invalid(self):
        """Invalid products should be silently filtered."""
        raws = [
            _make_raw(name="正常商品手机壳"),
            _make_raw(name="包邮秒杀清仓"),  # becomes empty → dropped
            _make_raw(name="另一个水杯"),
        ]
        results = self.pipeline.process_batch(raws)
        assert len(results) == 2
        assert results[0].name == "正常商品手机壳"
        assert results[1].name == "另一个水杯"

    def test_batch_classify(self):
        """Each product should be classified correctly."""
        raws = [
            _make_raw(name="机械键盘青轴"),
            _make_raw(name="竹凉席1.8米"),
            _make_raw(name="运动鞋跑步鞋"),
            _make_raw(name="神秘商品XYZ"),
        ]
        results = self.pipeline.process_batch(raws)
        categories = [r.category for r in results]
        assert categories == ["数码", "家居", "服饰", "Other"]

    def test_batch_empty_input(self):
        """Empty input should return empty output."""
        results = self.pipeline.process_batch([])
        assert results == []

    def test_to_db_kwargs(self):
        """CleanedProduct.to_db_kwargs() should produce valid Product fields."""
        raw = _make_raw(name="充电宝20000毫安")
        result = self.pipeline.process(raw)
        assert result is not None

        kwargs = result.to_db_kwargs()
        assert kwargs["name"] == "充电宝20000毫安"
        assert kwargs["platform"] == "xiaohongshu"
        assert kwargs["shop"] == "数码旗舰店"
        assert kwargs["price"] == 99.9
        assert kwargs["viewers"] == 1200
        assert kwargs["sales_24h"] == 350
        assert kwargs["image"] == "https://img.example.com/earphone.jpg"
        # category and url are now included in db kwargs
        assert kwargs["category"] == "数码"
        assert "url" in kwargs
