"""Tests for the graph module."""

import os

import pytest

from repomap.graph import RepoGraph

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mock_saas")


@pytest.fixture
def graph():
    g = RepoGraph(FIXTURES_DIR)
    g.build()
    return g


def test_graph_node_count(graph):
    """Graph should contain all 11 parseable files."""
    assert len(graph.graph.nodes()) == 11


def test_blast_radius_date_utils(graph):
    """Modifying date_utils.ts should affect many files up the chain."""
    result = graph.get_blast_radius("src/utils/date_utils.ts")

    assert result.total_affected_files > 0

    # billing_service.ts directly imports date_utils.ts
    assert "src/services/billing_service.ts" in result.direct_dependents

    # format_helpers.ts directly imports date_utils.ts
    assert "src/utils/format_helpers.ts" in result.direct_dependents

    # index.ts should be a transitive dependent
    all_affected = result.direct_dependents + result.transitive_dependents
    assert "src/index.ts" in all_affected


def test_blast_radius_leaf_queries(graph):
    """queries.ts is imported by multiple services."""
    result = graph.get_blast_radius("src/db/queries.ts")
    assert result.total_affected_files >= 3  # billing, user, attribution services


def test_blast_radius_no_dependents(graph):
    """index.ts is the root — nothing imports it."""
    result = graph.get_blast_radius("src/index.ts")
    assert result.total_affected_files == 0


def test_execution_path_index_to_queries(graph):
    """There should be a path from index.ts to queries.ts."""
    result = graph.find_execution_path("src/index.ts", "src/db/queries.ts")
    assert result.exists
    assert result.path is not None
    assert result.path[0] == "src/index.ts"
    assert result.path[-1] == "src/db/queries.ts"
    assert result.path_length is not None and result.path_length >= 2


def test_execution_path_no_connection(graph):
    """Two disconnected files should have no path (if any exist)."""
    # All files in mock_saas are connected, so test non-existent file
    result = graph.find_execution_path("src/index.ts", "nonexistent.ts")
    assert not result.exists


def test_domain_context_billing(graph):
    """'billing' concept should find billing-related files."""
    result = graph.get_domain_context("billing")
    assert len(result.matching_files) > 0
    assert any("billing_service" in f for f in result.matching_files)


def test_domain_context_checkout(graph):
    """'checkout' concept should find checkout-related files."""
    result = graph.get_domain_context("checkout")
    matching = result.matching_files
    assert any("checkout" in f.lower() for f in matching)


def test_repo_overview(graph):
    """Overview should return correct file counts and identify hotspots."""
    result = graph.get_repo_overview()
    assert result.total_files == 11
    assert "typescript" in result.languages
    assert result.languages["typescript"] == 11
    assert len(result.most_connected) > 0
    assert len(result.risk_hotspots) > 0


def test_file_info(graph):
    """File info should return correct imports/exports for billing_service.ts."""
    result = graph.get_file_info("src/services/billing_service.ts")
    assert result.language == "typescript"
    assert "src/utils/date_utils.ts" in result.imports_from
    assert "src/db/queries.ts" in result.imports_from
    assert "processCharge" in result.exports
    assert len(result.imported_by) > 0


def test_file_info_nonexistent(graph):
    """Querying a nonexistent file should return empty info, not crash."""
    result = graph.get_file_info("nonexistent.ts")
    assert result.language == "unknown"
    assert result.imports_from == []


def test_risk_score_range(graph):
    """Risk scores should be between 0 and 1."""
    result = graph.get_blast_radius("src/utils/date_utils.ts")
    assert 0.0 <= result.risk_score <= 1.0
