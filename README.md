# RepoMap

Deterministic codebase intelligence for AI coding agents. An MCP server that replaces probabilistic grep with AST-backed graph math.

## The Problem

AI coding agents suffer from context starvation. They either guess blindly and break dependencies, or stuff the whole repo into context and hallucinate. `grep` returns zero structural insight — it can't trace transitive dependencies, resolve aliased imports, or identify that changing a utility function will cascade through billing-critical code paths.

## The Solution

RepoMap parses source files into an AST-backed dependency graph (using tree-sitter) and exposes MCP tools that return precise, deterministic answers:

- Which files are affected if you modify this one?
- What's the dependency chain between two files?
- Does this change hit a critical policy zone (billing, auth, PII)?
- What's the overall architecture of this repo?

No LLM guessing. No probabilistic search. Just graph math.

## Quick Start

```bash
# Clone and install
git clone https://github.com/Allenbrd/repomap.git
cd repomap
pip install -e .

# Run the MCP server
repomap

# Or run directly
python -m repomap.server
```

## Cursor Integration

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "repomap": {
      "command": "python",
      "args": ["-m", "repomap.server"],
      "cwd": "/path/to/repomap"
    }
  }
}
```

## Claude Code Integration

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "repomap": {
      "command": "python",
      "args": ["-m", "repomap.server"],
      "cwd": "/path/to/repomap"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `analyze_blast_radius` | Find all files affected by modifying a file, with risk scores and policy violations |
| `find_dependency_path` | Find the shortest dependency path between two files |
| `get_domain_context` | Find all files related to a domain concept (e.g., "billing", "checkout") |
| `get_repo_overview` | Get architectural overview: languages, hotspots, policy zones |
| `get_file_info` | Get detailed info about a file: imports, dependents, exports, centrality |

## How It Works

1. **AST Parsing** — tree-sitter parses Python, JavaScript, and TypeScript files to extract import/export relationships with zero false positives.
2. **Graph Construction** — Import edges are assembled into a NetworkX directed graph where `A → B` means "A imports from B".
3. **Graph Queries** — MCP tools use graph algorithms (ancestors, shortest path, centrality) to answer structural questions deterministically.
4. **Policy Zones** — Files are auto-tagged into zones (billing, auth, PII, infrastructure) based on path heuristics. Changes that reach policy zones trigger violations.
5. **Visualization** — Results include Mermaid diagrams for visual dependency mapping.

## Policy Zones

Files are automatically classified into policy zones based on path and filename keywords:

- **billing** — payment, stripe, invoice, checkout, subscription, charge
- **auth** — login, session, token, permission, oauth, password
- **pii** — user_service, profile, personal, gdpr
- **infrastructure** — database, schema, migration, cache, redis, prisma

Override auto-detection with `.repomap.yml` in your repo root:

```yaml
policy_zones:
  billing:
    - "src/services/billing_service.ts"
    - "src/routes/checkout.ts"
  auth:
    - "src/middleware/auth.ts"
  critical:
    - "src/db/schema.prisma"
```

## Supported Languages

- Python (`.py`)
- JavaScript (`.js`, `.jsx`)
- TypeScript (`.ts`, `.tsx`)

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## License

MIT
