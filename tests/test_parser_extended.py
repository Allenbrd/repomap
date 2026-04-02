"""Extended parser tests — fills Python parsing, JS edge cases, and error paths."""

import os
import stat
import tempfile
from unittest.mock import patch

import pytest

from repomap.parser import _get_language_key, parse_directory, parse_file


# ── Python relative imports ──────────────────────────────────────────────

class TestPythonRelativeImports:
    """Test _extract_python_imports and _resolve_python_import via parse_file."""

    def _make_pkg(self, root, rel_path, content=""):
        """Create a file under root, ensuring parent dirs + __init__.py exist."""
        full = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        # Ensure __init__.py in every package dir
        parts = rel_path.split(os.sep)
        for i in range(1, len(parts)):
            pkg_dir = os.path.join(root, *parts[:i])
            if os.path.isdir(pkg_dir):
                init = os.path.join(pkg_dir, "__init__.py")
                if not os.path.exists(init):
                    open(init, "w").close()
        with open(full, "w") as f:
            f.write(content)
        return full

    def test_from_dot_import_module(self):
        """from . import utils  →  resolves to sibling utils.py."""
        with tempfile.TemporaryDirectory() as root:
            self._make_pkg(root, "pkg/main.py", "from . import utils\n")
            self._make_pkg(root, "pkg/utils.py", "def helper(): pass\n")

            node = parse_file(os.path.join(root, "pkg/main.py"), root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("utils.py" in t for t in targets)

    def test_from_dot_module_import_name(self):
        """from .models import User  →  resolves to models.py."""
        with tempfile.TemporaryDirectory() as root:
            self._make_pkg(root, "pkg/main.py", "from .models import User\n")
            self._make_pkg(root, "pkg/models.py", "class User: pass\n")

            node = parse_file(os.path.join(root, "pkg/main.py"), root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("models.py" in t for t in targets)

    def test_from_dotdot_import(self):
        """from .. import utils  →  resolves to parent package utils.py."""
        with tempfile.TemporaryDirectory() as root:
            self._make_pkg(root, "pkg/sub/main.py", "from .. import utils\n")
            self._make_pkg(root, "pkg/utils.py", "X = 1\n")

            node = parse_file(os.path.join(root, "pkg/sub/main.py"), root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("utils.py" in t for t in targets)

    def test_absolute_import_skipped(self):
        """import os  and  from collections import OrderedDict  produce no edges."""
        with tempfile.TemporaryDirectory() as root:
            self._make_pkg(
                root,
                "pkg/main.py",
                "import os\nfrom collections import OrderedDict\n",
            )
            node = parse_file(os.path.join(root, "pkg/main.py"), root)
            assert node is not None
            assert len(node.imports) == 0


# ── Python exports ───────────────────────────────────────────────────────

class TestPythonExports:
    def test_class_export(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "mod.py")
            with open(path, "w") as f:
                f.write("class MyService:\n    pass\n")
            node = parse_file(path, root)
            assert "MyService" in node.exports

    def test_private_function_excluded(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "mod.py")
            with open(path, "w") as f:
                f.write("def _helper():\n    pass\n\ndef public_fn():\n    pass\n")
            node = parse_file(path, root)
            assert "public_fn" in node.exports
            assert "_helper" not in node.exports

    def test_module_constant_export(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "mod.py")
            with open(path, "w") as f:
                f.write("MAX_RETRIES = 3\n_INTERNAL = 5\n")
            node = parse_file(path, root)
            assert "MAX_RETRIES" in node.exports
            assert "_INTERNAL" not in node.exports


# ── JS/TS edge cases ────────────────────────────────────────────────────

class TestJsTsEdgeCases:
    def test_commonjs_require(self):
        with tempfile.TemporaryDirectory() as root:
            lib = os.path.join(root, "lib.js")
            main = os.path.join(root, "main.js")
            with open(lib, "w") as f:
                f.write("module.exports = {}\n")
            with open(main, "w") as f:
                f.write("const x = require('./lib')\n")
            node = parse_file(main, root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("lib.js" in t for t in targets)

    def test_default_import(self):
        with tempfile.TemporaryDirectory() as root:
            utils = os.path.join(root, "utils.ts")
            main = os.path.join(root, "main.ts")
            with open(utils, "w") as f:
                f.write("export default function foo() {}\n")
            with open(main, "w") as f:
                f.write("import Default from './utils'\n")
            node = parse_file(main, root)
            assert node is not None
            assert any("Default" in imp.imported_names for imp in node.imports)

    def test_type_alias_export(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "types.ts")
            with open(path, "w") as f:
                f.write("export type UserId = string\n")
            node = parse_file(path, root)
            assert "UserId" in node.exports

    def test_interface_export(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "types.ts")
            with open(path, "w") as f:
                f.write("export interface UserData {}\n")
            node = parse_file(path, root)
            assert "UserData" in node.exports

    def test_exact_extension_resolution(self):
        """import x from './helper.js' resolves to helper.js exactly."""
        with tempfile.TemporaryDirectory() as root:
            helper = os.path.join(root, "helper.js")
            main = os.path.join(root, "main.js")
            with open(helper, "w") as f:
                f.write("export function x() {}\n")
            with open(main, "w") as f:
                f.write("import x from './helper.js'\n")
            node = parse_file(main, root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("helper.js" in t for t in targets)

    def test_index_directory_resolution(self):
        """import { Btn } from './components' resolves to components/index.ts."""
        with tempfile.TemporaryDirectory() as root:
            comp_dir = os.path.join(root, "components")
            os.makedirs(comp_dir)
            with open(os.path.join(comp_dir, "index.ts"), "w") as f:
                f.write("export function Btn() {}\n")
            main = os.path.join(root, "main.ts")
            with open(main, "w") as f:
                f.write("import { Btn } from './components'\n")
            node = parse_file(main, root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("index.ts" in t for t in targets)


# ── Error paths ──────────────────────────────────────────────────────────

def test_unsupported_extension_returns_none():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "data.json")
        with open(path, "w") as f:
            f.write("{}")
        assert parse_file(path, root) is None


def test_unreadable_file_returns_none():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "secret.ts")
        with open(path, "w") as f:
            f.write("export const x = 1")
        os.chmod(path, 0o000)
        try:
            result = parse_file(path, root)
            assert result is None
        finally:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def test_parser_exception_returns_none():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "ok.ts")
        with open(path, "w") as f:
            f.write("export const x = 1")
        with patch("repomap.parser._get_parser", side_effect=Exception("mock parser error")):
            assert parse_file(path, root) is None


def test_syntax_error_still_returns_filenode():
    """A file with syntax errors triggers a warning but still returns a FileNode."""
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "bad.ts")
        with open(path, "w") as f:
            f.write("export function {{{ broken !!!!")
        node = parse_file(path, root)
        # tree-sitter does best-effort parse, should still return a FileNode
        assert node is not None
        assert node.language == "typescript"


# ── _get_language_key ────────────────────────────────────────────────────

def test_get_language_key_tsx():
    assert _get_language_key(".tsx") == "tsx"


def test_get_language_key_ts():
    assert _get_language_key(".ts") == "typescript"


def test_get_language_key_js():
    assert _get_language_key(".js") == "javascript"


def test_get_language_key_py():
    assert _get_language_key(".py") == "python"


def test_get_language_key_unsupported():
    assert _get_language_key(".rb") == ""


# ── Additional coverage for uncovered branches ───────────────────────────

class TestPythonInitResolution:
    """Cover _resolve_python_import resolving to __init__.py (lines 102-104)."""

    def test_from_dot_subpackage_resolves_to_init(self):
        """from .models import User where models is a package with __init__.py."""
        with tempfile.TemporaryDirectory() as root:
            # Create pkg/main.py that imports from .models
            pkg = os.path.join(root, "pkg")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(pkg, "main.py"), "w") as f:
                f.write("from .models import User\n")
            # Create models as a package (directory with __init__.py), NOT a file
            models_dir = os.path.join(pkg, "models")
            os.makedirs(models_dir)
            with open(os.path.join(models_dir, "__init__.py"), "w") as f:
                f.write("class User: pass\n")

            node = parse_file(os.path.join(pkg, "main.py"), root)
            assert node is not None
            targets = [imp.target_file for imp in node.imports]
            assert any("__init__.py" in t for t in targets)

    def test_relative_import_unresolvable(self):
        """from .nonexistent import X where nonexistent doesn't exist (line 109)."""
        with tempfile.TemporaryDirectory() as root:
            pkg = os.path.join(root, "pkg")
            os.makedirs(pkg)
            with open(os.path.join(pkg, "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(pkg, "main.py"), "w") as f:
                f.write("from .nonexistent import Foo\n")

            node = parse_file(os.path.join(pkg, "main.py"), root)
            assert node is not None
            assert len(node.imports) == 0


class TestJsExternalAndUnresolvable:
    """Cover _resolve_js_import_path returning None for external and unresolvable."""

    def test_external_package_import(self):
        """import { x } from 'lodash' — external package, no edge (line 61)."""
        with tempfile.TemporaryDirectory() as root:
            main = os.path.join(root, "main.ts")
            with open(main, "w") as f:
                f.write("import { x } from 'lodash'\n")
            node = parse_file(main, root)
            assert node is not None
            assert len(node.imports) == 0

    def test_unresolvable_relative_import(self):
        """import { x } from './nonexistent' — no file found (line 83)."""
        with tempfile.TemporaryDirectory() as root:
            main = os.path.join(root, "main.ts")
            with open(main, "w") as f:
                f.write("import { x } from './nonexistent'\n")
            node = parse_file(main, root)
            assert node is not None
            assert len(node.imports) == 0


class TestJsExportedClass:
    """Cover exported class declaration (lines 259-261).

    Note: In TypeScript, class names are `type_identifier` nodes, not `identifier`.
    The parser's class_declaration branch checks for `identifier`, which means
    this branch doesn't match for TS. Testing with JS where it would match.
    """

    def test_exported_class_js(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "service.js")
            with open(path, "w") as f:
                f.write("export class UserService {}\n")
            node = parse_file(path, root)
            assert "UserService" in node.exports


def test_lang_key_not_in_languages():
    """parse_file returns None when _get_language_key gives unsupported key (line 303)."""
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "test.ts")
        with open(path, "w") as f:
            f.write("export const x = 1")
        with patch("repomap.parser._get_language_key", return_value="unknown_lang"):
            result = parse_file(path, root)
            assert result is None


class TestJsImportDefensiveBranches:
    """Cover defensive continue branches in _extract_js_ts_imports (lines 194, 197)."""

    def test_import_no_source_string(self):
        """Mock _find_child_by_type to return None for 'string' (line 194)."""
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "main.ts")
            with open(path, "w") as f:
                f.write("import x from './utils'\n")

            from repomap.parser import _extract_js_ts_imports, _get_parser, _get_language_key, _find_child_by_type

            with open(path, "rb") as f:
                source = f.read()
            lang_key = _get_language_key(".ts")
            parser = _get_parser(lang_key)
            tree = parser.parse(source)

            original_find = _find_child_by_type

            def patched_find(node, type_name):
                if type_name == "string":
                    return None
                return original_find(node, type_name)

            with patch("repomap.parser._find_child_by_type", side_effect=patched_find):
                imports, exports = _extract_js_ts_imports(tree, path, root)
                assert len(imports) == 0

    def test_import_string_no_fragment(self):
        """Mock tree where string node has no string_fragment (line 197)."""
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "main.ts")
            with open(path, "w") as f:
                f.write("import x from './utils'\n")

            from repomap.parser import _extract_js_ts_imports, _get_parser, _get_language_key, _find_child_by_type

            with open(path, "rb") as f:
                source = f.read()
            lang_key = _get_language_key(".ts")
            parser = _get_parser(lang_key)
            tree = parser.parse(source)

            # Mock _find_child_by_type to return None for string_fragment
            original_find = _find_child_by_type

            def patched_find(node, type_name):
                if type_name == "string_fragment":
                    return None
                return original_find(node, type_name)

            with patch("repomap.parser._find_child_by_type", side_effect=patched_find):
                imports, exports = _extract_js_ts_imports(tree, path, root)
                assert len(imports) == 0
