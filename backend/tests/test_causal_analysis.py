"""
Tests for the domain-cost subgroup breakdown service (causal_analysis.py).

Verifies the pandas.groupby-based descriptive analytics that replaced the
former DoWhy backdoor regression. No causal claims are made; tests assert
shape correctness, edge cases, and arithmetic.
"""

import pytest

from app.services.causal_analysis import _compute_breakdown, run_domain_cost_breakdown


class TestComputeBreakdownEmpty:
    def test_empty_rows_returns_zero_n_with_note(self):
        result = _compute_breakdown([])
        assert result["n"] == 0
        assert result["n_sensitive_domain"] == 0
        assert result["n_general"] == 0
        assert result["tiers"] == []
        assert result["cost_delta_usd"] is None
        assert "No requests yet" in result["note"]
        assert result["method"] == "subgroup_mean_comparison"


class TestComputeBreakdownInsufficientGroups:
    def test_all_sensitive_returns_null_delta(self):
        rows = [
            {"domain": "legal", "cost_usd": 0.0025, "complexity_score": 0.5},
            {"domain": "medical", "cost_usd": 0.0025, "complexity_score": 0.7},
        ]
        result = _compute_breakdown(rows)
        assert result["n"] == 2
        assert result["n_sensitive_domain"] == 2
        assert result["n_general"] == 0
        assert result["cost_delta_usd"] is None
        assert "Need both" in result["note"]

    def test_all_general_returns_null_delta(self):
        rows = [
            {"domain": "general", "cost_usd": 0.0001, "complexity_score": 0.1},
            {"domain": "technical", "cost_usd": 0.0002, "complexity_score": 0.3},
        ]
        result = _compute_breakdown(rows)
        assert result["n_general"] == 2
        assert result["n_sensitive_domain"] == 0
        assert result["cost_delta_usd"] is None


class TestComputeBreakdownArithmetic:
    def test_delta_matches_subgroup_means(self):
        rows = [
            # Sensitive: avg cost = 0.0025
            {"domain": "legal", "cost_usd": 0.0025, "complexity_score": 0.50},
            {"domain": "medical", "cost_usd": 0.0025, "complexity_score": 0.70},
            # General: avg cost = 0.0005
            {"domain": "general", "cost_usd": 0.0001, "complexity_score": 0.10},
            {"domain": "technical", "cost_usd": 0.0009, "complexity_score": 0.40},
        ]
        result = _compute_breakdown(rows)
        assert result["n"] == 4
        assert result["n_sensitive_domain"] == 2
        assert result["n_general"] == 2
        assert result["avg_cost_sensitive"] == pytest.approx(0.0025)
        assert result["avg_cost_general"] == pytest.approx(0.0005)
        assert result["cost_delta_usd"] == pytest.approx(0.002)

    def test_tier_stratification_buckets_by_complexity(self):
        rows = [
            # mid tier [0.45, 0.65)
            {"domain": "legal", "cost_usd": 0.0025, "complexity_score": 0.50},
            {"domain": "general", "cost_usd": 0.0005, "complexity_score": 0.55},
            # top tier [0.80, 1.01)
            {"domain": "medical", "cost_usd": 0.0030, "complexity_score": 0.85},
            {"domain": "general", "cost_usd": 0.0006, "complexity_score": 0.90},
        ]
        result = _compute_breakdown(rows)
        tiers_by_name = {t["tier"]: t for t in result["tiers"]}

        assert tiers_by_name["mid"]["n_sensitive"] == 1
        assert tiers_by_name["mid"]["n_general"] == 1
        assert tiers_by_name["mid"]["cost_delta"] == pytest.approx(0.002)

        assert tiers_by_name["top"]["n_sensitive"] == 1
        assert tiers_by_name["top"]["n_general"] == 1
        assert tiers_by_name["top"]["cost_delta"] == pytest.approx(0.0024)

        # Empty tiers report null delta
        assert tiers_by_name["low"]["cost_delta"] is None
        assert tiers_by_name["high"]["cost_delta"] is None


class TestComputeBreakdownShape:
    def test_method_field_is_subgroup_mean_comparison(self):
        rows = [
            {"domain": "legal", "cost_usd": 0.001, "complexity_score": 0.5},
            {"domain": "general", "cost_usd": 0.0001, "complexity_score": 0.1},
        ]
        assert _compute_breakdown(rows)["method"] == "subgroup_mean_comparison"

    def test_no_dowhy_or_refutation_fields_present(self):
        """Regression: ensure the dishonest DoWhy/refutation fields are gone."""
        rows = [
            {"domain": "legal", "cost_usd": 0.001, "complexity_score": 0.5},
            {"domain": "general", "cost_usd": 0.0001, "complexity_score": 0.1},
        ]
        result = _compute_breakdown(rows)
        assert "causal_effect_usd" not in result
        assert "refutation_passed" not in result
        assert "placebo_effect_usd" not in result
        assert "dag" not in result


@pytest.mark.asyncio
async def test_async_wrapper_returns_same_shape():
    rows = [
        {"domain": "legal", "cost_usd": 0.0025, "complexity_score": 0.5},
        {"domain": "general", "cost_usd": 0.0001, "complexity_score": 0.1},
    ]
    result = await run_domain_cost_breakdown(rows)
    assert "cost_delta_usd" in result
    assert "tiers" in result
    assert result["method"] == "subgroup_mean_comparison"
