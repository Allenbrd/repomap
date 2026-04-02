"""Tests for the policy module."""

import os

import pytest

from repomap.graph import RepoGraph
from repomap.policy import auto_detect_zones

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mock_saas")


@pytest.fixture
def graph():
    g = RepoGraph(FIXTURES_DIR)
    g.build()
    return g


def test_billing_service_auto_tagged():
    """billing_service.ts should be auto-tagged in the billing zone."""
    zones = auto_detect_zones("src/services/billing_service.ts")
    assert "billing" in zones


def test_checkout_auto_tagged():
    """checkout.ts should be auto-tagged in the billing zone."""
    zones = auto_detect_zones("src/routes/checkout.ts")
    assert "billing" in zones


def test_user_service_pii_tagged():
    """user_service.ts should be auto-tagged in the pii zone."""
    zones = auto_detect_zones("src/services/user_service.ts")
    assert "pii" in zones


def test_queries_infrastructure_tagged():
    """queries.ts is not tagged as infrastructure (no keyword match)."""
    zones = auto_detect_zones("src/db/queries.ts")
    # 'queries' is not in the infrastructure keywords
    assert "infrastructure" not in zones


def test_schema_prisma_infrastructure_tagged():
    """schema.prisma should be tagged as infrastructure."""
    zones = auto_detect_zones("src/db/schema.prisma")
    assert "infrastructure" in zones


def test_date_utils_no_zones():
    """date_utils.ts should not be in any policy zone."""
    zones = auto_detect_zones("src/utils/date_utils.ts")
    assert len(zones) == 0


def test_modifying_date_utils_triggers_billing_violation(graph):
    """Modifying date_utils.ts should trigger a billing violation.

    Chain: date_utils -> billing_service (billing zone).
    """
    result = graph.get_blast_radius("src/utils/date_utils.ts")
    billing_violations = [v for v in result.policy_violations if v.zone == "billing"]
    assert len(billing_violations) > 0


def test_modifying_date_utils_triggers_checkout_violation(graph):
    """Modifying date_utils.ts should trigger violations for checkout files."""
    result = graph.get_blast_radius("src/utils/date_utils.ts")
    violated_files = {v.violated_file for v in result.policy_violations}
    assert any("checkout" in f for f in violated_files)


def test_modifying_user_service_no_billing_violation(graph):
    """Modifying user_service.ts should NOT trigger a billing violation.

    user_service only imports from queries.ts, which doesn't reach billing.
    """
    result = graph.get_blast_radius("src/services/user_service.ts")
    billing_violations = [v for v in result.policy_violations if v.zone == "billing"]
    assert len(billing_violations) == 0


def test_policy_violation_severity(graph):
    """Billing zone violations should have 'critical' severity."""
    result = graph.get_blast_radius("src/utils/date_utils.ts")
    billing_violations = [v for v in result.policy_violations if v.zone == "billing"]
    for v in billing_violations:
        assert v.severity == "critical"


def test_policy_zones_on_graph_nodes(graph):
    """Graph nodes should have policy_zones attribute set."""
    billing_node = "src/services/billing_service.ts"
    zones = graph.graph.nodes[billing_node].get("policy_zones", [])
    assert "billing" in zones
