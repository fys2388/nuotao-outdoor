"""A/B testing framework for image and content variants.

Tracks A/B test experiments for product images and content variants,
records metrics (CTR, CVR, engagement), and determines winners.

Design:
- Experiments group variants for comparison
- Variants track impressions, clicks, conversions
- Statistical significance calculation (simple z-test)
- Deterministic: no LLM, pure metric tracking

Usage:
    from app.services.ab_testing import get_ab_test_service

    service = get_ab_test_service()
    experiment = service.create_experiment(
        name="Main Image CTR Test",
        variants=["original", "generated_v1", "generated_v2"],
    )
    service.record_impression(experiment.id, "generated_v1")
    service.record_click(experiment.id, "generated_v1")
    results = service.get_results(experiment.id)
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class ExperimentStatus(str, Enum):
    """Status of an A/B test experiment."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class VariantMetrics:
    """Metrics for a single variant."""

    variant_name: str
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0

    @property
    def ctr(self) -> float:
        """Click-through rate."""
        return self.clicks / self.impressions if self.impressions > 0 else 0.0

    @property
    def cvr(self) -> float:
        """Conversion rate."""
        return self.conversions / self.clicks if self.clicks > 0 else 0.0

    @property
    def revenue_per_click(self) -> float:
        """Revenue per click."""
        return self.revenue / self.clicks if self.clicks > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "variant_name": self.variant_name,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "conversions": self.conversions,
            "revenue": self.revenue,
            "ctr": round(self.ctr, 4),
            "cvr": round(self.cvr, 4),
            "revenue_per_click": round(self.revenue_per_click, 2),
        }


@dataclass
class Experiment:
    """An A/B test experiment."""

    id: str
    name: str
    variants: list[str]
    status: ExperimentStatus = ExperimentStatus.RUNNING
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    description: str = ""
    product_id: str = ""
    metrics: dict[str, VariantMetrics] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Initialize metrics for each variant
        for variant in self.variants:
            if variant not in self.metrics:
                self.metrics[variant] = VariantMetrics(variant_name=variant)

    def add_impression(self, variant: str) -> None:
        """Record an impression for a variant."""
        if variant in self.metrics:
            self.metrics[variant].impressions += 1

    def add_click(self, variant: str) -> None:
        """Record a click for a variant."""
        if variant in self.metrics:
            self.metrics[variant].clicks += 1

    def add_conversion(self, variant: str, revenue: float = 0.0) -> None:
        """Record a conversion for a variant."""
        if variant in self.metrics:
            self.metrics[variant].conversions += 1
            self.metrics[variant].revenue += revenue

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "variants": self.variants,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "description": self.description,
            "product_id": self.product_id,
            "metrics": {
                name: m.to_dict() for name, m in self.metrics.items()
            },
        }


# ---------------------------------------------------------------------------
# Statistical calculation
# ---------------------------------------------------------------------------


def calculate_z_score(
    clicks_a: int,
    impressions_a: int,
    clicks_b: int,
    impressions_b: int,
) -> float:
    """Calculate z-score for comparing two CTRs.

    Uses a two-proportion z-test for significance.
    """
    if impressions_a == 0 or impressions_b == 0:
        return 0.0

    p_a = clicks_a / impressions_a
    p_b = clicks_b / impressions_b

    # Pooled proportion
    p_pool = (clicks_a + clicks_b) / (impressions_a + impressions_b)

    # Standard error
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / impressions_a + 1 / impressions_b))

    if se == 0:
        return 0.0

    z = (p_a - p_b) / se
    return z


def is_significant(
    z_score: float,
    alpha: float = 0.05,
) -> bool:
    """Check if z-score is statistically significant.

    Args:
        z_score: The z-score from the test.
        alpha: Significance level (0.05 = 95% confidence).

    Returns:
        True if the result is statistically significant.
    """
    # Two-tailed test: critical z-value for 95% confidence is ~1.96
    critical_z = 1.96 if alpha == 0.05 else 1.645  # 90% = 1.645
    return abs(z_score) > critical_z


def get_winner(
    metrics: dict[str, VariantMetrics],
    alpha: float = 0.05,
) -> str | None:
    """Determine the winning variant based on CTR.

    Returns the variant with the highest CTR if statistically significant,
    otherwise returns None.
    """
    if len(metrics) < 2:
        return None

    variants = list(metrics.keys())
    best_variant = None
    best_ctr = 0.0

    for v in variants:
        m = metrics[v]
        if m.ctr > best_ctr:
            best_ctr = m.ctr
            best_variant = v

    if best_variant is None:
        return None

    # Check significance against the next best variant
    for v in variants:
        if v == best_variant:
            continue
        z = calculate_z_score(
            metrics[best_variant].clicks,
            metrics[best_variant].impressions,
            metrics[v].clicks,
            metrics[v].impressions,
        )
        if not is_significant(z, alpha):
            return None  # Not significant

    return best_variant


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ABTestService:
    """Service for managing A/B test experiments."""

    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    def create_experiment(
        self,
        name: str,
        variants: list[str],
        *,
        description: str = "",
        product_id: str = "",
    ) -> Experiment:
        """Create a new A/B test experiment.

        Args:
            name: Experiment name.
            variants: List of variant names.
            description: Optional description.
            product_id: Optional product ID for context.

        Returns:
            The created Experiment.
        """
        if len(variants) < 2:
            raise ValueError("A/B test requires at least 2 variants")

        experiment = Experiment(
            id=str(uuid.uuid4()),
            name=name,
            variants=variants,
            description=description,
            product_id=product_id,
        )
        self._experiments[experiment.id] = experiment
        logger.info(
            "A/B test created: %s (%s) with %d variants",
            name, experiment.id, len(variants),
        )
        return experiment

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)

    def list_experiments(
        self,
        *,
        status: ExperimentStatus | None = None,
        product_id: str | None = None,
    ) -> list[Experiment]:
        """List experiments, optionally filtered."""
        results = list(self._experiments.values())
        if status:
            results = [e for e in results if e.status == status]
        if product_id:
            results = [e for e in results if e.product_id == product_id]
        return results

    def record_impression(
        self,
        experiment_id: str,
        variant: str,
        *,
        impressions: int = 1,
    ) -> bool:
        """Record impressions for a variant."""
        experiment = self._experiments.get(experiment_id)
        if not experiment or variant not in experiment.metrics:
            return False
        for _ in range(impressions):
            experiment.add_impression(variant)
        return True

    def record_click(
        self,
        experiment_id: str,
        variant: str,
        *,
        clicks: int = 1,
    ) -> bool:
        """Record clicks for a variant."""
        experiment = self._experiments.get(experiment_id)
        if not experiment or variant not in experiment.metrics:
            return False
        for _ in range(clicks):
            experiment.add_click(variant)
        return True

    def record_conversion(
        self,
        experiment_id: str,
        variant: str,
        *,
        conversions: int = 1,
        revenue: float = 0.0,
    ) -> bool:
        """Record conversions for a variant."""
        experiment = self._experiments.get(experiment_id)
        if not experiment or variant not in experiment.metrics:
            return False
        for _ in range(conversions):
            experiment.add_conversion(variant, revenue / conversions if conversions > 0 else 0)
        return True

    def complete_experiment(self, experiment_id: str) -> bool:
        """Mark an experiment as completed."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return False
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = time.time()
        return True

    def cancel_experiment(self, experiment_id: str) -> bool:
        """Cancel an experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return False
        experiment.status = ExperimentStatus.CANCELLED
        experiment.completed_at = time.time()
        return True

    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment."""
        if experiment_id in self._experiments:
            del self._experiments[experiment_id]
            return True
        return False

    def get_results(self, experiment_id: str) -> dict[str, Any]:
        """Get results for an experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return {"error": "Experiment not found"}

        metrics = experiment.metrics
        winner = get_winner(metrics)

        return {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "status": experiment.status.value,
            "variants": experiment.variants,
            "metrics": {
                name: m.to_dict() for name, m in metrics.items()
            },
            "winner": winner,
            "is_significant": winner is not None,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get A/B test service statistics."""
        running = sum(1 for e in self._experiments.values() if e.status == ExperimentStatus.RUNNING)
        completed = sum(1 for e in self._experiments.values() if e.status == ExperimentStatus.COMPLETED)
        total_impressions = sum(
            m.impressions for e in self._experiments.values() for m in e.metrics.values()
        )
        total_clicks = sum(
            m.clicks for e in self._experiments.values() for m in e.metrics.values()
        )
        return {
            "total_experiments": len(self._experiments),
            "running": running,
            "completed": completed,
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
        }

    def export(self) -> str:
        """Export all experiments as JSON."""
        import json

        data = {eid: e.to_dict() for eid, e in self._experiments.items()}
        return json.dumps(data, indent=2, ensure_ascii=False)

    def import_json(self, json_str: str) -> int:
        """Import experiments from JSON."""
        import json

        data = json.loads(json_str)
        count = 0
        for eid, exp_data in data.items():
            experiment = Experiment(
                id=eid,
                name=exp_data["name"],
                variants=exp_data["variants"],
                status=ExperimentStatus(exp_data.get("status", "running")),
                created_at=exp_data.get("created_at", time.time()),
                completed_at=exp_data.get("completed_at"),
                description=exp_data.get("description", ""),
                product_id=exp_data.get("product_id", ""),
            )
            # Restore metrics
            for v_name, m_data in exp_data.get("metrics", {}).items():
                if v_name in experiment.metrics:
                    experiment.metrics[v_name] = VariantMetrics(
                        variant_name=v_name,
                        impressions=m_data.get("impressions", 0),
                        clicks=m_data.get("clicks", 0),
                        conversions=m_data.get("conversions", 0),
                        revenue=m_data.get("revenue", 0.0),
                    )
            self._experiments[eid] = experiment
            count += 1
        return count


# ---------------------------------------------------------------------------
# Global service instance
# ---------------------------------------------------------------------------

_service: ABTestService | None = None


def get_ab_test_service() -> ABTestService:
    """Get or create the global A/B test service."""
    global _service
    if _service is None:
        _service = ABTestService()
    return _service


def format_experiment_report(service: ABTestService, experiment_id: str) -> str:
    """Format experiment results as a report."""
    results = service.get_results(experiment_id)
    if "error" in results:
        return f"Error: {results['error']}"

    lines = [
        f"A/B Test Report: {results['name']}",
        f"  ID: {results['experiment_id']}",
        f"  Status: {results['status']}",
        f"  Winner: {results['winner'] or 'None (not significant)'}",
        f"  Significant: {'Yes' if results['is_significant'] else 'No'}",
        "",
        "Variant Metrics:",
    ]

    for v_name, m in results["metrics"].items():
        lines.append(f"  {v_name}:")
        lines.append(f"    Impressions: {m['impressions']}")
        lines.append(f"    Clicks: {m['clicks']}")
        lines.append(f"    CTR: {m['ctr']:.2%}")
        lines.append(f"    Conversions: {m['conversions']}")
        lines.append(f"    CVR: {m['cvr']:.2%}")
        lines.append(f"    Revenue: ${m['revenue']:.2f}")
        lines.append("")

    return "\n".join(lines)
