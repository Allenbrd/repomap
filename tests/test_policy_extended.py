"""Extended policy tests — fills YAML loading and edge cases."""

import os
import tempfile
from unittest.mock import patch

import networkx as nx
import pytest

from repomap.policy import apply_zones_to_graph, detect_violations, load_manual_zones


# ── load_manual_zones ────────────────────────────────────────────────────

def test_load_manual_zones_valid():
    with tempfile.TemporaryDirectory() as root:
        cfg = os.path.join(root, ".repomap.yml")
        with open(cfg, "w") as f:
            f.write("policy_zones:\n  billing:\n    - src/billing.ts\n")
        result = load_manual_zones(root)
        assert "billing" in result
        assert "src/billing.ts" in result["billing"]


def test_load_manual_zones_empty_yaml():
    with tempfile.TemporaryDirectory() as root:
        cfg = os.path.join(root, ".repomap.yml")
        with open(cfg, "w") as f:
            f.write("")
        result = load_manual_zones(root)
        assert result == {}


def test_load_manual_zones_missing_key():
    with tempfile.TemporaryDirectory() as root:
        cfg = os.path.join(root, ".repomap.yml")
        with open(cfg, "w") as f:
            f.write("other_key: 123\n")
        result = load_manual_zones(root)
        assert result == {}


def test_load_manual_zones_malformed_yaml():
    with tempfile.TemporaryDirectory() as root:
        cfg = os.path.join(root, ".repomap.yml")
        with open(cfg, "w") as f:
            f.write(": : :\n  bad yaml {{{")
        result = load_manual_zones(root)
        assert result == {}


def test_load_manual_zones_no_file():
    result = load_manual_zones("/tmp/nonexistent_dir_xyz")
    assert result == {}


# ── apply_zones_to_graph with manual overrides ──────────────────────────

def test_apply_zones_manual_override():
    """Manual zone config should apply custom zone to matching node."""
    with tempfile.TemporaryDirectory() as root:
        cfg = os.path.join(root, ".repomap.yml")
        with open(cfg, "w") as f:
            f.write("policy_zones:\n  custom_zone:\n    - src/my_file.ts\n")

        graph = nx.DiGraph()
        graph.add_node("src/my_file.ts", language="typescript", exports=[], policy_zones=[])
        apply_zones_to_graph(graph, root)

        zones = graph.nodes["src/my_file.ts"]["policy_zones"]
        assert "custom_zone" in zones


def test_apply_zones_no_duplicate():
    """If auto-detect and manual both find the same zone, no duplicates."""
    with tempfile.TemporaryDirectory() as root:
        cfg = os.path.join(root, ".repomap.yml")
        with open(cfg, "w") as f:
            f.write("policy_zones:\n  billing:\n    - src/billing_service.ts\n")

        graph = nx.DiGraph()
        graph.add_node("src/billing_service.ts", language="typescript", exports=[], policy_zones=[])
        apply_zones_to_graph(graph, root)

        zones = graph.nodes["src/billing_service.ts"]["policy_zones"]
        assert zones.count("billing") == 1


# ── detect_violations with disconnected graph ───────────────────────────

def test_detect_violations_no_path_fallback():
    """When there's no path between files, chain becomes [affected, '...', target]."""
    graph = nx.DiGraph()
    graph.add_node("billing.ts", policy_zones=["billing"])
    graph.add_node("target.ts", policy_zones=[])

    violations = detect_violations(graph, "target.ts", ["billing.ts"])
    assert len(violations) == 1
    assert violations[0].dependency_chain == ["billing.ts", "...", "target.ts"]
    assert violations[0].severity == "critical"
