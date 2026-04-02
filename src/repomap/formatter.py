"""Output formatting for Mermaid diagrams and text summaries."""

from __future__ import annotations

import re

from .graph import (
    BlastRadiusResult,
    DomainContextResult,
    ExecutionPathResult,
    FileInfoResult,
    RepoOverviewResult,
)


def _sanitize_mermaid_id(filepath: str) -> str:
    """Replace characters invalid in Mermaid node IDs."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", filepath)


def format_blast_radius_mermaid(result: BlastRadiusResult) -> str:
    """Generate a Mermaid graph diagram showing the blast radius."""
    if result.total_affected_files == 0:
        return ""

    lines = ["graph TD"]

    # Collect all nodes that appear in chains
    all_nodes: set[str] = {result.target_file}
    for chain in result.dependency_chains:
        all_nodes.update(chain)

    # Track policy zone files for styling
    policy_files = {v.violated_file for v in result.policy_violations}
    direct_set = set(result.direct_dependents)

    # Add edges from chains
    seen_edges: set[tuple[str, str]] = set()
    for chain in result.dependency_chains:
        for i in range(len(chain) - 1):
            src, dst = chain[i], chain[i + 1]
            if (src, dst) not in seen_edges:
                seen_edges.add((src, dst))
                src_id = _sanitize_mermaid_id(src)
                dst_id = _sanitize_mermaid_id(dst)
                lines.append(f'    {src_id}["{src}"] -->|"imports"| {dst_id}["{dst}"]')

    # Style nodes
    target_id = _sanitize_mermaid_id(result.target_file)
    lines.append(f"    style {target_id} fill:#e91e63,stroke:#333,stroke-width:4px")

    for f in policy_files:
        fid = _sanitize_mermaid_id(f)
        lines.append(f"    style {fid} fill:#ff5252,stroke:#f00,stroke-width:2px")

    for f in direct_set:
        if f not in policy_files:
            fid = _sanitize_mermaid_id(f)
            lines.append(f"    style {fid} fill:#ff9800,stroke:#333,stroke-width:2px")

    for f in result.transitive_dependents:
        if f not in policy_files and f not in direct_set:
            fid = _sanitize_mermaid_id(f)
            lines.append(f"    style {fid} fill:#ffeb3b,stroke:#333,stroke-width:1px")

    return "\n".join(lines)


def _risk_label(score: float) -> str:
    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


def format_blast_radius_text(result: BlastRadiusResult) -> str:
    """Generate a clear text summary of the blast radius."""
    lines = [
        f"## Blast Radius Analysis for `{result.target_file}`",
        "",
        f"**Risk Score: {result.risk_score} ({_risk_label(result.risk_score)})**",
        f"**Total affected files: {result.total_affected_files}**",
        "",
    ]

    if result.direct_dependents:
        lines.append(f"### Direct Dependents ({len(result.direct_dependents)} files):")
        for f in result.direct_dependents:
            lines.append(f"- {f}")
        lines.append("")

    if result.transitive_dependents:
        lines.append(f"### Transitive Dependents ({len(result.transitive_dependents)} files):")
        for chain in result.dependency_chains:
            if chain[0] in result.transitive_dependents:
                lines.append(f"- {' -> '.join(chain)}")
        lines.append("")

    if result.policy_violations:
        lines.append("### POLICY VIOLATIONS")
        for v in result.policy_violations:
            icon = "🔴" if v.severity == "critical" else "🟡"
            lines.append(f"{icon} {v.severity.upper()}: {v.message}")
        lines.append("")

    if not result.direct_dependents and not result.transitive_dependents:
        lines.append("No other files depend on this file. Safe to modify.")

    return "\n".join(lines)


def format_execution_path_text(result: ExecutionPathResult) -> str:
    """Format the execution path result."""
    if not result.exists:
        return (
            f"## Dependency Path: `{result.start_file}` -> `{result.end_file}`\n\n"
            f"**No dependency path exists** between these files."
        )

    path_str = " -> ".join(result.path) if result.path else ""
    return (
        f"## Dependency Path: `{result.start_file}` -> `{result.end_file}`\n\n"
        f"**Path length:** {result.path_length} hops\n\n"
        f"**Chain:** {path_str}"
    )


def format_domain_context_text(result: DomainContextResult) -> str:
    """Format domain context results."""
    lines = [
        f'## Domain Context: "{result.concept}"',
        "",
        f"**Matching files ({len(result.matching_files)}):**",
    ]
    for f in result.matching_files:
        lines.append(f"- {f}")

    if result.context_files:
        neighbors_only = [f for f in result.context_files if f not in result.matching_files]
        if neighbors_only:
            lines.append("")
            lines.append(f"**Related files ({len(neighbors_only)}):**")
            for f in neighbors_only:
                lines.append(f"- {f}")

    if result.relationships:
        lines.append("")
        lines.append("**Relationships:**")
        for u, v in result.relationships:
            lines.append(f"- {u} imports {v}")

    return "\n".join(lines)


def format_domain_context_mermaid(result: DomainContextResult) -> str:
    """Generate Mermaid diagram for domain context."""
    if not result.relationships:
        return ""

    lines = ["graph TD"]
    matching_set = set(result.matching_files)

    for u, v in result.relationships:
        uid = _sanitize_mermaid_id(u)
        vid = _sanitize_mermaid_id(v)
        lines.append(f'    {uid}["{u}"] -->|"imports"| {vid}["{v}"]')

    for f in matching_set:
        fid = _sanitize_mermaid_id(f)
        lines.append(f"    style {fid} fill:#4caf50,stroke:#333,stroke-width:3px")

    return "\n".join(lines)


def format_file_info_text(result: FileInfoResult) -> str:
    """Format file info results."""
    lines = [
        f"## File Info: `{result.filepath}`",
        "",
        f"**Language:** {result.language}",
        f"**Degree Centrality:** {result.degree_centrality}",
    ]

    if result.policy_zones:
        lines.append(f"**Policy Zones:** {', '.join(result.policy_zones)}")

    if result.exports:
        lines.append(f"\n**Exports:** {', '.join(result.exports)}")

    if result.imports_from:
        lines.append(f"\n**Imports from ({len(result.imports_from)}):**")
        for f in result.imports_from:
            lines.append(f"- {f}")

    if result.imported_by:
        lines.append(f"\n**Imported by ({len(result.imported_by)}):**")
        for f in result.imported_by:
            lines.append(f"- {f}")

    return "\n".join(lines)


def format_repo_overview_text(result: RepoOverviewResult) -> str:
    """Format repo overview."""
    lines = [
        "## Repository Overview",
        "",
        f"**Total files:** {result.total_files}",
        "",
        "### Languages:",
    ]
    for lang, count in sorted(result.languages.items(), key=lambda x: -x[1]):
        lines.append(f"- {lang}: {count} files")

    if result.most_connected:
        lines.append("")
        lines.append("### Most Connected Files:")
        for f, c in result.most_connected:
            lines.append(f"- {f} (centrality: {c})")

    if result.risk_hotspots:
        lines.append("")
        lines.append("### Risk Hotspots (by betweenness centrality):")
        for f, c in result.risk_hotspots:
            lines.append(f"- {f} (betweenness: {c})")

    if result.policy_zone_files:
        lines.append("")
        lines.append("### Policy Zones:")
        for zone, files in sorted(result.policy_zone_files.items()):
            lines.append(f"\n**{zone}:**")
            for f in files:
                lines.append(f"- {f}")

    return "\n".join(lines)
