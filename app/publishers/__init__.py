"""发布模块 —— MockPublisher 模拟发布平台。

Usage::

    from app.publishers import MockPublisher

    pub = MockPublisher()
    result = await pub.publish(context)
"""

from app.publishers.mock_publisher import MockPublisher, PublishContext, PublishResult

__all__ = [
    "MockPublisher",
    "PublishContext",
    "PublishResult",
]
