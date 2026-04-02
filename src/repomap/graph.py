"""Dependency graph builder using NetworkX."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import networkx as nx

from .config import POLICY_ZONE_KEYWORDS
from .parser import parse_directory
from .policy import PolicyViolation, apply_zones_to_graph, detect_violations


@dataclass
class BlastRadiusResult:
    target_file: str
    direct_dependents: list[str]
    transitive_dependents: list[str]
    dependency_chains: list[list[str]]
    policy_violations: list[PolicyViolation]
    risk_score: float
    total_affected_files: int


@dataclass
class ExecutionPathResult:
    start_file: str
    end_file: str
    path: list[str] | None
    path_length: int | None
    exists: bool


@dataclass
class DomainContextResult:
    concept: str
    matching_files: list[str]
    context_files: list[str]
    relationships: list[tuple[str, str]]


@dataclass
class FileInfoResult:
    filepath: str
    language: str
    imports_from: list[str]
    imported_by: list[str]
    exports: list[str]
    policy_zones: list[str]
    degree_centrality: float


@dataclass
class RepoOverviewResult:
    total_files: int
    languages: dict[str, int]
    most_connected: list[tuple[str, float]]
    policy_zone_files: dict[str, list[str]]
    risk_hotspots: list[tuple[str, float]]


class RepoGraph:
    def __init__(self, root_path: str):
        self.root = os.path.abspath(root_path)
        self.graph: nx.DiGraph = nx.DiGraph()

    def _to_relative(self, filepath: str) -> str:
        """Convert absolute path to relative from repo root."""
        abs_path = os.path.abspath(filepath)
        try:
            return os.path.relpath(abs_path, self.root)
        except ValueError:
            return filepath

    def _resolve_filepath(self, filepath: str) -> str:
        """Normalize a user-provided filepath to the relative form used in the graph."""
        # Strip leading ./
        clean = filepath.lstrip("./")
        if clean in self.graph:
            return clean
        # Try as-is
        if filepath in self.graph:
            return filepath
        # Try relative from root
        rel = self._to_relative(filepath)
        if rel in self.graph:
            return rel
        return clean

    def build(self, exclude_patterns: list[str] | None = None) -> None:
        """Parse the repo and populate self.graph."""
        file_nodes = parse_directory(self.root, exclude_patterns)

        # Add all files as nodes
        for fnode in file_nodes:
            rel_path = self._to_relative(fnode.filepath)
            self.graph.add_node(
                rel_path,
                language=fnode.language,
                exports=fnode.exports,
                policy_zones=[],
            )

        # Add edges: A -> B means A imports from B
        for fnode in file_nodes:
            source_rel = self._to_relative(fnode.filepath)
            for imp in fnode.imports:
                target_rel = self._to_relative(imp.target_file)
                if target_rel in self.graph:
                    self.graph.add_edge(
                        source_rel,
                        target_rel,
                        imported_names=imp.imported_names,
                        line_number=imp.line_number,
                    )

        # Apply policy zones
        apply_zones_to_graph(self.graph, self.root)

    def get_blast_radius(self, filepath: str) -> BlastRadiusResult:
        """
        Find all files that depend on the target file (direct + transitive).
        Edge direction: A -> B means A imports B.
        ancestors(target) = all nodes that can reach target = all importers.
        """
        target = self._resolve_filepath(filepath)

        if target not in self.graph:
            return BlastRadiusResult(
                target_file=target,
                direct_dependents=[],
                transitive_dependents=[],
                dependency_chains=[],
                policy_violations=[],
                risk_score=0.0,
                total_affected_files=0,
            )

        # Direct dependents: nodes with an edge pointing to target
        direct = [n for n in self.graph.predecessors(target)]

        # All transitive dependents
        all_ancestors = nx.ancestors(self.graph, target)
        transitive = [n for n in all_ancestors if n not in direct]

        # Build dependency chains
        all_affected = list(all_ancestors)
        chains: list[list[str]] = []
        for dep in all_affected:
            try:
                path = nx.shortest_path(self.graph, dep, target)
                chains.append(path)
            except nx.NetworkXNoPath:
                pass

        # Detect policy violations
        violations = detect_violations(self.graph, target, all_affected)

        # Calculate risk score
        total = len(all_affected)
        total_nodes = len(self.graph)
        base_risk = min(total / max(total_nodes, 1), 1.0)
        # Boost for policy violations
        violation_boost = min(len(violations) * 0.15, 0.4)
        risk_score = min(base_risk + violation_boost, 1.0)

        return BlastRadiusResult(
            target_file=target,
            direct_dependents=sorted(direct),
            transitive_dependents=sorted(transitive),
            dependency_chains=chains,
            policy_violations=violations,
            risk_score=round(risk_score, 2),
            total_affected_files=total,
        )

    def find_execution_path(self, start_file: str, end_file: str) -> ExecutionPathResult:
        """Find the shortest dependency path between two files."""
        start = self._resolve_filepath(start_file)
        end = self._resolve_filepath(end_file)

        undirected = self.graph.to_undirected()

        try:
            path = nx.shortest_path(undirected, start, end)
            return ExecutionPathResult(
                start_file=start,
                end_file=end,
                path=path,
                path_length=len(path) - 1,
                exists=True,
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return ExecutionPathResult(
                start_file=start,
                end_file=end,
                path=None,
                path_length=None,
                exists=False,
            )

    def get_domain_context(self, concept: str) -> DomainContextResult:
        """Find files related to a domain concept via name/export matching.

        If the concept matches a policy zone name, all keywords for that zone
        are used for matching (e.g. "billing" also matches "payment", "stripe",
        "checkout", "subscription", etc.).
        """
        concept_lower = concept.lower()

        # Build search terms: the concept itself + any policy zone synonyms
        search_terms = [concept_lower]
        for zone, keywords in POLICY_ZONE_KEYWORDS.items():
            if concept_lower in keywords or concept_lower == zone:
                for kw in keywords:
                    if kw not in search_terms:
                        search_terms.append(kw)

        matching: list[str] = []

        # Path matching: expanded keywords with word boundaries
        # Use a custom boundary that treats - _ / . as separators (unlike \b which treats _ as \w)
        sep = r"(?<![a-zA-Z0-9])"
        end = r"(?![a-zA-Z0-9])"
        path_pattern = re.compile(
            "|".join(rf"{sep}{re.escape(t)}{end}" for t in search_terms)
        )

        for node in self.graph.nodes():
            node_lower = node.lower()
            if path_pattern.search(node_lower):
                matching.append(node)
                continue
            # Export matching: direct concept only (no expansion)
            exports = self.graph.nodes[node].get("exports", [])
            if any(concept_lower in exp.lower() for exp in exports):
                matching.append(node)

        # Expand to 1-hop neighbors
        context_set = set(matching)
        for f in matching:
            context_set.update(self.graph.predecessors(f))
            context_set.update(self.graph.successors(f))

        context_files = sorted(context_set)

        # Collect edges within the context
        relationships = []
        for u, v in self.graph.edges():
            if u in context_set and v in context_set:
                relationships.append((u, v))

        return DomainContextResult(
            concept=concept,
            matching_files=sorted(matching),
            context_files=context_files,
            relationships=relationships,
        )

    def get_file_info(self, filepath: str) -> FileInfoResult:
        """Return detailed information about a single file."""
        target = self._resolve_filepath(filepath)

        if target not in self.graph:
            return FileInfoResult(
                filepath=target,
                language="unknown",
                imports_from=[],
                imported_by=[],
                exports=[],
                policy_zones=[],
                degree_centrality=0.0,
            )

        attrs = self.graph.nodes[target]
        centrality = nx.degree_centrality(self.graph)

        return FileInfoResult(
            filepath=target,
            language=attrs.get("language", "unknown"),
            imports_from=sorted(self.graph.successors(target)),
            imported_by=sorted(self.graph.predecessors(target)),
            exports=attrs.get("exports", []),
            policy_zones=attrs.get("policy_zones", []),
            degree_centrality=round(centrality.get(target, 0.0), 4),
        )

    def get_repo_overview(self) -> RepoOverviewResult:
        """Return a high-level summary of the repo."""
        languages: dict[str, int] = {}
        policy_zone_files: dict[str, list[str]] = {}

        for node, attrs in self.graph.nodes(data=True):
            lang = attrs.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1

            for zone in attrs.get("policy_zones", []):
                policy_zone_files.setdefault(zone, []).append(node)

        # Degree centrality
        if len(self.graph) > 0:
            deg_centrality = nx.degree_centrality(self.graph)
            most_connected = sorted(
                deg_centrality.items(), key=lambda x: x[1], reverse=True
            )[:10]
        else:
            most_connected = []

        # Betweenness centrality for risk hotspots
        if len(self.graph) > 1:
            between = nx.betweenness_centrality(self.graph)
            risk_hotspots = sorted(
                between.items(), key=lambda x: x[1], reverse=True
            )[:5]
        else:
            risk_hotspots = []

        return RepoOverviewResult(
            total_files=len(self.graph),
            languages=languages,
            most_connected=[(f, round(c, 4)) for f, c in most_connected],
            policy_zone_files=policy_zone_files,
            risk_hotspots=[(f, round(c, 4)) for f, c in risk_hotspots],
        )
