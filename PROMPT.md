# Build a toy Rust interpreter in Python

Build "theclown" — a single-file Python interpreter for a subset of Rust. Use tree-sitter-rust for parsing and Python's `match`/`case` for AST walking. Any Rust feature not explicitly supported should be rejected with a clear error.

## Setup

```bash
uv init --python 3.10
uv add tree-sitter tree-sitter-rust
uv add --dev pytest
```

Single file: `theclown.py`, invoked as `uv run python theclown.py <file.rs>`.

## Architecture

```
.rs file → tree-sitter-rust parser → AST → evaluate(node) via match/case → stdout
```

The interpreter is a recursive `evaluate(node)` function (or method) that switches on `node.type` using `match`/`case`. Every supported node type gets an explicit `case`. The `case _:` default arm rejects anything unknown with a clear error — this is the "bouncer" pattern.

### tree-sitter API

```python
from tree_sitter import Language, Parser
import tree_sitter_rust

RUST = Language(tree_sitter_rust.language())
parser = Parser(RUST)
tree = parser.parse(bytes(source, "utf8"))
root = tree.root_node
```

Key accessors: `node.type`, `node.children`, `node.child_by_field_name("name")`, `node.text` (bytes), `node.child(index)`.

### Debugging strategy

Add a `--dump-ast` flag that prints the full tree-sitter AST and exits. Use it to discover node type names before implementing each feature:

```bash
echo 'fn main() { let x = 5; }' > /tmp/probe.rs
uv run python theclown.py --dump-ast /tmp/probe.rs
```

### Design decisions

- **Type annotations are ignored everywhere.** Rust code has `let x: i32`, `fn foo(n: i32) -> i32`, etc. tree-sitter parses these as child nodes. Skip them — no type checking, all values are dynamically typed Python objects.
- **Division/modulo must match Rust semantics.** Rust truncates toward zero (`-7 / 2 == -3`); Python floors toward negative infinity (`-7 // 2 == -4`). Get this right.
- **Functions get a fresh environment** — no closures, no access to outer variables.

## Testing

Tests are `.rs` files in `tests/`. A pytest harness (`tests/test_theclown.py`) runs the interpreter as a subprocess and checks stdout/stderr. Build incrementally — run `uv run pytest tests/` after each feature, every previous test must keep passing.

Comments below show expected output. "→ ErrorName" means non-zero exit with that error class name in stderr.

## Supported features and tests

### Bouncer (reject unsupported syntax)

```rust
// bouncer_struct.rs → OutOfDepthError
struct MyStruct {}

// bouncer_enum.rs → OutOfDepthError
enum Color { Red, Green, Blue }

// bouncer_trait.rs → OutOfDepthError
trait Printable { fn print(&self); }

// bouncer_use.rs → OutOfDepthError
use std::io;
fn main() {}

// bouncer_impl.rs → OutOfDepthError
impl Foo { fn new() -> Foo { Foo } }
```

### Arithmetic, literals, `println!`

`println!` supports format strings with `{}` placeholders and named captures like `{x}`. Expressions inside `println!` arguments must be fully evaluated (including nested arithmetic, function calls, and `as` casts).

```rust
// arith_precedence.rs → "7"
fn main() { println!("{}", 1 + 2 * 3); }

// arith_parens.rs → "9"
fn main() { println!("{}", (1 + 2) * 3); }

// arith_subtract.rs → "7"
fn main() { println!("{}", 10 - 3); }

// println_nested_parens.rs → "21"
fn main() { println!("{}", (1 + 2) * (3 + 4)); }

// println_unary.rs → "1"
fn main() { println!("{}", -1 + 2); }

// println_multi_args.rs → "3 7"
fn main() { println!("{} {}", 1 + 2, 3 + 4); }

// println_bool.rs → "true"
fn main() { println!("{}", 1 < 2); }

// adversarial_multi_arg.rs → "1 2"
fn main() { println!("{} {}", 1, 2); }

// neg_div.rs → "-3" then "-1"
fn main() {
    let a = 0 - 7;
    let b = a / 2;
    println!("{}", b);
    let c = a % 2;
    println!("{}", c);
}

// adversarial_div_zero.rs → ClownRuntimeError
fn main() { println!("{}", 5 / 0); }

// adversarial_mod_zero.rs → ClownRuntimeError
fn main() { println!("{}", 5 % 0); }
```

### Variables (`let` / `let mut`, shadowing, assignment)

```rust
// let_variables.rs → "6" then "15"
fn main() {
    let x = 5;
    let mut y = 10;
    let x = x + 1;
    y = y + 5;
    println!("{}", x);
    println!("{}", y);
}

// let_type_annotation.rs → "5"
fn main() { let x: i32 = 5; println!("{}", x); }

// error_immutable.rs → ClownMutabilityError
fn main() { let x = 5; x = 10; }

// adversarial_uninitialized.rs → ClownRuntimeError
fn main() { let x; println!("{}", x); }
```

### Block scoping (blocks are expressions)

```rust
// block_expr.rs → "6"
fn main() { let x = { let y = 5; y + 1 }; println!("{}", x); }

// error_scope.rs → ClownNameError
fn main() { let x = { let y = 5; y + 1 }; println!("{}", y); }
```

### Control flow (`if`/`else` as expressions, `while`, short-circuit `&&`/`||`)

```rust
// if_basic.rs → "1"
fn main() { let x = if true { 1 } else { 0 }; println!("{}", x); }

// if_else_if.rs → "2"
fn main() {
    let x = 2;
    let result = if x == 1 { 1 } else if x == 2 { 2 } else { 0 };
    println!("{}", result);
}

// if_false_side_effect.rs → "0"
fn main() { let mut x = 0; if false { x = 1; } println!("{}", x); }

// while_loop.rs → "5 4 3 2 1"
fn main() {
    let mut i = 5;
    while i > 0 { println!("{}", i); i = i - 1; }
}

// short_circuit.rs → "false" then "true"
fn main() {
    let x = false && (1 / 0 > 0);
    println!("{}", x);
    let y = true || (1 / 0 > 0);
    println!("{}", y);
}
```

### Functions (recursion, early return)

```rust
// fn_multiple.rs → "7" then "10"
fn add(a: i32, b: i32) -> i32 { a + b }
fn double(x: i32) -> i32 { x * 2 }
fn main() {
    println!("{}", add(3, 4));
    println!("{}", double(5));
}

// fn_return.rs → "42"
fn add_one(x: i32) -> i32 { return x + 1; }
fn main() { println!("{}", add_one(41)); }

// fib_recursive.rs → "55"
fn fib(n: i32) -> i32 {
    if n <= 1 { n } else { fib(n - 1) + fib(n - 2) }
}
fn main() { println!("{}", fib(10)); }

// println_call.rs → "5"
fn add(a: i32, b: i32) -> i32 { a + b }
fn main() { println!("{}", add(2, 3)); }

// println_capture.rs → "42" then "hello world" then "42 and world"
fn main() {
    let x = 42;
    let name = "world";
    println!("{x}");
    println!("hello {name}");
    println!("{x} and {name}");
}

// error_wrong_arity.rs → ClownRuntimeError
fn add(a: i32, b: i32) -> i32 { a + b }
fn main() { println!("{}", add(1)); }
```

### Move semantics (strings move, primitives copy)

```rust
// move_strings.rs → ClownMoveError
fn main() { let a = "hello"; let b = a; println!("{}", a); }

// move_primitives.rs → "10" then "10"
fn main() { let a = 10; let b = a; println!("{}", a); println!("{}", b); }
```

### Loops (`for` with ranges, `loop`, `break`/`continue`)

`for` supports `..` (exclusive) and `..=` (inclusive) ranges. `loop` is an expression — `break value` returns a value. `break`/`continue` work in `for`, `while`, and `loop`.

```rust
// for_range.rs → "0 1 2 3 4"
fn main() { for i in 0..5 { println!("{}", i); } }

// for_range_inclusive.rs → "1 2 3 4 5"
fn main() { for i in 1..=5 { println!("{}", i); } }

// for_sum.rs → "5050"
fn main() {
    let mut sum = 0;
    for i in 1..=100 { sum = sum + i; }
    println!("{}", sum);
}

// loop_break.rs → "3"
fn main() {
    let mut i = 0;
    loop { if i >= 3 { break; } i = i + 1; }
    println!("{}", i);
}

// loop_break_value.rs → "42"
fn main() { let x = loop { break 42; }; println!("{}", x); }

// while_break.rs → "5"
fn main() {
    let mut i = 0;
    while true { if i >= 5 { break; } i = i + 1; }
    println!("{}", i);
}

// while_continue.rs → "1 3 5 7 9"
fn main() {
    let mut i = 0;
    while i < 10 {
        i = i + 1;
        if i % 2 == 0 { continue; }
        println!("{}", i);
    }
}
```

### Floating-point literals and arithmetic

`f64` values are supported. Mixed int/float arithmetic promotes to float. Display matches Rust: whole-number floats print without a decimal point (`42.0` displays as `42`).

```rust
// float_basic.rs → "5.140000000000001" then "6.28" then "2"
fn main() {
    let x: f64 = 3.14;
    let y: f64 = 2.0;
    println!("{}", x + y);
    println!("{}", x * y);
    let mut z: f64 = 1.5;
    z = z + 0.5;
    println!("{}", z);
}

// float_division.rs → "3.5" then "1"
fn main() {
    let a: f64 = 7.0;
    let b: f64 = 2.0;
    println!("{}", a / b);
    let c: f64 = 5.0;
    let d: f64 = 4.0;
    println!("{}", c % d);
}

// float_negation.rs → "-4.5" then "4.5"
fn main() {
    let x: f64 = 4.5;
    println!("{}", -x);
    println!("{}", -(-x));
}
```

### Type casts (`as`)

Numeric `as` casts between integer and float types. Unsupported targets (e.g. `as char`) are rejected with `OutOfDepthError`. Casts also work inside `println!` macro arguments, where `as` binds tighter than arithmetic operators.

```rust
// cast_basic.rs → "42" then "3"
fn main() {
    let x: i64 = 42;
    let y: f64 = x as f64;
    println!("{}", y);
    let z: f64 = 3.9;
    let w: i64 = z as i64;
    println!("{}", w);
}

// cast_println.rs → "25"
fn main() {
    let n: i64 = 10;
    println!("{}", n as f64 * 2.5);
}

// cast_unsupported.rs → OutOfDepthError
fn main() {
    let x: i64 = 65;
    let c = x as char;
    println!("{}", c);
}
```

### Tuples (literals and destructuring)

```rust
// tuple_basic.rs → "1 2"
fn main() { let (a, b) = (1, 2); println!("{} {}", a, b); }

// tuple_swap.rs → "2 1"
fn main() {
    let a = 1; let b = 2;
    let (a, b) = (b, a);
    println!("{} {}", a, b);
}

// tuple_nested_expr.rs → "3 12"
fn main() { let (x, y) = (1 + 2, 3 * 4); println!("{} {}", x, y); }
```
