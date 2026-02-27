# 🤡 theclown

A toy/vibecoded Rust interpreter written in Python.

Uses [tree-sitter-rust](https://github.com/tree-sitter/tree-sitter-rust) for parsing and Python's structural pattern matching (`match`/`case`) for AST walking. The interpreter runs a meaningful subset of Rust — enough for structs, match expressions, Option types, recursion, control flow, and move semantics — in a single-file interpreter.

Named after kRusty the Clown. Vaguely inspired by pydantic's [monty](https://github.com/pydantic/monty), which compiles a Python subset using Rust. theclown goes the other way: it interprets Rust in Python 🤡.

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

- Integer, float (`f64`), and boolean literals, arithmetic with correct Rust semantics (truncating division, not floor division)
- `let` / `let mut` bindings, variable shadowing, block scoping
- `const` declarations
- Compound assignment operators (`+=`, `-=`, `*=`, `/=`, `%=`)
- `use` declarations (accepted and ignored — no module system)
- Attributes (`#[derive(...)]`, `#[allow(...)]`, etc.) accepted and ignored — no macro expansion
- References (`&x`, `&mut x`) accepted as pass-through — the expression evaluates to the inner value (no borrow checking)
- `if` / `else if` / `else` as expressions
- `match` expressions with literal, wildcard (`_`), and or-pattern (`|`) arms
- `while`, `for` with range expressions (`..` and `..=`), `loop` with `break`-as-value
- `break`, `continue` in all loop forms
- Functions with parameters, recursion, and early `return`
- `println!` with format strings and arbitrary expressions
- Move semantics for strings, arrays, and structs (primitives copy, non-primitives move, use-after-move raises `ClownMoveError`)
- Tuple literals and destructuring in `let` bindings
- Type casts with `as` for numeric primitives (`i64 as f64`, `f64 as i64`, etc.); unsupported targets (e.g. `as char`) raise `OutOfDepthError`
- Math builtins: method style (`x.sqrt()`, `x.abs()`, `x.sin()`, …) and scoped style (`f64::sqrt(x)`)
- Arrays (`[1, 2, 3]`) and `vec![]` macro with indexing, `.len()`, `.push()`, `.pop()`
- Structs: definition, construction, field access, and inherent `impl` blocks with methods (including `self` receiver)
- Enums: unit variants (`Direction::North`) and tuple variants (`Shape::Circle(5.0)`), with `match` destructuring
- Built-in `Option<T>`: `Some(x)`, `None`, `.unwrap()`, `.unwrap_or()`, `.is_some()`, `.is_none()`, and `?` early-return operator

## Unsupported features

theclown uses a whitelist-based evaluator. Any Rust syntax not on the list is rejected with an `OutOfDepthError`:

```
OutOfDepthError: theclown doesn't understand trait_item yet
```

Notable exclusions: traits, generics, closures, struct-like enum variants (`Foo { x: i64 }`), `impl` blocks for enums, and `use` for actual module resolution.

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
