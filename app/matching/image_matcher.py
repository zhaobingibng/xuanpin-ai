"""ImageMatcher — 商品图片感知哈希相似度（dHash）。

使用 dHash（差异哈希）进行轻量级图片相似度对比。
不依赖在线 API，纯本地计算，基于 Pillow。

支持输入：PIL Image、本地文件路径、图片 URL、bytes。

Usage:
    matcher = ImageMatcher()

    # PIL Image
    score = matcher.calculate_similarity(img1, img2)

    # 本地文件
    score = matcher.calculate_similarity("a.jpg", "b.png")

    # 图片 URL
    score = matcher.calculate_similarity("https://.../a.jpg", "https://.../b.jpg")

    # 混合输入
    score = matcher.calculate_similarity(img, "https://.../b.jpg")
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


# ── Pillow check ──────────────────────────────────────────────

try:
    from PIL import Image as _PILImage
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False


# ── ImageMatcher ──────────────────────────────────────────────

class ImageMatcher:
    """商品图片感知哈希相似度计算器。

    使用 dHash（差异哈希）算法：
    1. 将图片缩放到 9×8 灰度
    2. 比较相邻像素生成 64-bit 哈希
    3. 通过汉明距离计算相似度 [0, 1]

    Attributes:
        HASH_SIZE: dHash 哈希尺寸 (默认 8 → 64-bit)
    """

    HASH_SIZE = 8  # 8×8 = 64 bit hash

    def __init__(self) -> None:
        if not HAS_PIL:  # pragma: no cover
            raise RuntimeError(
                "Pillow is required for ImageMatcher. Install with: pip install Pillow"
            )

    # ── Public API ────────────────────────────────────────────

    def calculate_similarity(
        self,
        source_a: "str | Path | PILImage | bytes | None",
        source_b: "str | Path | PILImage | bytes | None",
    ) -> float:
        """计算两张图片的相似度。

        Args:
            source_a: 图片 A，支持:
                - PIL Image 对象
                - 本地文件路径 (str / Path)
                - 图片 URL (以 http:// 或 https:// 开头)
                - bytes 数据
                - None → 返回 0.0
            source_b: 图片 B，支持同上类型。

        Returns:
            相似度 [0, 1]，1.0 表示完全相同，0.0 表示完全不同。
            任一输入为 None 或加载失败时返回 0.0。
        """
        if source_a is None or source_b is None:
            return 0.0

        img_a = self._load_image(source_a)
        img_b = self._load_image(source_b)

        if img_a is None or img_b is None:
            return 0.0

        hash_a = self._compute_dhash(img_a)
        hash_b = self._compute_dhash(img_b)

        distance = self._hamming_distance(hash_a, hash_b)
        return self._similarity_from_hamming(distance)

    def compute_hash(
        self,
        source: "str | Path | PILImage | bytes | None",
    ) -> str | None:
        """计算单张图片的 dHash。

        Args:
            source: 图片输入，支持类型同 calculate_similarity。

        Returns:
            16-char hex hash string，失败返回 None。
        """
        if source is None:
            return None
        img = self._load_image(source)
        if img is None:
            return None
        return self._compute_dhash(img)

    # ── dHash computation ─────────────────────────────────────

    def _compute_dhash(self, image: "PILImage") -> str:
        """计算 dHash（差异哈希）。

        流程：
        1. 缩放为 9×8 的灰度图（宽度多一列用于相邻比较）
        2. 水平方向比较相邻像素 → 64 bits
        3. 转换为 16-char hex 字符串

        Returns:
            16-char hex string (64-bit hash)。
        """
        size = self.HASH_SIZE
        resized = image.convert("L").resize((size + 1, size), _PILImage.LANCZOS)
        pixels = list(resized.getdata())

        bits: list[int] = []
        for row in range(size):
            for col in range(size):
                left = pixels[row * (size + 1) + col]
                right = pixels[row * (size + 1) + col + 1]
                bits.append(1 if left > right else 0)

        hash_int = 0
        for bit in bits:
            hash_int = (hash_int << 1) | bit

        return format(hash_int, f"0{size * 2}x")

    # ── Image loading ─────────────────────────────────────────

    def _load_image(
        self,
        source: "str | Path | PILImage | bytes",
    ) -> "PILImage | None":
        """从多种输入格式加载 PIL Image。

        支持:
        - PIL Image → 直接返回
        - bytes → 用 BytesIO 解码
        - str/Path → 本地文件
        - URL (http/https) → 下载

        Returns:
            PIL Image，失败返回 None。
        """
        # Already a PIL Image
        if hasattr(source, "convert"):
            return source  # type: ignore[return-value]

        if isinstance(source, bytes):
            return self._load_from_bytes(source)

        if isinstance(source, (str, Path)):
            s = str(source)
            if s.startswith(("http://", "https://")):
                return self._load_from_url(s)
            return self._load_from_path(s)

        return None

    def _load_from_bytes(self, data: bytes) -> "PILImage | None":
        """从 bytes 加载图片。"""
        try:
            return _PILImage.open(io.BytesIO(data))
        except Exception as exc:
            logger.debug("[ImageMatcher] Failed to load from bytes: {}", exc)
            return None

    def _load_from_path(self, path: str) -> "PILImage | None":
        """从本地文件路径加载图片。"""
        try:
            p = Path(path)
            if not p.exists():
                logger.debug("[ImageMatcher] File not found: {}", path)
                return None
            return _PILImage.open(p)
        except Exception as exc:
            logger.debug("[ImageMatcher] Failed to load from path '{}': {}", path, exc)
            return None

    def _load_from_url(self, url: str) -> "PILImage | None":
        """从 URL 下载图片。"""
        try:
            import httpx
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            return _PILImage.open(io.BytesIO(resp.content))
        except Exception as exc:
            logger.debug("[ImageMatcher] Failed to download image from '{}': {}", url[:80], exc)
            return None

    # ── Hamming distance & similarity ─────────────────────────

    @staticmethod
    def _hamming_distance(hash_a: str, hash_b: str) -> int:
        """计算两个 hex hash 之间的汉明距离。

        Returns:
            不同 bit 的数量 (0-64)。
        """
        if len(hash_a) != len(hash_b):
            return 64
        xor = int(hash_a, 16) ^ int(hash_b, 16)
        return xor.bit_count()

    def _similarity_from_hamming(self, distance: int) -> float:
        """将汉明距离转换为相似度 [0, 1]."""
        max_bits = self.HASH_SIZE * self.HASH_SIZE  # 64
        if max_bits == 0:
            return 0.0
        return 1.0 - (distance / max_bits)
