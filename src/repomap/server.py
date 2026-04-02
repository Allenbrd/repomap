"""MCP server entry point for RepoMap."""

from __future__ import annotations

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .formatter import (
    format_blast_radius_mermaid,
    format_blast_radius_text,
    format_domain_context_mermaid,
    format_domain_context_text,
    format_execution_path_text,
    format_file_info_text,
    format_repo_overview_text,
)
from .graph import RepoGraph

logger = logging.getLogger(__name__)

app = Server("repomap")

# Simple in-memory cache: repo_path -> RepoGraph
_graph_cache: dict[str, RepoGraph] = {}


def _get_graph(repo_path: str) -> RepoGraph:
    """Get or build a cached RepoGraph for the given repo path."""
    if repo_path not in _graph_cache:
        graph = RepoGraph(repo_path)
        graph.build()
        _graph_cache[repo_path] = graph
    return _graph_cache[repo_path]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_blast_radius",
            description=(
                "Analyze the blast radius of modifying a file. Returns all files that "
                "directly or transitively depend on the target file, policy zone violations "
                "(billing, auth, PII, infrastructure), a risk score, and a visual Mermaid "
                "dependency graph. Call this BEFORE modifying any file to understand what could break."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file being modified (relative to repo root).",
                    },
                },
                "required": ["repo_path", "file_path"],
            },
        ),
        Tool(
            name="find_dependency_path",
            description=(
                "Find the shortest dependency path between two files in the codebase. "
                "Useful for understanding how a change in one file can propagate to another, "
                "or for tracing how data flows between modules."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "start_file": {
                        "type": "string",
                        "description": "Starting file path (relative to repo root).",
                    },
                    "end_file": {
                        "type": "string",
                        "description": "Target file path (relative to repo root).",
                    },
                },
                "required": ["repo_path", "start_file", "end_file"],
            },
        ),
        Tool(
            name="get_domain_context",
            description=(
                "Find all files related to a domain concept (e.g., 'billing', 'authentication', "
                "'checkout'). Returns the relevant file cluster and their relationships. "
                "Use this when you need to understand a feature area before making changes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "concept": {
                        "type": "string",
                        "description": "The domain concept to search for (e.g., 'checkout', 'user auth').",
                    },
                },
                "required": ["repo_path", "concept"],
            },
        ),
        Tool(
            name="get_repo_overview",
            description=(
                "Get a high-level architectural overview of a codebase: languages, most-connected "
                "files, risk hotspots, and policy zones. Call this when onboarding to a new repo "
                "or before starting a major refactor."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="get_file_info",
            description=(
                "Get detailed information about a specific file: what it imports, what imports it, "
                "its exports, policy zones, and centrality in the codebase. Use this to understand "
                "a file's role before editing it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository root.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file (relative to repo root).",
                    },
                },
                "required": ["repo_path", "file_path"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "analyze_blast_radius":
            graph = _get_graph(arguments["repo_path"])
            result = graph.get_blast_radius(arguments["file_path"])
            text = format_blast_radius_text(result)
            mermaid = format_blast_radius_mermaid(result)
            if mermaid:
                text += f"\n\n```mermaid\n{mermaid}\n```"
            return [TextContent(type="text", text=text)]

        elif name == "find_dependency_path":
            graph = _get_graph(arguments["repo_path"])
            result = graph.find_execution_path(arguments["start_file"], arguments["end_file"])
            text = format_execution_path_text(result)
            return [TextContent(type="text", text=text)]

        elif name == "get_domain_context":
            graph = _get_graph(arguments["repo_path"])
            result = graph.get_domain_context(arguments["concept"])
            text = format_domain_context_text(result)
            mermaid = format_domain_context_mermaid(result)
            if mermaid:
                text += f"\n\n```mermaid\n{mermaid}\n```"
            return [TextContent(type="text", text=text)]

        elif name == "get_repo_overview":
            graph = _get_graph(arguments["repo_path"])
            result = graph.get_repo_overview()
            text = format_repo_overview_text(result)
            return [TextContent(type="text", text=text)]

        elif name == "get_file_info":
            graph = _get_graph(arguments["repo_path"])
            result = graph.get_file_info(arguments["file_path"])
            text = format_file_info_text(result)
            return [TextContent(type="text", text=text)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception("Error in tool %s", name)
        return [TextContent(type="text", text=f"Error: {e}")]


async def run_server():  # pragma: no cover
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():  # pragma: no cover
    """Run the MCP server via stdio transport."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())


if __name__ == "__main__":  # pragma: no cover
    main()
