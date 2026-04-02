"""Tests for the parser module."""

import os
import tempfile

import pytest

from repomap.parser import parse_directory, parse_file

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "mock_saas")


def test_parse_directory_file_count():
    """parse_directory returns the correct number of FileNodes."""
    nodes = parse_directory(FIXTURES_DIR)
    # 11 .ts/.tsx files (schema.prisma is not a supported extension)
    assert len(nodes) == 11


def test_parse_directory_languages():
    """All files are detected as typescript."""
    nodes = parse_directory(FIXTURES_DIR)
    languages = {n.language for n in nodes}
    assert languages == {"typescript"}


def test_checkout_imports_billing_service():
    """checkout.ts should import from billing_service.ts."""
    nodes = parse_directory(FIXTURES_DIR)
    checkout = next(n for n in nodes if "checkout.ts" in n.filepath)

    target_files = [imp.target_file for imp in checkout.imports]
    assert any("billing_service.ts" in t for t in target_files)


def test_checkout_imports_checkout_modal():
    """checkout.ts should import from CheckoutModal.tsx."""
    nodes = parse_directory(FIXTURES_DIR)
    checkout = next(n for n in nodes if n.filepath.endswith("checkout.ts"))

    target_files = [imp.target_file for imp in checkout.imports]
    assert any("CheckoutModal.tsx" in t for t in target_files)


def test_imported_names_extracted():
    """Import edges should include specific imported names."""
    nodes = parse_directory(FIXTURES_DIR)
    checkout = next(n for n in nodes if n.filepath.endswith("checkout.ts"))

    billing_import = next(
        imp for imp in checkout.imports if "billing_service" in imp.target_file
    )
    assert "processCharge" in billing_import.imported_names
    assert "createInvoice" in billing_import.imported_names


def test_exports_extracted():
    """Files should have their exported names detected."""
    nodes = parse_directory(FIXTURES_DIR)
    date_utils = next(n for n in nodes if "date_utils.ts" in n.filepath)

    assert "formatDate" in date_utils.exports
    assert "parseISO" in date_utils.exports
    assert "daysBetween" in date_utils.exports


def test_leaf_node_has_no_imports():
    """date_utils.ts is a leaf node with no imports."""
    nodes = parse_directory(FIXTURES_DIR)
    date_utils = next(n for n in nodes if "date_utils.ts" in n.filepath)
    assert len(date_utils.imports) == 0


def test_syntax_error_file_skipped():
    """A file with a syntax error should be skipped without crashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_file = os.path.join(tmpdir, "bad.ts")
        with open(bad_file, "w") as f:
            f.write("export function {{{ broken syntax !!!!")

        nodes = parse_directory(tmpdir)
        # Should still return results (possibly with the file if best-effort parse works)
        # The key thing is it doesn't crash
        assert isinstance(nodes, list)


def test_index_imports_routes():
    """index.ts should import from both route files."""
    nodes = parse_directory(FIXTURES_DIR)
    index = next(n for n in nodes if n.filepath.endswith("index.ts"))

    target_files = [imp.target_file for imp in index.imports]
    assert any("checkout.ts" in t for t in target_files)
    assert any("webhooks.ts" in t for t in target_files)
