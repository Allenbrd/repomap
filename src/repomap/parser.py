"""AST parsing engine using tree-sitter for Python, JavaScript, and TypeScript."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript

from .config import DEFAULT_EXCLUDE_PATTERNS, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# Initialize tree-sitter languages and parsers
_LANGUAGES: dict[str, tree_sitter.Language] = {
    "python": tree_sitter.Language(tree_sitter_python.language()),
    "javascript": tree_sitter.Language(tree_sitter_javascript.language()),
    "typescript": tree_sitter.Language(tree_sitter_typescript.language_typescript()),
    "tsx": tree_sitter.Language(tree_sitter_typescript.language_tsx()),
}


def _get_parser(language: str) -> tree_sitter.Parser:
    """Create a parser for the given language."""
    lang = _LANGUAGES[language]
    return tree_sitter.Parser(lang)


@dataclass
class ImportEdge:
    source_file: str  # absolute path of the importing file
    target_file: str  # absolute path of the imported file
    imported_names: list[str]  # specific names imported
    line_number: int  # line where the import occurs


@dataclass
class FileNode:
    filepath: str  # absolute path
    language: str  # "python" | "javascript" | "typescript"
    exports: list[str] = field(default_factory=list)
    imports: list[ImportEdge] = field(default_factory=list)


def _find_child_by_type(node: tree_sitter.Node, type_name: str) -> tree_sitter.Node | None:
    """Find the first child node with the given type."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _resolve_js_import_path(source_file: str, import_path: str, root_path: str) -> str | None:
    """Resolve a JS/TS relative import path to an absolute file path."""
    if not import_path.startswith("."):
        return None  # external package

    source_dir = os.path.dirname(source_file)
    resolved = os.path.normpath(os.path.join(source_dir, import_path))

    # Try exact match first, then with extensions, then as directory with index
    extensions = [".ts", ".tsx", ".js", ".jsx"]

    if os.path.isfile(resolved):
        return resolved

    for ext in extensions:
        candidate = resolved + ext
        if os.path.isfile(candidate):
            return candidate

    # Try index file resolution
    for ext in extensions:
        candidate = os.path.join(resolved, f"index{ext}")
        if os.path.isfile(candidate):
            return candidate

    return None


def _resolve_python_import(source_file: str, module_path: str, dots: int, root_path: str) -> str | None:
    """Resolve a Python relative import to an absolute file path."""
    source_dir = os.path.dirname(source_file)

    # Go up `dots - 1` directories (one dot = current package)
    base_dir = source_dir
    for _ in range(dots - 1):
        base_dir = os.path.dirname(base_dir)

    if module_path:
        parts = module_path.split(".")
        candidate_dir = os.path.join(base_dir, *parts)
        # Could be a module (directory with __init__.py) or a file
        candidate_file = candidate_dir + ".py"
        if os.path.isfile(candidate_file):
            return candidate_file
        init_file = os.path.join(candidate_dir, "__init__.py")
        if os.path.isfile(init_file):
            return init_file
    else:
        # `from . import X` — X is a module in the same package
        return None  # handled at import name level

    return None


def _extract_python_imports(tree: tree_sitter.Tree, source_file: str, root_path: str) -> tuple[list[ImportEdge], list[str]]:
    """Extract imports and exports from a Python AST."""
    imports: list[ImportEdge] = []
    exports: list[str] = []

    for node in tree.root_node.children:
        if node.type == "import_from_statement":
            # Check for relative import
            rel_import = _find_child_by_type(node, "relative_import")
            if rel_import:
                prefix = _find_child_by_type(rel_import, "import_prefix")
                dots = len(prefix.text.decode()) if prefix else 0
                dotted = _find_child_by_type(rel_import, "dotted_name")
                module_path = dotted.text.decode() if dotted else ""

                # Collect imported names
                imported_names = []
                for child in node.children:
                    if child.type == "dotted_name" and child != dotted:
                        imported_names.append(child.text.decode())

                target = _resolve_python_import(source_file, module_path, dots, root_path)
                if target:
                    imports.append(ImportEdge(
                        source_file=source_file,
                        target_file=target,
                        imported_names=imported_names,
                        line_number=node.start_point.row + 1,
                    ))
                elif not module_path and dots > 0:
                    # `from . import X` — try each name as a module
                    source_dir = os.path.dirname(source_file)
                    base_dir = source_dir
                    for _ in range(dots - 1):
                        base_dir = os.path.dirname(base_dir)
                    for name in imported_names:
                        candidate = os.path.join(base_dir, name + ".py")
                        if os.path.isfile(candidate):
                            imports.append(ImportEdge(
                                source_file=source_file,
                                target_file=candidate,
                                imported_names=[name],
                                line_number=node.start_point.row + 1,
                            ))
            else:
                # Absolute import: from X import Y — skip, external
                pass

        elif node.type == "import_statement":
            # import X — skip external modules
            pass

        # Extract exports: top-level function/class defs, and __all__
        elif node.type == "function_definition":
            name_node = _find_child_by_type(node, "identifier")
            if name_node and not name_node.text.decode().startswith("_"):
                exports.append(name_node.text.decode())
        elif node.type == "class_definition":
            name_node = _find_child_by_type(node, "identifier")
            if name_node:
                exports.append(name_node.text.decode())
        elif node.type == "expression_statement":
            # Check for top-level assignments (module-level constants)
            assign = _find_child_by_type(node, "assignment")
            if assign:
                left = assign.children[0] if assign.children else None
                if left and left.type == "identifier" and not left.text.decode().startswith("_"):
                    exports.append(left.text.decode())

    return imports, exports


def _extract_js_ts_imports(tree: tree_sitter.Tree, source_file: str, root_path: str) -> tuple[list[ImportEdge], list[str]]:
    """Extract imports and exports from a JavaScript/TypeScript AST."""
    imports: list[ImportEdge] = []
    exports: list[str] = []

    for node in tree.root_node.children:
        if node.type == "import_statement":
            # Find the source string
            source_node = _find_child_by_type(node, "string")
            if not source_node:
                continue
            frag = _find_child_by_type(source_node, "string_fragment")
            if not frag:
                continue
            import_path = frag.text.decode()

            # Collect imported names
            imported_names = []
            clause = _find_child_by_type(node, "import_clause")
            if clause:
                # Default import
                ident = _find_child_by_type(clause, "identifier")
                if ident:
                    imported_names.append(ident.text.decode())
                # Named imports
                named = _find_child_by_type(clause, "named_imports")
                if named:
                    for spec in named.children:
                        if spec.type == "import_specifier":
                            name_node = _find_child_by_type(spec, "identifier")
                            if name_node:
                                imported_names.append(name_node.text.decode())

            target = _resolve_js_import_path(source_file, import_path, root_path)
            if target:
                imports.append(ImportEdge(
                    source_file=source_file,
                    target_file=target,
                    imported_names=imported_names,
                    line_number=node.start_point.row + 1,
                ))

        elif node.type == "lexical_declaration":
            # Check for require() calls: const x = require('./path')
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    name_node = _find_child_by_type(declarator, "identifier")
                    call = _find_child_by_type(declarator, "call_expression")
                    if call:
                        func = _find_child_by_type(call, "identifier")
                        if func and func.text.decode() == "require":
                            args = _find_child_by_type(call, "arguments")
                            if args:
                                str_node = _find_child_by_type(args, "string")
                                if str_node:
                                    frag = _find_child_by_type(str_node, "string_fragment")
                                    if frag:
                                        import_path = frag.text.decode()
                                        target = _resolve_js_import_path(source_file, import_path, root_path)
                                        if target:
                                            imports.append(ImportEdge(
                                                source_file=source_file,
                                                target_file=target,
                                                imported_names=[name_node.text.decode()] if name_node else [],
                                                line_number=node.start_point.row + 1,
                                            ))

        elif node.type == "export_statement":
            # Extract exported names
            for child in node.children:
                if child.type == "function_declaration":
                    name = _find_child_by_type(child, "identifier")
                    if name:
                        exports.append(name.text.decode())
                elif child.type == "class_declaration":
                    name = _find_child_by_type(child, "identifier")
                    if name:
                        exports.append(name.text.decode())
                elif child.type == "lexical_declaration":
                    for decl in child.children:
                        if decl.type == "variable_declarator":
                            name = _find_child_by_type(decl, "identifier")
                            if name:
                                exports.append(name.text.decode())
                elif child.type == "type_alias_declaration":
                    name = _find_child_by_type(child, "type_identifier")
                    if name:
                        exports.append(name.text.decode())
                elif child.type == "interface_declaration":
                    name = _find_child_by_type(child, "type_identifier")
                    if name:
                        exports.append(name.text.decode())

    return imports, exports


def _get_language_key(ext: str) -> str:
    """Map file extension to tree-sitter language key."""
    if ext == ".tsx":
        return "tsx"
    lang = SUPPORTED_EXTENSIONS.get(ext)
    if lang == "typescript":
        return "typescript"
    if lang == "javascript":
        return "javascript"
    if lang == "python":
        return "python"
    return lang or ""


def parse_file(filepath: str, root_path: str) -> FileNode | None:
    """Parse a single source file and extract imports/exports."""
    ext = os.path.splitext(filepath)[1]
    language = SUPPORTED_EXTENSIONS.get(ext)
    if not language:
        return None

    lang_key = _get_language_key(ext)
    if lang_key not in _LANGUAGES:
        return None

    try:
        with open(filepath, "rb") as f:
            source = f.read()
    except (OSError, IOError) as e:
        logger.warning("Could not read %s: %s", filepath, e)
        return None

    try:
        parser = _get_parser(lang_key)
        tree = parser.parse(source)
    except Exception as e:
        logger.warning("Failed to parse %s: %s", filepath, e)
        return None

    if tree.root_node.has_error:
        logger.warning("Syntax errors in %s, attempting best-effort parse", filepath)

    if language == "python":
        imports, exports = _extract_python_imports(tree, filepath, root_path)
    else:
        imports, exports = _extract_js_ts_imports(tree, filepath, root_path)

    return FileNode(
        filepath=filepath,
        language=language,
        exports=exports,
        imports=imports,
    )


def parse_directory(root_path: str, exclude_patterns: list[str] | None = None) -> list[FileNode]:
    """
    Recursively walk root_path, parse every supported source file,
    and return a list of FileNodes with their import/export edges.
    """
    if exclude_patterns is None:
        exclude_patterns = DEFAULT_EXCLUDE_PATTERNS

    root_path = os.path.abspath(root_path)
    file_nodes: list[FileNode] = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter out excluded directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not any(pat in d for pat in exclude_patterns)
        ]

        for filename in filenames:
            ext = os.path.splitext(filename)[1]
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(dirpath, filename)
            node = parse_file(filepath, root_path)
            if node is not None:
                file_nodes.append(node)

    return file_nodes
