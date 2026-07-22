"""Mock 1688 supplier product data.

This module provides simulated 1688 product data for supply chain matching.
In production, this would be replaced by actual 1688 API/crawler data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Mock1688Product:
    """Simulated 1688 supplier product."""

    product_id: str
    title: str
    price: float  # 批发价
    min_order: int  # 最小起订量
    supplier_name: str
    supplier_location: str
    monthly_sales: int
    image_url: str | None = None
    url: str | None = None
    crawled_at: datetime | None = None


# Mock 1688 product catalog — covers common categories
MOCK_1688_CATALOG: list[Mock1688Product] = [
    # 蓝牙耳机
    Mock1688Product(
        product_id="1688_bt_001",
        title="无线蓝牙耳机入耳式降噪运动跑步超长续航",
        price=15.8,
        min_order=10,
        supplier_name="深圳市声科电子有限公司",
        supplier_location="广东深圳",
        monthly_sales=50000,
        image_url="https://cbu01.alicdn.com/img/bt_earphone_001.jpg",
    ),
    Mock1688Product(
        product_id="1688_bt_002",
        title="TWS真无线蓝牙耳机触控降噪双耳立体声",
        price=22.5,
        min_order=5,
        supplier_name="东莞市酷声电子厂",
        supplier_location="广东东莞",
        monthly_sales=30000,
        image_url="https://cbu01.alicdn.com/img/bt_earphone_002.jpg",
    ),
    # 手机壳
    Mock1688Product(
        product_id="1688_case_001",
        title="适用iPhone手机壳硅胶透明防摔保护套",
        price=2.5,
        min_order=50,
        supplier_name="义乌市优壳贸易有限公司",
        supplier_location="浙江义乌",
        monthly_sales=100000,
        image_url="https://cbu01.alicdn.com/img/phone_case_001.jpg",
    ),
    Mock1688Product(
        product_id="1688_case_002",
        title="华为手机壳新款液态硅胶全包防摔",
        price=3.2,
        min_order=30,
        supplier_name="深圳市壳王科技有限公司",
        supplier_location="广东深圳",
        monthly_sales=80000,
        image_url="https://cbu01.alicdn.com/img/phone_case_002.jpg",
    ),
    # 收纳用品
    Mock1688Product(
        product_id="1688_storage_001",
        title="桌面收纳盒化妆品整理置物架储物盒",
        price=5.8,
        min_order=20,
        supplier_name="台州市黄岩美塑模具厂",
        supplier_location="浙江台州",
        monthly_sales=40000,
        image_url="https://cbu01.alicdn.com/img/storage_001.jpg",
    ),
    Mock1688Product(
        product_id="1688_storage_002",
        title="折叠收纳箱衣柜整理储物箱大号有盖",
        price=8.5,
        min_order=10,
        supplier_name="金华市金东区顺发家居用品厂",
        supplier_location="浙江金华",
        monthly_sales=25000,
        image_url="https://cbu01.alicdn.com/img/storage_002.jpg",
    ),
    # 宠物用品
    Mock1688Product(
        product_id="1688_pet_001",
        title="宠物狗玩具球耐咬磨牙发声球泰迪金毛",
        price=3.5,
        min_order=30,
        supplier_name="平阳县宠爱宠物用品厂",
        supplier_location="浙江温州",
        monthly_sales=60000,
        image_url="https://cbu01.alicdn.com/img/pet_toy_001.jpg",
    ),
    Mock1688Product(
        product_id="1688_pet_002",
        title="猫砂盆全封闭猫厕所防外溅大号猫沙盆",
        price=18.0,
        min_order=5,
        supplier_name="台州市路桥优宠塑业有限公司",
        supplier_location="浙江台州",
        monthly_sales=15000,
        image_url="https://cbu01.alicdn.com/img/pet_litter_001.jpg",
    ),
    # 美妆
    Mock1688Product(
        product_id="1688_beauty_001",
        title="口红哑光雾面持久不脱色防水唇釉",
        price=4.5,
        min_order=20,
        supplier_name="广州市白云区美妆化妆品厂",
        supplier_location="广东广州",
        monthly_sales=45000,
        image_url="https://cbu01.alicdn.com/img/lipstick_001.jpg",
    ),
    Mock1688Product(
        product_id="1688_beauty_002",
        title="美妆蛋粉扑化妆 sponge 粉底液气垫",
        price=1.2,
        min_order=100,
        supplier_name="深圳市美尚美妆工具有限公司",
        supplier_location="广东深圳",
        monthly_sales=200000,
        image_url="https://cbu01.alicdn.com/img/beauty_sponge_001.jpg",
    ),
    # 家居
    Mock1688Product(
        product_id="1688_home_001",
        title="LED台灯护眼学习书桌阅读灯充电折叠",
        price=12.0,
        min_order=10,
        supplier_name="中山市古镇明辉照明电器厂",
        supplier_location="广东中山",
        monthly_sales=35000,
        image_url="https://cbu01.alicdn.com/img/desk_lamp_001.jpg",
    ),
    # 女装
    Mock1688Product(
        product_id="1688_fashion_001",
        title="夏季新款碎花连衣裙女中长款气质显瘦",
        price=35.0,
        min_order=5,
        supplier_name="广州市白云区新市美衣服装厂",
        supplier_location="广东广州",
        monthly_sales=20000,
        image_url="https://cbu01.alicdn.com/img/dress_001.jpg",
    ),
]


def get_1688_catalog() -> list[Mock1688Product]:
    """Return the full 1688 mock catalog."""
    return MOCK_1688_CATALOG.copy()


def search_1688_by_keyword(keyword: str, limit: int = 10) -> list[Mock1688Product]:
    """Search 1688 mock catalog by keyword in title."""
    keyword_lower = keyword.lower()
    results = [
        p for p in MOCK_1688_CATALOG
        if keyword_lower in p.title.lower()
    ]
    return results[:limit]
