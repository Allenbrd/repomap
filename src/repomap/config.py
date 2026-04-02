"""Configuration and constants for RepoMap."""

DEFAULT_EXCLUDE_PATTERNS = [
    "node_modules",
    ".git",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "venv",
    ".venv",
    ".tox",
    "egg-info",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
]

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

POLICY_ZONE_KEYWORDS: dict[str, list[str]] = {
    "billing": [
        "billing", "payment", "stripe", "invoice", "checkout",
        "subscription", "charge", "price", "revenue",
        "pricing", "plan", "trial", "paid", "setup-intent",
    ],
    "auth": [
        "auth", "login", "session", "token", "permission",
        "rbac", "oauth", "credential", "password",
    ],
    "pii": [
        "user_service", "user_handler", "profile", "personal", "gdpr", "pii",
    ],
    "infrastructure": [
        "database", "schema", "migration", "queue", "cache", "redis", "prisma",
    ],
}

RISK_THRESHOLDS: dict[str, float] = {
    "low": 0.3,
    "medium": 0.6,
    "high": 0.8,
}
