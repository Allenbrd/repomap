"""Tests for the server module."""

from unittest.mock import MagicMock, patch

import pytest

from repomap.graph import (
    BlastRadiusResult,
    DomainContextResult,
    ExecutionPathResult,
    FileInfoResult,
    RepoOverviewResult,
)
from repomap.server import _get_graph, _graph_cache, call_tool, list_tools


# --- _get_graph ---

def test_get_graph_cache_miss():
    """First call builds the graph and caches it."""
    _graph_cache.clear()
    with patch("repomap.server.RepoGraph") as MockGraph:
        mock_instance = MagicMock()
        MockGraph.return_value = mock_instance

        result = _get_graph("/tmp/fake_repo")

        MockGraph.assert_called_once_with("/tmp/fake_repo")
        mock_instance.build.assert_called_once()
        assert result is mock_instance
    _graph_cache.clear()


def test_get_graph_cache_hit():
    """Second call returns cached graph without rebuilding."""
    _graph_cache.clear()
    sentinel = MagicMock()
    _graph_cache["/tmp/cached"] = sentinel

    result = _get_graph("/tmp/cached")
    assert result is sentinel
    _graph_cache.clear()


# --- list_tools ---

@pytest.mark.asyncio
async def test_list_tools_returns_five():
    tools = await list_tools()
    assert len(tools) == 5
    names = {t.name for t in tools}
    assert names == {
        "analyze_blast_radius",
        "find_dependency_path",
        "get_domain_context",
        "get_repo_overview",
        "get_file_info",
    }


# --- call_tool: analyze_blast_radius ---

@pytest.mark.asyncio
async def test_call_tool_blast_radius():
    mock_result = BlastRadiusResult(
        target_file="a.ts",
        direct_dependents=[],
        transitive_dependents=[],
        dependency_chains=[],
        policy_violations=[],
        risk_score=0.0,
        total_affected_files=0,
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.get_blast_radius.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool("analyze_blast_radius", {"repo_path": "/r", "file_path": "a.ts"})
        assert len(result) == 1
        assert "a.ts" in result[0].text


@pytest.mark.asyncio
async def test_call_tool_blast_radius_with_mermaid():
    """When blast radius has affected files, mermaid diagram is appended."""
    from repomap.policy import PolicyViolation

    mock_result = BlastRadiusResult(
        target_file="a.ts",
        direct_dependents=["b.ts"],
        transitive_dependents=[],
        dependency_chains=[["b.ts", "a.ts"]],
        policy_violations=[],
        risk_score=0.1,
        total_affected_files=1,
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.get_blast_radius.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool("analyze_blast_radius", {"repo_path": "/r", "file_path": "a.ts"})
        assert "mermaid" in result[0].text


# --- call_tool: find_dependency_path ---

@pytest.mark.asyncio
async def test_call_tool_find_dependency_path():
    mock_result = ExecutionPathResult(
        start_file="a.ts", end_file="b.ts", path=["a.ts", "b.ts"], path_length=1, exists=True
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.find_execution_path.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool(
            "find_dependency_path", {"repo_path": "/r", "start_file": "a.ts", "end_file": "b.ts"}
        )
        assert "a.ts" in result[0].text


# --- call_tool: get_domain_context ---

@pytest.mark.asyncio
async def test_call_tool_domain_context():
    mock_result = DomainContextResult(
        concept="billing",
        matching_files=["billing.ts"],
        context_files=["billing.ts"],
        relationships=[],
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.get_domain_context.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool("get_domain_context", {"repo_path": "/r", "concept": "billing"})
        assert "billing" in result[0].text


@pytest.mark.asyncio
async def test_call_tool_domain_context_with_mermaid():
    mock_result = DomainContextResult(
        concept="billing",
        matching_files=["billing.ts"],
        context_files=["billing.ts", "checkout.ts"],
        relationships=[("checkout.ts", "billing.ts")],
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.get_domain_context.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool("get_domain_context", {"repo_path": "/r", "concept": "billing"})
        assert "mermaid" in result[0].text


# --- call_tool: get_repo_overview ---

@pytest.mark.asyncio
async def test_call_tool_repo_overview():
    mock_result = RepoOverviewResult(
        total_files=5,
        languages={"typescript": 5},
        most_connected=[],
        policy_zone_files={},
        risk_hotspots=[],
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.get_repo_overview.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool("get_repo_overview", {"repo_path": "/r"})
        assert "5" in result[0].text


# --- call_tool: get_file_info ---

@pytest.mark.asyncio
async def test_call_tool_file_info():
    mock_result = FileInfoResult(
        filepath="a.ts",
        language="typescript",
        imports_from=[],
        imported_by=[],
        exports=[],
        policy_zones=[],
        degree_centrality=0.0,
    )
    with patch("repomap.server._get_graph") as mock_gg:
        mock_graph = MagicMock()
        mock_graph.get_file_info.return_value = mock_result
        mock_gg.return_value = mock_graph

        result = await call_tool("get_file_info", {"repo_path": "/r", "file_path": "a.ts"})
        assert "a.ts" in result[0].text


# --- call_tool: unknown tool ---

@pytest.mark.asyncio
async def test_call_tool_unknown():
    result = await call_tool("nonexistent_tool", {})
    assert "Unknown tool" in result[0].text


# --- call_tool: exception handler ---

@pytest.mark.asyncio
async def test_call_tool_exception():
    with patch("repomap.server._get_graph") as mock_gg:
        mock_gg.side_effect = RuntimeError("boom")

        result = await call_tool("analyze_blast_radius", {"repo_path": "/r", "file_path": "a.ts"})
        assert "Error: boom" in result[0].text
