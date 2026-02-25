# 🤡 theclown

A toy/vibecoded Rust interpreter written in Python.

Uses [tree-sitter-rust](https://github.com/tree-sitter/tree-sitter-rust) for parsing and Python's structural pattern matching (`match`/`case`) for AST walking. The interpreter runs a meaningful subset of Rust — enough for recursion, control flow, move semantics, and tuples — in a single ~700-line file.

Named after kRusty the Clown. Inspired by pydantic's [monty](https://github.com/pydantic/monty), which interprets a Python subset in Rust. theclown goes the other way: it interprets Rust in Python 🤡.

## Quickstart

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/davidefiocco/theclown.git
cd theclown
uv sync
uv run python theclown.py tests/fib_recursive.rs
# 55
```

## Supported features

- Integer and boolean literals, arithmetic with correct Rust semantics (truncating division, not floor division)
- `let` / `let mut` bindings, variable shadowing, block scoping
- `if` / `else if` / `else` as expressions
- `while`, `for` with range expressions (`..` and `..=`), `loop` with `break`-as-value
- `break`, `continue` in all loop forms
- Functions with parameters, recursion, and early `return`
- `println!` with format strings and arbitrary expressions
- Move semantics for strings (primitives copy, strings move, use-after-move raises `ClownMoveError`)
- Tuple literals and destructuring in `let` bindings

## Unsupported features

theclown uses a whitelist-based evaluator. Any Rust syntax not on the list is rejected with an `OutOfDepthError`:

```
OutOfDepthError: theclown doesn't understand struct_item yet
```

Notable exclusions: structs, enums, traits, generics, `impl` blocks, closures, references (`&` / `&mut`), pattern matching (`match` arms), and `use` declarations.

## Origin

`PROMPT.md` contains the a prompt to try to generate this project with an LLM.

## Architecture

The interpreter is a single file (`theclown.py`) with four main components:

- **`Interpreter.evaluate(node)`** — recursive AST walker using `match`/`case` with a strict whitelist. The `case _:` arm raises `OutOfDepthError`.
- **`Environment`** — a scope stack (`list[dict]`) supporting `define`, `get`, `set`, `move`, and `push_scope`/`pop_scope`.
- **Function table** — all `fn` items are registered in a first pass. Each call gets a fresh isolated `Environment` (no closures).
- **Pratt parser for `println!`** — tree-sitter represents macro arguments as flat token trees, so a small precedence-climbing parser evaluates expressions inside `println!`.

## Testing

Tests are `.rs` files in `tests/` exercised by a pytest harness that invokes the interpreter as a subprocess:

```bash
uv run pytest tests/
```

## AST debugging

```bash
uv run python theclown.py --dump-ast tests/fib_recursive.rs
```

Prints the full tree-sitter AST, useful for discovering node types before extending the interpreter.

## License

MIT
