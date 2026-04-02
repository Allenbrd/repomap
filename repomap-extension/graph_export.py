#!/usr/bin/env python3
"""Export the RepoGraph as JSON for the VS Code extension.

Usage: python graph_export.py <repo_path>
Prints: {"nodes": [...], "edges": [...]} to stdout
"""
import json
import sys

from repomap.graph import RepoGraph


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: graph_export.py <repo_path>"}))
        sys.exit(1)

    repo_path = sys.argv[1]
    try:
        g = RepoGraph(repo_path)
        g.build()
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    in_deg = dict(g.graph.in_degree())
    out_deg = dict(g.graph.out_degree())

    nodes = []
    for node_id, attrs in g.graph.nodes(data=True):
        nodes.append({
            "id": node_id,
            "language": attrs.get("language", "unknown"),
            "policy_zones": attrs.get("policy_zones", []),
            "exports": attrs.get("exports", []),
            "connection_count": in_deg.get(node_id, 0) + out_deg.get(node_id, 0),
        })

    edges = []
    for u, v, _attrs in g.graph.edges(data=True):
        edges.append({"source": u, "target": v})

    json.dump({"nodes": nodes, "edges": edges}, sys.stdout)


if __name__ == "__main__":
    main()
