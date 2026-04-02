"""Tests for the formatter module — 100% statement coverage."""

from repomap.formatter import (
    _risk_label,
    _sanitize_mermaid_id,
    format_blast_radius_mermaid,
    format_blast_radius_text,
    format_domain_context_mermaid,
    format_domain_context_text,
    format_execution_path_text,
    format_file_info_text,
    format_repo_overview_text,
)
from repomap.graph import (
    BlastRadiusResult,
    DomainContextResult,
    ExecutionPathResult,
    FileInfoResult,
    RepoOverviewResult,
)
from repomap.policy import PolicyViolation


# --- _sanitize_mermaid_id ---

def test_sanitize_slashes_and_dots():
    assert _sanitize_mermaid_id("src/utils/date_utils.ts") == "src_utils_date_utils_ts"


def test_sanitize_already_clean():
    assert _sanitize_mermaid_id("abc_123") == "abc_123"


# --- _risk_label ---

def test_risk_label_critical():
    assert _risk_label(0.8) == "CRITICAL"
    assert _risk_label(1.0) == "CRITICAL"


def test_risk_label_high():
    assert _risk_label(0.6) == "HIGH"
    assert _risk_label(0.79) == "HIGH"


def test_risk_label_medium():
    assert _risk_label(0.3) == "MEDIUM"
    assert _risk_label(0.59) == "MEDIUM"


def test_risk_label_low():
    assert _risk_label(0.0) == "LOW"
    assert _risk_label(0.29) == "LOW"


# --- format_blast_radius_mermaid ---

def test_blast_radius_mermaid_empty():
    result = BlastRadiusResult(
        target_file="a.ts",
        direct_dependents=[],
        transitive_dependents=[],
        dependency_chains=[],
        policy_violations=[],
        risk_score=0.0,
        total_affected_files=0,
    )
    assert format_blast_radius_mermaid(result) == ""


def test_blast_radius_mermaid_full():
    violation = PolicyViolation(
        zone="billing",
        violated_file="billing.ts",
        dependency_chain=["billing.ts", "a.ts"],
        severity="critical",
        message="reaches BILLING zone",
    )
    result = BlastRadiusResult(
        target_file="a.ts",
        direct_dependents=["b.ts"],
        transitive_dependents=["c.ts"],
        dependency_chains=[["b.ts", "a.ts"], ["c.ts", "b.ts", "a.ts"], ["billing.ts", "a.ts"]],
        policy_violations=[violation],
        risk_score=0.5,
        total_affected_files=3,
    )
    out = format_blast_radius_mermaid(result)
    assert "graph TD" in out
    # Target styling
    assert "fill:#e91e63" in out
    # Policy violation styling
    assert "fill:#ff5252" in out
    # Direct dependent styling (b.ts is not in policy_files)
    assert "fill:#ff9800" in out
    # Transitive styling (c.ts not in policy or direct)
    assert "fill:#ffeb3b" in out
    # Edge
    assert 'imports' in out


# --- format_blast_radius_text ---

def test_blast_radius_text_no_dependents():
    result = BlastRadiusResult(
        target_file="leaf.ts",
        direct_dependents=[],
        transitive_dependents=[],
        dependency_chains=[],
        policy_violations=[],
        risk_score=0.0,
        total_affected_files=0,
    )
    out = format_blast_radius_text(result)
    assert "Safe to modify" in out
    assert "leaf.ts" in out
    assert "LOW" in out


def test_blast_radius_text_with_dependents_and_violations():
    violation = PolicyViolation(
        zone="billing",
        violated_file="billing.ts",
        dependency_chain=["billing.ts", "a.ts"],
        severity="critical",
        message="reaches BILLING zone",
    )
    warning = PolicyViolation(
        zone="infrastructure",
        violated_file="db.ts",
        dependency_chain=["db.ts", "a.ts"],
        severity="warning",
        message="reaches INFRASTRUCTURE zone",
    )
    result = BlastRadiusResult(
        target_file="a.ts",
        direct_dependents=["b.ts"],
        transitive_dependents=["c.ts"],
        dependency_chains=[["c.ts", "b.ts", "a.ts"]],
        policy_violations=[violation, warning],
        risk_score=0.85,
        total_affected_files=2,
    )
    out = format_blast_radius_text(result)
    assert "Direct Dependents (1 files)" in out
    assert "Transitive Dependents (1 files)" in out
    assert "POLICY VIOLATIONS" in out
    assert "CRITICAL" in out
    assert "WARNING" in out
    assert "🔴" in out
    assert "🟡" in out


# --- format_execution_path_text ---

def test_execution_path_text_exists():
    result = ExecutionPathResult(
        start_file="a.ts",
        end_file="c.ts",
        path=["a.ts", "b.ts", "c.ts"],
        path_length=2,
        exists=True,
    )
    out = format_execution_path_text(result)
    assert "a.ts" in out
    assert "c.ts" in out
    assert "2 hops" in out
    assert "a.ts -> b.ts -> c.ts" in out


def test_execution_path_text_not_exists():
    result = ExecutionPathResult(
        start_file="a.ts",
        end_file="z.ts",
        path=None,
        path_length=None,
        exists=False,
    )
    out = format_execution_path_text(result)
    assert "No dependency path exists" in out


def test_execution_path_text_empty_path():
    result = ExecutionPathResult(
        start_file="a.ts",
        end_file="a.ts",
        path=[],
        path_length=0,
        exists=True,
    )
    out = format_execution_path_text(result)
    assert "0 hops" in out


# --- format_domain_context_text ---

def test_domain_context_text_with_neighbors_and_relationships():
    result = DomainContextResult(
        concept="billing",
        matching_files=["billing.ts"],
        context_files=["billing.ts", "checkout.ts"],
        relationships=[("checkout.ts", "billing.ts")],
    )
    out = format_domain_context_text(result)
    assert '"billing"' in out
    assert "billing.ts" in out
    assert "Related files (1)" in out
    assert "checkout.ts imports billing.ts" in out


def test_domain_context_text_no_neighbors_no_relationships():
    result = DomainContextResult(
        concept="orphan",
        matching_files=["orphan.ts"],
        context_files=["orphan.ts"],
        relationships=[],
    )
    out = format_domain_context_text(result)
    assert "orphan.ts" in out
    assert "Related files" not in out
    assert "Relationships" not in out


# --- format_domain_context_mermaid ---

def test_domain_context_mermaid_empty():
    result = DomainContextResult(
        concept="x",
        matching_files=[],
        context_files=[],
        relationships=[],
    )
    assert format_domain_context_mermaid(result) == ""


def test_domain_context_mermaid_with_relationships():
    result = DomainContextResult(
        concept="billing",
        matching_files=["billing.ts"],
        context_files=["billing.ts", "checkout.ts"],
        relationships=[("checkout.ts", "billing.ts")],
    )
    out = format_domain_context_mermaid(result)
    assert "graph TD" in out
    assert "imports" in out
    # Matching file should have green style
    assert "fill:#4caf50" in out


# --- format_file_info_text ---

def test_file_info_text_minimal():
    result = FileInfoResult(
        filepath="leaf.ts",
        language="typescript",
        imports_from=[],
        imported_by=[],
        exports=[],
        policy_zones=[],
        degree_centrality=0.0,
    )
    out = format_file_info_text(result)
    assert "leaf.ts" in out
    assert "typescript" in out
    assert "Policy Zones" not in out
    assert "Exports" not in out
    assert "Imports from" not in out
    assert "Imported by" not in out


def test_file_info_text_full():
    result = FileInfoResult(
        filepath="billing.ts",
        language="typescript",
        imports_from=["queries.ts"],
        imported_by=["checkout.ts"],
        exports=["processCharge"],
        policy_zones=["billing"],
        degree_centrality=0.5,
    )
    out = format_file_info_text(result)
    assert "Policy Zones:** billing" in out
    assert "Exports:** processCharge" in out
    assert "Imports from (1):**" in out
    assert "Imported by (1):**" in out


# --- format_repo_overview_text ---

def test_repo_overview_text_minimal():
    result = RepoOverviewResult(
        total_files=3,
        languages={"typescript": 3},
        most_connected=[],
        policy_zone_files={},
        risk_hotspots=[],
    )
    out = format_repo_overview_text(result)
    assert "Total files:** 3" in out
    assert "typescript: 3 files" in out
    assert "Most Connected" not in out
    assert "Risk Hotspots" not in out
    assert "Policy Zones" not in out


def test_repo_overview_text_full():
    result = RepoOverviewResult(
        total_files=10,
        languages={"typescript": 8, "python": 2},
        most_connected=[("a.ts", 0.9), ("b.ts", 0.5)],
        policy_zone_files={"billing": ["billing.ts", "checkout.ts"]},
        risk_hotspots=[("a.ts", 0.7)],
    )
    out = format_repo_overview_text(result)
    assert "Most Connected Files" in out
    assert "a.ts (centrality: 0.9)" in out
    assert "Risk Hotspots" in out
    assert "a.ts (betweenness: 0.7)" in out
    assert "Policy Zones" in out
    assert "billing" in out
