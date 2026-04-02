"""White Circle policy zones and guardrail checks."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import networkx as nx
import yaml

from .config import POLICY_ZONE_KEYWORDS

logger = logging.getLogger(__name__)


@dataclass
class PolicyViolation:
    zone: str  # e.g., "billing"
    violated_file: str  # the file in the policy zone
    dependency_chain: list[str]  # path from the modified file to the policy zone file
    severity: str  # "critical" | "warning"
    message: str  # human-readable explanation


# Zones considered critical (vs warning)
_CRITICAL_ZONES = {"billing", "auth", "pii"}


def auto_detect_zones(filepath: str) -> list[str]:
    """Detect policy zones for a file based on path/name heuristics."""
    lower_path = filepath.lower()
    zones = []
    for zone, keywords in POLICY_ZONE_KEYWORDS.items():
        if any(kw in lower_path for kw in keywords):
            zones.append(zone)
    return zones


def load_manual_zones(root_path: str) -> dict[str, list[str]]:
    """Load manual policy zone overrides from .repomap.yml."""
    config_path = os.path.join(root_path, ".repomap.yml")
    if not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        if not config or "policy_zones" not in config:
            return {}
        return config["policy_zones"]
    except Exception as e:
        logger.warning("Failed to load .repomap.yml: %s", e)
        return {}


def apply_zones_to_graph(graph: nx.DiGraph, root_path: str) -> None:
    """Tag all nodes in the graph with their policy zones."""
    manual_zones = load_manual_zones(root_path)

    # Build reverse lookup: filepath -> zones from manual config
    manual_lookup: dict[str, list[str]] = {}
    for zone, files in manual_zones.items():
        for filepath in files:
            normalized = filepath.replace("\\", "/").strip("./")
            manual_lookup.setdefault(normalized, []).append(zone)

    for node in graph.nodes():
        zones = auto_detect_zones(node)

        # Merge manual zones
        normalized_node = node.replace("\\", "/").strip("./")
        if normalized_node in manual_lookup:
            for z in manual_lookup[normalized_node]:
                if z not in zones:
                    zones.append(z)

        graph.nodes[node]["policy_zones"] = zones


def detect_violations(
    graph: nx.DiGraph,
    target_file: str,
    affected_files: list[str],
) -> list[PolicyViolation]:
    """Check if any affected file is in a policy zone and generate violations."""
    violations: list[PolicyViolation] = []

    for affected in affected_files:
        zones = graph.nodes.get(affected, {}).get("policy_zones", [])
        if not zones:
            continue

        # Find the dependency chain from affected -> target
        try:
            chain = nx.shortest_path(graph, affected, target_file)
        except nx.NetworkXNoPath:
            chain = [affected, "...", target_file]

        for zone in zones:
            severity = "critical" if zone in _CRITICAL_ZONES else "warning"
            message = (
                f"Modification reaches {zone.upper()} zone via: "
                + " → ".join(chain)
            )
            violations.append(PolicyViolation(
                zone=zone,
                violated_file=affected,
                dependency_chain=chain,
                severity=severity,
                message=message,
            ))

    return violations
