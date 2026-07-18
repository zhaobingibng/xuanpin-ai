"""Crawler module — platform-specific web crawlers for product data."""

from app.crawler.base import BaseCrawler
from app.crawler.douyin import DouyinCrawler
from app.crawler.kuaishou import KuaishouCrawler
from app.crawler.manager import CrawlerManager
from app.crawler.xiaohongshu import XiaohongshuCrawler

__all__ = [
    "BaseCrawler",
    "CrawlerManager",
    "DouyinCrawler",
    "KuaishouCrawler",
    "XiaohongshuCrawler",
]
