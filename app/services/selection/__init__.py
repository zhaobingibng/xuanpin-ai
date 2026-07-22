"""Selection orchestration package (Phase 37.1).

Exposes the DailySelectionPipeline — a stateless orchestration layer that
wires existing services (product acquisition → supplier matching →
opportunity scoring → daily selection report) into a single flow.
"""

from app.services.selection.daily_selection_pipeline import DailySelectionPipeline

__all__ = ["DailySelectionPipeline"]
