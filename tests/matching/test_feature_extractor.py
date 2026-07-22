"""Tests for Phase 28: FeatureExtractor."""

import pytest

from app.matching.feature_extractor import FeatureExtractor


class TestBasicExtraction:
    """Test basic feature extraction."""

    def test_extract_returns_all_fields(self):
        """Should return all expected fields."""
        extractor = FeatureExtractor()
        features = extractor.extract("海苔卷零食50g桶装儿童")

        assert "keywords" in features
        assert "category" in features
        assert "weight_value" in features
        assert "weight_unit" in features
        assert "package" in features
        assert "target" in features

    def test_extract_keywords(self):
        """Should extract meaningful keywords."""
        extractor = FeatureExtractor()
        features = extractor.extract("三只松鼠坚果礼盒装2024新款")

        keywords = features["keywords"]
        assert len(keywords) > 0
        # Should contain product-related terms
        assert "坚果" in keywords or "松鼠" in keywords or "礼盒" in keywords

    def test_keywords_filter_noise(self):
        """Should filter noise keywords like 爆款, 新品, 包邮."""
        extractor = FeatureExtractor()
        features = extractor.extract("爆款海苔卷零食包邮代发")

        keywords = features["keywords"]
        assert "爆款" not in keywords
        assert "包邮" not in keywords
        assert "代发" not in keywords


class TestWeightExtraction:
    """Test weight extraction."""

    def test_extract_weight_g(self):
        """Should extract weight in grams."""
        extractor = FeatureExtractor()
        features = extractor.extract("海苔卷零食50g桶装")

        assert features["weight_value"] == 50.0
        assert features["weight_unit"] == "g"

    def test_extract_weight_ke(self):
        """Should extract weight in 克."""
        extractor = FeatureExtractor()
        features = extractor.extract("坚果100克袋装")

        assert features["weight_value"] == 100.0
        assert features["weight_unit"] == "g"

    def test_extract_weight_kg(self):
        """Should extract weight in kg."""
        extractor = FeatureExtractor()
        features = extractor.extract("大米1kg袋装")

        assert features["weight_value"] == 1.0
        assert features["weight_unit"] == "kg"

    def test_extract_weight_ml(self):
        """Should extract volume in ml."""
        extractor = FeatureExtractor()
        features = extractor.extract("饮料500ml瓶装")

        assert features["weight_value"] == 500.0
        assert features["weight_unit"] == "ml"

    def test_extract_weight_decimal(self):
        """Should extract decimal weight."""
        extractor = FeatureExtractor()
        features = extractor.extract("咖啡豆2.5kg装")

        assert features["weight_value"] == 2.5
        assert features["weight_unit"] == "kg"

    def test_no_weight(self):
        """Should return 0/empty when no weight."""
        extractor = FeatureExtractor()
        features = extractor.extract("三只松鼠坚果礼盒装")

        assert features["weight_value"] == 0.0
        assert features["weight_unit"] == ""


class TestPackageExtraction:
    """Test package type extraction."""

    def test_extract_bag(self):
        """Should extract 袋装."""
        extractor = FeatureExtractor()
        features = extractor.extract("坚果零食袋装批发")

        assert features["package"] == "袋装"

    def test_extract_bucket(self):
        """Should extract 桶装."""
        extractor = FeatureExtractor()
        features = extractor.extract("海苔卷桶装即食")

        assert features["package"] == "桶装"

    def test_extract_box(self):
        """Should extract 盒装."""
        extractor = FeatureExtractor()
        features = extractor.extract("巧克力盒装礼盒")

        # "盒装" appears before "礼盒" in our keywords list
        assert features["package"] in ("盒装", "礼盒")

    def test_extract_gift_box(self):
        """Should extract 礼盒."""
        extractor = FeatureExtractor()
        features = extractor.extract("坚果礼盒装高端")

        assert features["package"] == "礼盒"

    def test_extract_loose(self):
        """Should extract 散装."""
        extractor = FeatureExtractor()
        features = extractor.extract("糖果散装称斤")

        assert features["package"] == "散装"

    def test_no_package(self):
        """Should return empty when no package info."""
        extractor = FeatureExtractor()
        features = extractor.extract("无线蓝牙耳机降噪")

        assert features["package"] == ""


class TestTargetExtraction:
    """Test target audience extraction."""

    def test_extract_children(self):
        """Should extract 儿童."""
        extractor = FeatureExtractor()
        features = extractor.extract("儿童零食营养饼干")

        assert features["target"] == "儿童"

    def test_extract_student(self):
        """Should extract 学生."""
        extractor = FeatureExtractor()
        features = extractor.extract("学生文具套装")

        assert features["target"] == "学生"

    def test_extract_office(self):
        """Should extract 办公室."""
        extractor = FeatureExtractor()
        features = extractor.extract("办公室零食小包装")

        assert features["target"] == "办公室"

    def test_extract_girl(self):
        """Should extract 女生."""
        extractor = FeatureExtractor()
        features = extractor.extract("女生礼物精选")

        assert features["target"] == "女生"

    def test_extract_elder(self):
        """Should extract 老人."""
        extractor = FeatureExtractor()
        features = extractor.extract("老人营养保健品")

        assert features["target"] == "老人"

    def test_no_target(self):
        """Should return empty when no target info."""
        extractor = FeatureExtractor()
        features = extractor.extract("无线蓝牙耳机降噪")

        assert features["target"] == ""


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_title(self):
        """Empty title should return defaults."""
        extractor = FeatureExtractor()
        features = extractor.extract("")

        assert features["keywords"] == []
        assert features["category"] == ""
        assert features["weight_value"] == 0.0

    def test_whitespace_title(self):
        """Whitespace-only title should return defaults."""
        extractor = FeatureExtractor()
        features = extractor.extract("   ")

        assert features["keywords"] == []

    def test_full_feature_title(self):
        """Title with all features should extract everything."""
        extractor = FeatureExtractor()
        features = extractor.extract("儿童海苔卷零食50g桶装")

        assert "儿童" in features["target"]
        assert features["package"] == "桶装"
        assert features["weight_value"] == 50.0
        assert len(features["keywords"]) > 0

    def test_same_category_products(self):
        """Similar products should share category."""
        extractor = FeatureExtractor()
        f1 = extractor.extract("三只松鼠坚果礼盒")
        f2 = extractor.extract("坚果零食混合装")

        # Both should be 食品 category
        assert f1["category"] == "食品"
        assert f2["category"] == "食品"

    def test_category_inference(self):
        """Should infer category from keywords."""
        extractor = FeatureExtractor()
        
        # Food
        f = extractor.extract("海苔卷零食大礼包")
        assert f["category"] == "食品"
        
        # Digital
        f = extractor.extract("无线蓝牙耳机降噪")
        assert f["category"] == "数码"
        
        # Unknown
        f = extractor.extract("xyz unknown")
        assert f["category"] == ""
