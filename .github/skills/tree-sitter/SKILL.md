# Tree-sitter — Stack Skill

## What It Is

Tree-sitter is an incremental parsing library that builds concrete syntax trees for source code. It supports many languages via separate grammar packages. Sentinel uses it for **language-agnostic AST extraction** in LLM-assisted detectors.

## Packages

| Package | Purpose |
|---------|---------|
| `tree-sitter>=0.24` | Core parser library (C bindings) |
| `tree-sitter-javascript>=0.23` | JavaScript grammar |
| `tree-sitter-typescript>=0.23` | TypeScript + TSX grammars |

All are **optional dependencies** — Sentinel degrades gracefully to regex extraction when tree-sitter is not installed.

## API Patterns (v0.24+)

### Language Setup

```python
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

JS_LANG = Language(tsjs.language())
TS_LANG = Language(tsts.language_typescript())
TSX_LANG = Language(tsts.language_tsx())
```

### Parsing

```python
parser = Parser(JS_LANG)
tree = parser.parse(source_bytes)  # Must be bytes, not str
root = tree.root_node
```

### Node Structure

- `node.type` — grammar node type string (e.g. `"function_declaration"`)
- `node.text` — raw bytes of the node's source
- `node.children` — list of child nodes
- `node.start_point` / `node.end_point` — `(row, column)` tuples (0-indexed rows)
- `node.child_by_field_name("name")` — named field access

### Key JS/TS Node Types

| Node Type | What It Is | Key Children |
|-----------|-----------|--------------|
| `function_declaration` | `function foo() {}` | `identifier`, `formal_parameters`, `statement_block` |
| `class_declaration` | `class Foo {}` | `identifier`, `class_body` |
| `method_definition` | Class method | `property_identifier`, `formal_parameters`, `statement_block` |
| `lexical_declaration` | `const/let` (arrow fns) | `variable_declarator` → `arrow_function` |
| `arrow_function` | `(x) => {}` | `formal_parameters`, `statement_block` or expression |
| `export_statement` | `export function/class` | Wraps the declaration as child |
| `import_statement` | `import { x } from "y"` | `import_clause`, `string` (source) |
| `comment` | `// ...` or `/** ... */` | Leaf node |

### JSDoc Extraction

JSDoc comments (`/** ... */`) are **sibling** nodes preceding the declaration, not children. To extract:

```python
def get_jsdoc(node, root):
    """Get JSDoc comment preceding a declaration node."""
    idx = root.children.index(node)
    if idx > 0:
        prev = root.children[idx - 1]
        if prev.type == "comment" and prev.text.startswith(b"/**"):
            return prev.text.decode("utf-8")
    return None
```

For methods inside `class_body`, check `class_body.children` for preceding comments.

### Export Wrapping (TS common pattern)

In TypeScript, `export function foo()` produces an `export_statement` wrapping the function:

```python
if node.type == "export_statement":
    for child in node.children:
        if child.type in ("function_declaration", "class_declaration"):
            # Process the inner declaration
```

## Sentinel Integration Rules

1. **Optional dependency** — always guard imports with `try/except ImportError`
2. **Bytes input** — tree-sitter requires `bytes`, not `str`. Encode with UTF-8.
3. **Line numbers** — tree-sitter uses 0-indexed rows. Add 1 for user-facing line numbers.
4. **Graceful degradation** — when tree-sitter is not available, fall back to regex extraction
5. **No tree-sitter in core deps** — listed under `[project.optional-dependencies]` only
