#!/usr/bin/env python3
"""Run a repomap tool and return structured JSON for the extension.

Usage:
  python run_tool.py analyze_blast_radius <repo_path> <file_path>
  python run_tool.py find_dependency_path  <repo_path> <start_file> <end_file>
  python run_tool.py get_domain_context    <repo_path> <concept>
"""
import json
import sys

from repomap.graph import RepoGraph


def _risk_label(score: float) -> str:
    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


def run_blast_radius(repo_path: str, file_path: str):
    g = RepoGraph(repo_path)
    g.build()
    r = g.get_blast_radius(file_path)
    violations = []
    for v in r.policy_violations:
        violations.append({
            "zone": v.zone,
            "severity": v.severity,
            "message": v.message,
        })
    return {
        "tool": "analyze_blast_radius",
        "args": {"repo_path": repo_path, "file_path": file_path},
        "risk_score": r.risk_score,
        "risk_level": _risk_label(r.risk_score),
        "direct_dependents": r.direct_dependents,
        "transitive_dependents": r.transitive_dependents,
        "violations": violations,
        "reasoning": f"Blast radius for {r.target_file}: {r.total_affected_files} affected, score {r.risk_score}",
    }


def run_dependency_path(repo_path: str, start_file: str, end_file: str):
    g = RepoGraph(repo_path)
    g.build()
    r = g.find_execution_path(start_file, end_file)
    return {
        "tool": "find_dependency_path",
        "args": {"repo_path": repo_path, "start_file": start_file, "end_file": end_file},
        "risk_score": 0,
        "risk_level": "LOW",
        "path_files": r.path or [],
        "reasoning": f"Path {'found' if r.exists else 'not found'}: {r.path_length or 0} hops",
        "violations": [],
        "direct_dependents": [],
        "transitive_dependents": [],
    }


def run_domain_context(repo_path: str, concept: str):
    g = RepoGraph(repo_path)
    g.build()
    r = g.get_domain_context(concept)
    return {
        "tool": "get_domain_context",
        "args": {"repo_path": repo_path, "concept": concept},
        "risk_score": 0,
        "risk_level": "LOW",
        "matching_files": r.matching_files,
        "context_files": r.context_files,
        "reasoning": f"Domain '{concept}': {len(r.matching_files)} matching, {len(r.context_files)} context files",
        "violations": [],
        "direct_dependents": [],
        "transitive_dependents": [],
        "path_files": [],
    }


def main():
    if len(sys.argv) < 3:
        json.dump({"error": "Usage: run_tool.py <tool> <repo_path> [args...]"}, sys.stdout)
        sys.exit(1)

    tool = sys.argv[1]
    repo_path = sys.argv[2]

    try:
        if tool == "analyze_blast_radius" and len(sys.argv) >= 4:
            result = run_blast_radius(repo_path, sys.argv[3])
        elif tool == "find_dependency_path" and len(sys.argv) >= 5:
            result = run_dependency_path(repo_path, sys.argv[3], sys.argv[4])
        elif tool == "get_domain_context" and len(sys.argv) >= 4:
            result = run_domain_context(repo_path, sys.argv[3])
        else:
            result = {"error": f"Unknown tool or missing args: {tool}"}
        json.dump(result, sys.stdout)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
