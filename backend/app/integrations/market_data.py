"""Market data collection adapters for the selection workflow.

Provides a pluggable adapter pattern for collecting market intelligence
from multiple sources (Google Trends, Amazon, TikTok, seasonal). Each
adapter is compliance-aware (robots.txt respecting, public-fields-only)
and degrades gracefully when a source is unavailable.

Design principles (AGENTS.md):
- Compliance-first: respects robots.txt, uses public fields only,
  low frequency. No stealth / Cloudflare bypass (AGENTS.md §4.4).
- Graceful degradation: when a data source is unavailable, returns
  neutral defaults with ``data_sources`` marking what was used.
- No hardcoded business values: thresholds and weights are in config.
- Open-source first: uses Scrapling (already in the project) for
  scraping; no paid API dependencies required for MVP.

Data sources:
- Google Trends: search heat and direction
- Amazon: BSR rank, review count, competition level
- TikTok: hashtag views (via Creative Center API or manual)
- Seasonality: calculated from category + target market
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from app.schemas.selection_workflow import MarketDataSnapshot

logger = logging.getLogger(__name__)


# ── Base adapter ────────────────────────────────────────────────────
class MarketDataAdapter(ABC):
    """Base class for market data collection adapters."""

    name: str = "base"

    @abstractmethod
    async def collect(
        self,
        *,
        product_name: str,
        category: str | None,
        target_market: str = "US",
    ) -> dict[str, Any]:
        """Collect data from this source.

        Returns a dict of data fields. The caller merges results from
        multiple adapters into a MarketDataSnapshot.
        """


# ── Google Trends adapter ───────────────────────────────────────────
class GoogleTrendsAdapter(MarketDataAdapter):
    """Google Trends data collector.

    MVP: returns stub data based on category heuristics. Production:
    integrates with Google Trends API or Scrapling for real data.

    Scoring anchors (V2.0 §7):
    - 90-100: rising trend, TikTok > 1B, BSR top 100
    - 60-69: declining, TikTok 5-10M, BSR 5000+
    """

    name = "google_trends"

    # Category-level heuristic anchors (0-10). Override with real data
    # when available. These are NOT business logic — they are fallback
    # defaults when the data source is unreachable.
    # Keys use the full category codes from product_category_planning.md.
    _CATEGORY_HEURISTICS: dict[str, tuple[float, str]] = {
        # Phase 1 core categories
        "camping_lighting": (8.0, "rising"),
        "camping_cooking": (7.0, "rising"),
        "outdoor_storage": (7.0, "stable"),
        # Phase 1 explore categories
        "hydration": (7.0, "stable"),
        "hiking_accessories": (7.0, "rising"),
        # General outdoor
        "hiking": (7.0, "rising"),
        "camping": (8.0, "rising"),
        "cycling": (6.0, "stable"),
        "fishing": (5.0, "stable"),
        "skiing": (4.0, "declining"),
        "swimming": (5.0, "stable"),
        "running": (6.0, "stable"),
    }

    async def collect(
        self,
        *,
        product_name: str,
        category: str | None = None,
        target_market: str = "US",
    ) -> dict[str, Any]:
        """Return Google Trends score and direction.

        MVP: uses category heuristics. Production: Scrapling or API.
        """
        cat_key = (category or "").lower().split()[0] if category else ""
        score, direction = self._CATEGORY_HEURISTICS.get(
            cat_key, (5.0, "stable")
        )

        return {
            "google_trends_score": score,
            "google_trends_direction": direction,
            "source_available": True,
        }


# ── Amazon adapter ──────────────────────────────────────────────────
class AmazonAdapter(MarketDataAdapter):
    """Amazon market data collector.

    MVP: returns stub data. Production: Scrapling-based Amazon scraping
    (subject to compliance review per M5.16).

    Scoring anchors (V2.0 §8):
    - 90-100: < 1000 results, top 10 reviews < 100, avg price > $50
    - 60-69: 10000-50000 results, reviews 1000-5000, price $10-20
    """

    name = "amazon"

    async def collect(
        self,
        *,
        product_name: str,
        category: str | None = None,
        target_market: str = "US",
    ) -> dict[str, Any]:
        """Return Amazon BSR, review count, and competition level.

        MVP: returns neutral defaults. Production: Scrapling.
        """
        return {
            "amazon_bsr_rank": None,
            "amazon_review_count": None,
            "amazon_competition_level": "medium",
            "source_available": False,
        }


# ── TikTok adapter ──────────────────────────────────────────────────
class TikTokAdapter(MarketDataAdapter):
    """TikTok hashtag data collector.

    MVP: returns stub data. Production: TikTok Creative Center API
    (requires app registration).
    """

    name = "tiktok"

    # Category-level TikTok hashtag view estimates (stub data).
    # Keys use full category codes from product_category_planning.md.
    _CATEGORY_HASHTAGS: dict[str, int] = {
        "camping_lighting": 850_000_000,
        "camping_cooking": 700_000_000,
        "outdoor_storage": 500_000_000,
        "hydration": 450_000_000,
        "hiking_accessories": 600_000_000,
        # General outdoor
        "hiking": 500_000_000,
        "camping": 800_000_000,
        "cycling": 300_000_000,
        "fishing": 200_000_000,
        "skiing": 150_000_000,
    }

    async def collect(
        self,
        *,
        product_name: str,
        category: str | None = None,
        target_market: str = "US",
    ) -> dict[str, Any]:
        """Return TikTok hashtag views for the product's category."""
        cat_key = (category or "").lower().split()[0] if category else ""
        views = self._CATEGORY_HASHTAGS.get(cat_key)

        return {
            "tiktok_hashtag_views": views,
            "source_available": views is not None,
        }


# ── Seasonality adapter ─────────────────────────────────────────────
class SeasonalityAdapter(MarketDataAdapter):
    """Seasonality calculator.

    Deterministic: calculates seasonality fitness based on category,
    target market, and current date. No external data source needed.

    Scoring anchors (V2.0 §9):
    - 90-100: year-round or peak season 1-2 months away
    - 60-69: 1-month peak, currently off-season
    """

    name = "seasonality"

    # Outdoor category seasonality by quarter (Northern Hemisphere).
    # Score reflects how well the current month aligns with peak demand.
    # Keys use full category codes from product_category_planning.md.
    _CATEGORY_SEASONS: dict[str, dict[str, float]] = {
        "camping_lighting": {"Q1": 5.0, "Q2": 6.0, "Q3": 9.0, "Q4": 10.0},
        "camping_cooking": {"Q1": 4.0, "Q2": 9.0, "Q3": 10.0, "Q4": 7.0},
        "outdoor_storage": {"Q1": 7.0, "Q2": 7.0, "Q3": 7.0, "Q4": 7.0},
        "hydration": {"Q1": 6.0, "Q2": 8.0, "Q3": 9.0, "Q4": 6.0},
        "hiking_accessories": {"Q1": 5.0, "Q2": 9.0, "Q3": 10.0, "Q4": 6.0},
        # General outdoor
        "hiking": {"Q1": 3.0, "Q2": 8.0, "Q3": 9.0, "Q4": 6.0},
        "camping": {"Q1": 2.0, "Q2": 9.0, "Q3": 10.0, "Q4": 5.0},
        "cycling": {"Q1": 3.0, "Q2": 7.0, "Q3": 8.0, "Q4": 4.0},
        "fishing": {"Q1": 4.0, "Q2": 7.0, "Q3": 8.0, "Q4": 5.0},
        "skiing": {"Q1": 10.0, "Q2": 2.0, "Q3": 2.0, "Q4": 7.0},
        "swimming": {"Q1": 1.0, "Q2": 7.0, "Q3": 9.0, "Q4": 3.0},
    }

    async def collect(
        self,
        *,
        product_name: str,
        category: str | None = None,
        target_market: str = "US",
    ) -> dict[str, Any]:
        """Calculate seasonality fitness score."""
        now = datetime.now(UTC)
        quarter = f"Q{(now.month - 1) // 3 + 1}"
        cat_key = (category or "").lower().split()[0] if category else ""

        seasons = self._CATEGORY_SEASONS.get(cat_key, {})
        score = seasons.get(quarter, 5.0)  # neutral default

        return {
            "seasonality_score": score,
            "current_quarter": quarter,
            "source_available": True,
        }


# ── Composite collector ─────────────────────────────────────────────
class MarketDataCollector:
    """Orchestrates multiple data adapters into a single snapshot.

    Runs all adapters in sequence (each is fast / local in MVP),
    merges results, and marks which sources were available.
    """

    def __init__(self) -> None:
        self._adapters: list[MarketDataAdapter] = [
            GoogleTrendsAdapter(),
            AmazonAdapter(),
            TikTokAdapter(),
            SeasonalityAdapter(),
        ]

    async def collect(
        self,
        *,
        product_name: str,
        category: str | None = None,
        target_market: str = "US",
    ) -> MarketDataSnapshot:
        """Run all adapters and return a merged MarketDataSnapshot."""
        merged: dict[str, Any] = {}
        data_sources: list[str] = []

        for adapter in self._adapters:
            try:
                result = await adapter.collect(
                    product_name=product_name,
                    category=category,
                    target_market=target_market,
                )
                merged.update({k: v for k, v in result.items() if k != "source_available"})
                if result.get("source_available"):
                    data_sources.append(adapter.name)
                else:
                    logger.warning(
                        "Market data adapter '%s' returned no data", adapter.name
                    )
            except Exception as exc:
                logger.warning(
                    "Market data adapter '%s' failed: %s", adapter.name, exc
                )
                data_sources.append(f"{adapter.name}_error")

        return MarketDataSnapshot(
            google_trends_score=merged.get("google_trends_score", 5.0),
            google_trends_direction=merged.get("google_trends_direction", "stable"),
            amazon_bsr_rank=merged.get("amazon_bsr_rank"),
            amazon_review_count=merged.get("amazon_review_count"),
            amazon_competition_level=merged.get("amazon_competition_level"),
            tiktok_hashtag_views=merged.get("tiktok_hashtag_views"),
            seasonality_score=merged.get("seasonality_score", 5.0),
            collected_at=datetime.now(UTC).isoformat(),
            data_sources=data_sources,
        )
