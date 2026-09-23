"""Regression test: verify critical routers are registered on api_router.

Historical bug (2026-09-23): ``backend/app/api/v1/endpoints/b2b_finance.py``
defined ``GET /admin/b2b/receivables`` but was never ``include_router``'d in
``backend/app/api/v1/router.py``, so the production Dashboard kept polling a
route that returned 404 on every refresh. This test fails if any critical
router is ever dropped from the aggregator again.
"""

from app.api.v1.router import api_router


def _paths() -> set[str]:
    return {route.path for route in api_router.routes}


def test_b2b_finance_receivables_route_is_registered():
    """Dashboard polls this endpoint on every refresh; must not 404."""
    paths = _paths()
    assert "/admin/b2b/receivables" in paths, (
        "GET /admin/b2b/receivables is missing from api_router; "
        "dashboard will poll a 404. Register b2b_finance.router in "
        "backend/app/api/v1/router.py."
    )
    assert "/admin/b2b/receivables/stats" in paths


def test_all_b2b_prefix_routers_are_registered():
    """Sanity: every b2b_* endpoint module with a router is wired in."""
    # b2b_admin, b2b_credit, b2b_finance, b2b_fulfillment, b2b_pricing,
    # b2b_portal are the six B2B routers expected to be registered.
    # We assert at least one path from each is reachable on the aggregator.
    paths = _paths()
    # One representative path per b2b_* router that should be registered.
    expected_paths = [
        "/admin/b2b/agents",           # b2b_admin
        "/admin/b2b/credit/risks",     # b2b_credit
        "/admin/b2b/receivables",      # b2b_finance  (regression: 2026-09-23)
        "/admin/b2b/orders/{order_id}/fulfillment",  # b2b_fulfillment
        "/admin/b2b/price-versions/{price_version_id}",  # b2b_pricing
        "/b2b-portal/quotes",          # b2b_portal
    ]
    for path in expected_paths:
        assert path in paths, (
            f"Route {path!r} is missing from api_router; check that the "
            "corresponding router is imported and included in "
            "backend/app/api/v1/router.py."
        )
