"""1688 Event Data Parser.

Parses captured events (postMessage, CustomEvent) from 1688 search pages
into standardized product data structures.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ParsedProduct:
    """Unified product data structure from 1688 events."""

    title: str = ""
    price: float = 0.0
    sales: int = 0
    shop_name: str = ""
    offer_id: str = ""
    url: str = ""
    image: str = ""
    source: str = "1688"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "price": self.price,
            "sales": self.sales,
            "shop_name": self.shop_name,
            "offer_id": self.offer_id,
            "url": self.url,
            "image": self.image,
            "source": self.source,
        }


class EventParser:
    """Parse 1688 captured events into product data.
    
    Supports multiple event types:
    - offerV2: CustomEvent from search:firstDataReady:offerV2
    - message: postMessage with getOfferList action
    - dispatch: dispatchEvent hook capture
    
    Usage:
        parser = EventParser()
        products = parser.parse_events(events)
    """

    def parse_events(self, events: list[dict]) -> list[ParsedProduct]:
        """Parse a list of captured events into products.
        
        Args:
            events: List of event dicts from window.__1688_debug
        
        Returns:
            List of ParsedProduct
        """
        if not events:
            return []
        
        products: list[ParsedProduct] = []
        
        for event in events:
            if not isinstance(event, dict):
                continue
            
            event_type = event.get("type", "")
            
            try:
                if event_type == "offerV2":
                    parsed = self.parse_offer_event(event)
                    products.extend(parsed)
                
                elif event_type == "message":
                    action = event.get("action", "")
                    if action == "getOfferList":
                        data = event.get("data", {})
                        extracted = self.extract_products(data)
                        products.extend(extracted)
                
                elif event_type == "dispatch":
                    event_type_name = event.get("eventType", "")
                    if "offerV2" in event_type_name or "firstDataReady" in event_type_name:
                        detail = event.get("detail", {})
                        if detail:
                            extracted = self.extract_products(detail)
                            products.extend(extracted)
            
            except Exception as e:
                logger.debug("[EventParser] Event parse error: {}", e)
                continue
        
        # Deduplicate by offer_id
        seen_ids: set[str] = set()
        unique_products: list[ParsedProduct] = []
        for p in products:
            key = p.offer_id or p.title
            if key and key not in seen_ids:
                seen_ids.add(key)
                unique_products.append(p)
        
        return unique_products

    def parse_offer_event(self, event: dict) -> list[ParsedProduct]:
        """Parse an offerV2 CustomEvent.
        
        Expected structure:
        {
            "type": "offerV2",
            "detail": {
                "reqParams": {...},
                "response": {
                    "data": {
                        "offerList": [...]
                    }
                },
                "timeCost": 100
            }
        }
        
        Args:
            event: Event dict with type='offerV2'
        
        Returns:
            List of ParsedProduct
        """
        detail = event.get("detail", {})
        if not detail:
            return []
        
        # Try multiple data paths
        data = None
        
        # Path 1: detail.response.data
        response = detail.get("response", {})
        if isinstance(response, dict):
            data = response.get("data", {})
        
        # Path 2: detail.data
        if not data:
            data = detail.get("data", {})
        
        # Path 3: detail itself contains offerList
        if not data:
            data = detail
        
        return self.extract_products(data)

    def extract_products(self, data: Any) -> list[ParsedProduct]:
        """Extract products from various 1688 data structures.
        
        Supports:
        - data.offerList
        - data.result.list.items
        - data.data.offerList
        - Nested structures
        
        Args:
            data: Raw data dict from 1688 API/event
        
        Returns:
            List of ParsedProduct
        """
        if not data or not isinstance(data, dict):
            return []
        
        # Find the offer list from various possible locations
        offer_list = self._find_offer_list(data)
        
        if not offer_list:
            return []
        
        products: list[ParsedProduct] = []
        
        for item in offer_list:
            if not isinstance(item, dict):
                continue
            
            product = self._parse_single_product(item)
            if product and product.title:
                products.append(product)
        
        return products

    def _find_offer_list(self, data: dict) -> list:
        """Find offer list from various data structures.
        
        Args:
            data: Data dict
        
        Returns:
            List of offer items, or empty list
        """
        # Direct offerList
        offer_list = data.get("offerList", [])
        if offer_list:
            return offer_list
        
        # data.data.offerList
        inner = data.get("data", {})
        if isinstance(inner, dict):
            offer_list = inner.get("offerList", [])
            if offer_list:
                return offer_list
            
            # data.data.result.list.items
            result = inner.get("result", {})
            if isinstance(result, dict):
                items = result.get("list", {}).get("items", [])
                if items:
                    return items
            
            # data.data.offerV2
            offer_list = inner.get("offerV2", [])
            if offer_list:
                return offer_list
        
        # data.response.data.offerList
        response = data.get("response", {})
        if isinstance(response, dict):
            resp_data = response.get("data", {})
            if isinstance(resp_data, dict):
                offer_list = resp_data.get("offerList", [])
                if offer_list:
                    return offer_list
        
        return []

    def _parse_single_product(self, item: dict) -> ParsedProduct | None:
        """Parse a single product item.
        
        Handles multiple field name variations for robustness.
        
        Args:
            item: Single offer item dict
        
        Returns:
            ParsedProduct or None if no title found
        """
        try:
            # Get the offer object (may be nested under 'offer' key)
            offer = item.get("offer", item)
            if not isinstance(offer, dict):
                return None
            
            # Title - try multiple field names
            title = self._get_first(offer, [
                "title", "subject", "name", "offerTitle"
            ])
            if not title:
                return None
            
            # Price
            price = self._extract_price(offer)
            
            # Sales
            sales = self._extract_int(offer, [
                "quantitySumMonth", "sales", "monthlySales", 
                "totalSold", "saleCount"
            ])
            
            # Shop name
            shop_name = self._get_first(offer, [
                "companyName", "supplierName", "shopName", "sellerName"
            ])
            
            # Offer ID
            offer_id = str(self._get_first(offer, [
                "offerId", "id", "offer_id"
            ]) or "")
            
            # URL
            url = self._get_first(offer, [
                "detailUrl", "url", "link", "offerUrl"
            ])
            if url and not url.startswith("http"):
                url = "https://detail.1688.com" + url
            
            # Image
            image = self._get_first(offer, [
                "image", "imageUrl", "picUrl", "img", "mainImage"
            ])
            
            # Generate offer_id if not found
            if not offer_id:
                id_source = url or title
                offer_id = hashlib.md5(id_source.encode()).hexdigest()[:12]
            
            return ParsedProduct(
                title=title,
                price=price,
                sales=sales,
                shop_name=shop_name or "",
                offer_id=offer_id,
                url=url or "",
                image=image or "",
                source="1688",
            )
        
        except Exception as e:
            logger.debug("[EventParser] Product parse error: {}", e)
            return None

    def _get_first(self, data: dict, keys: list[str]) -> Any:
        """Get first non-empty value from dict by key list.
        
        Args:
            data: Source dict
            keys: List of possible key names
        
        Returns:
            First found value, or None
        """
        for key in keys:
            value = data.get(key)
            if value is not None and value != "":
                return value
        return None

    def _extract_price(self, offer: dict) -> float:
        """Extract price from offer data.
        
        Handles:
        - Direct price field
        - priceInfo object
        - String prices with currency symbols
        
        Args:
            offer: Offer dict
        
        Returns:
            Price as float, or 0.0
        """
        # Try priceInfo object first
        price_info = offer.get("priceInfo", {})
        if isinstance(price_info, dict):
            price_str = self._get_first(price_info, [
                "price", "value", "priceValue", "displayPrice"
            ])
            if price_str:
                return self._parse_price_str(str(price_str))
        
        # Try direct price field
        price = self._get_first(offer, [
            "price", "unitPrice", "refPrice"
        ])
        if price:
            return self._parse_price_str(str(price))
        
        return 0.0

    def _parse_price_str(self, price_str: str) -> float:
        """Parse price string, removing currency symbols.
        
        Args:
            price_str: Price string like "¥29.90" or "29.90元"
        
        Returns:
            Price as float, or 0.0
        """
        # Remove common currency symbols and whitespace
        cleaned = "".join(
            c for c in price_str if c.isdigit() or c == "."
        )
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                pass
        return 0.0

    def _extract_int(self, data: dict, keys: list[str]) -> int:
        """Extract integer value from dict.
        
        Args:
            data: Source dict
            keys: List of possible key names
        
        Returns:
            Integer value, or 0
        """
        value = self._get_first(data, keys)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                pass
        return 0
