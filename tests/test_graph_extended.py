"""Extended graph tests — fills edge cases to reach 100% coverage."""

import os
from unittest.mock import patch

import networkx as nx
import pytest

from repomap.graph import RepoGraph

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mock_saas")


@pytest.fixture
def graph():
    g = RepoGraph(FIXTURES_DIR)
    g.build()
    return g


def test_blast_radius_nonexistent_file(graph):
    """get_blast_radius for a missing file returns early with zero results."""
    result = graph.get_blast_radius("nonexistent.ts")
    assert result.total_affected_files == 0
    assert result.direct_dependents == []
    assert result.risk_score == 0.0


def test_resolve_filepath_absolute_path(graph):
    """_resolve_filepath with an absolute path resolves via _to_relative."""
    abs_path = os.path.join(FIXTURES_DIR, "src", "index.ts")
    resolved = graph._resolve_filepath(abs_path)
    assert resolved == "src/index.ts"


def test_repo_overview_empty_graph():
    """get_repo_overview on an empty graph (0 nodes)."""
    g = RepoGraph("/tmp/nonexistent_empty")
    # Don't build — graph stays empty
    result = g.get_repo_overview()
    assert result.total_files == 0
    assert result.most_connected == []
    assert result.risk_hotspots == []


def test_repo_overview_single_node():
    """get_repo_overview on a single-node graph (no betweenness)."""
    g = RepoGraph("/tmp/fake")
    g.graph.add_node("a.ts", language="typescript", exports=[], policy_zones=[])
    result = g.get_repo_overview()
    assert result.total_files == 1
    assert len(result.most_connected) == 1
    assert result.most_connected[0][0] == "a.ts"
    assert result.risk_hotspots == []  # betweenness needs >1 node


def test_domain_context_matches_on_export(graph):
    """get_domain_context matches on export name, not just filename."""
    result = graph.get_domain_context("processCharge")
    assert len(result.matching_files) > 0
    assert any("billing_service" in f for f in result.matching_files)


def test_resolve_filepath_as_is_match(graph):
    """_resolve_filepath returns filepath as-is when it's already in the graph (line 83)."""
    # Add a node with an unusual key that matches as-is but not after lstrip
    graph.graph.add_node("./special.ts", language="typescript", exports=[], policy_zones=[])
    resolved = graph._resolve_filepath("./special.ts")
    assert resolved == "./special.ts"


def test_to_relative_value_error():
    """_to_relative handles ValueError from os.path.relpath gracefully."""
    g = RepoGraph("/tmp/repo")
    with patch("os.path.relpath", side_effect=ValueError("different drives")):
        result = g._to_relative("/other/drive/file.ts")
        assert result == "/other/drive/file.ts"


def test_networkx_no_path_in_chain_building(graph):
    """NetworkXNoPath during chain building is silently skipped."""
    original_shortest_path = nx.shortest_path

    call_count = [0]

    def flaky_shortest_path(*args, **kwargs):
        call_count[0] += 1
        # Fail on the first call during chain building (not the ancestors call)
        if call_count[0] == 1:
            raise nx.NetworkXNoPath("mock no path")
        return original_shortest_path(*args, **kwargs)

    # Use a file with known ancestors
    with patch("repomap.graph.nx.shortest_path", side_effect=flaky_shortest_path):
        result = graph.get_blast_radius("src/utils/date_utils.ts")
        # Should not crash — the failed chain is just skipped
        assert result.total_affected_files > 0
