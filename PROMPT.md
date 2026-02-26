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

Structs, `impl` blocks, and `use` declarations are now supported. The bouncer still rejects enums and traits.

```rust
// bouncer_enum.rs → OutOfDepthError
enum Color { Red, Green, Blue }

// bouncer_trait.rs → OutOfDepthError
trait Printable { fn print(&self); }
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

### Math builtins

Method-style calls on `f64` values and scoped `f64::` free-function calls. Supported methods: `sqrt`, `abs`, `floor`, `ceil`, `round`, `sin`, `cos`, `tan`, `ln`, `log2`, `log10`, `powi`, `powf`, `min`, `max`. Unknown methods raise `OutOfDepthError`.

```rust
// math_methods.rs → "4" then "3.5" then "-4" then "-3" then "5"
fn main() {
    let x: f64 = 16.0;
    println!("{}", x.sqrt());
    let y: f64 = -3.5;
    println!("{}", y.abs());
    println!("{}", y.floor());
    println!("{}", y.ceil());
    println!("{}", x.sqrt() + 1.0);
}

// math_scoped.rs → "5" then "7"
fn main() {
    let x: f64 = 25.0;
    let y: f64 = f64::sqrt(x);
    println!("{}", y);
    let z: f64 = f64::abs(-7.0);
    println!("{}", z);
}

// math_trig.rs → "0" then "1" then "1"
fn main() {
    let x: f64 = 0.0;
    println!("{}", x.sin());
    println!("{}", x.cos());
    let pi: f64 = 3.141592653589793;
    let half_pi: f64 = pi / 2.0;
    println!("{}", half_pi.sin());
}
```

### Arrays and `vec![]`

Fixed-size array literals (`[1, 2, 3]`) and growable `vec![]` macro. Indexing with `a[i]` for read and write. Methods: `.len()`, `.push(val)`, `.pop()`. Arrays and vecs move on assignment (use-after-move raises `ClownMoveError`). Out-of-bounds indexing raises `ClownRuntimeError`.

```rust
// array_basic.rs → "10" then "30" then "3"
fn main() {
    let a = [10, 20, 30];
    println!("{}", a[0]);
    println!("{}", a[2]);
    println!("{}", a.len());
}

// array_mut.rs → "10 2 30"
fn main() {
    let mut a = [1, 2, 3];
    a[0] = 10;
    a[2] = 30;
    println!("{} {} {}", a[0], a[1], a[2]);
}

// array_oob.rs → ClownRuntimeError
fn main() {
    let a = [1, 2, 3];
    println!("{}", a[5]);
}

// vec_macro.rs → "3" then "3"
fn main() {
    let mut v = vec![1, 2];
    v.push(3);
    println!("{}", v.len());
    println!("{}", v[2]);
}

// vec_pop.rs → "30" then "2"
fn main() {
    let mut v = vec![10, 20, 30];
    let x = v.pop();
    println!("{}", x);
    println!("{}", v.len());
}

// array_move.rs → ClownMoveError
fn main() {
    let a = [1, 2, 3];
    let b = a;
    println!("{}", a[0]);
}
```

### Constants and compound assignment

`const` declarations are evaluated at top level and accessible from all functions. Compound assignment operators (`+=`, `-=`, `*=`, `/=`, `%=`) work on mutable variables.

```rust
// const_basic.rs → "100" then "3.14"
const MAX: i64 = 100;
const PI: f64 = 3.14;
fn main() {
    println!("{}", MAX);
    println!("{}", PI);
}

// compound_assign.rs → "15" then "12" then "24" then "4" then "1" then "2"
fn main() {
    let mut x: i64 = 10;
    x += 5;
    println!("{}", x);
    x -= 3;
    println!("{}", x);
    x *= 2;
    println!("{}", x);
    x /= 6;
    println!("{}", x);
    x %= 3;
    println!("{}", x);
    let mut y: f64 = 1.5;
    y += 0.5;
    println!("{}", y);
}
```

### Match expressions

`match` on integers, strings, booleans. Supports wildcard `_`, or-patterns `1 | 2`, and `match` as an expression. No enum destructuring.

```rust
// match_basic.rs → "three"
fn main() {
    let x = 3;
    match x {
        1 => println!("one"),
        2 => println!("two"),
        3 => println!("three"),
        _ => println!("other"),
    }
}

// match_string.rs → "great"
fn main() {
    let lang = "rust";
    let rating = match lang {
        "rust" => "great",
        "python" => "good",
        _ => "ok",
    };
    println!("{}", rating);
}

// match_or_pattern.rs → "small"
fn main() {
    let x = 2;
    let result = match x {
        1 | 2 => "small",
        3 | 4 => "medium",
        _ => "large",
    };
    println!("{}", result);
}

// match_expr.rs → "zero" then "one" then "many" then "many" then "many"
fn main() {
    for i in 0..5 {
        let label = match i {
            0 => "zero",
            1 => "one",
            _ => "many",
        };
        println!("{}", label);
    }
}
```

### Structs and methods

Struct definitions, construction (with field initializers and shorthand), field access, and inherent `impl` blocks with methods. Associated functions (no `self` receiver) are called via `Type::method()`. Struct instances use move semantics.

```rust
// struct_basic.rs → "1.5" then "2.5"
struct Point {
    x: f64,
    y: f64,
}
fn main() {
    let p = Point { x: 1.5, y: 2.5 };
    println!("{}", p.x);
    println!("{}", p.y);
}

// struct_method.rs → "12" then "14"
struct Rect {
    w: f64,
    h: f64,
}
impl Rect {
    fn new(w: f64, h: f64) -> Rect {
        Rect { w: w, h: h }
    }
    fn area(&self) -> f64 {
        self.w * self.h
    }
    fn perimeter(&self) -> f64 {
        2.0 * (self.w + self.h)
    }
}
fn main() {
    let r = Rect::new(3.0, 4.0);
    println!("{}", r.area());
    println!("{}", r.perimeter());
}

// struct_mut.rs → "0" then "42"
struct Counter {
    value: i64,
}
impl Counter {
    fn new() -> Counter {
        Counter { value: 0 }
    }
}
fn main() {
    let mut c = Counter::new();
    println!("{}", c.value);
    c.value = 42;
    println!("{}", c.value);
}

// struct_move.rs → ClownMoveError
struct Data {
    value: i64,
}
fn main() {
    let a = Data { value: 10 };
    let b = a;
    println!("{}", b.value);
    println!("{}", a.value);
}
```

### Option type

Built-in `Option<T>` with `Some(x)` and `None`. Methods: `.unwrap()`, `.unwrap_or(default)`, `.is_some()`, `.is_none()`. The `?` operator propagates `None` via early return.

```rust
// option_basic.rs → "42" then "true" then "false" then "false" then "true" then "99"
fn main() {
    let a = Some(42);
    let b: Option<i64> = None;
    println!("{}", a.unwrap());
    println!("{}", a.is_some());
    println!("{}", a.is_none());
    println!("{}", b.is_some());
    println!("{}", b.is_none());
    println!("{}", b.unwrap_or(99));
}

// option_question_mark.rs → "14" then "true" then "true"
fn double_if_positive(x: i64) -> Option<i64> {
    if x <= 0 {
        return None;
    }
    Some(x * 2)
}
fn add_doubled(a: i64, b: i64) -> Option<i64> {
    let da = double_if_positive(a)?;
    let db = double_if_positive(b)?;
    Some(da + db)
}
fn main() {
    println!("{}", add_doubled(3, 4).unwrap());
    println!("{}", add_doubled(-1, 4).is_none());
    println!("{}", add_doubled(3, -2).is_none());
}

// option_unwrap_panic.rs → ClownRuntimeError
fn main() {
    let x: Option<i64> = None;
    let v = x.unwrap();
    println!("{}", v);
}
```
