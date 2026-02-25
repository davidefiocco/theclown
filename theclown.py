#!/usr/bin/env python3

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, TextIO, cast

from tree_sitter import Language, Parser, Node
import tree_sitter_rust


RUST = Language(tree_sitter_rust.language())
TREE_PARSER = Parser(RUST)


def dump_ast(node, indent: int = 0) -> None:
    prefix = "  " * indent
    print(f"{prefix}{node.type}")
    for child in node.children:
        dump_ast(child, indent + 1)


class ClownError(Exception):
    pass


class OutOfDepthError(ClownError):
    pass


class ClownMutabilityError(ClownError):
    pass


class ClownNameError(ClownError):
    pass


class ClownMoveError(ClownError):
    pass


class ClownSyntaxError(ClownError):
    pass


class ClownRuntimeError(ClownError):
    pass


class ReturnSignal(Exception):
    def __init__(self, value: Value):
        self.value = value
        super().__init__(str(value))


class BreakSignal(Exception):
    def __init__(self, value: Value = None):
        self.value = value
        super().__init__(str(value))


class ContinueSignal(Exception):
    pass


class _Tombstone:
    pass


Value = int | float | bool | str | list | tuple | range | None | _Tombstone
TOMBSTONE = _Tombstone()


@dataclass(frozen=True)
class FunctionDef:
    params: list[tuple[str, bool]]
    body: Node


class Environment:
    def __init__(self) -> None:
        self.scopes: list[dict[str, tuple[Value, bool]]] = [{}]

    def push_scope(self) -> None:
        self.scopes.append({})

    def pop_scope(self) -> None:
        self.scopes.pop()

    def get(self, name: str) -> tuple[Value, bool]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise ClownNameError(f"cannot find value `{name}` in this scope")

    def set(self, name: str, value: Value) -> None:
        for scope in reversed(self.scopes):
            if name in scope:
                _, mutable = scope[name]
                if not mutable:
                    raise ClownMutabilityError(
                        f"cannot assign to immutable variable `{name}`"
                    )
                scope[name] = (value, mutable)
                return
        raise ClownNameError(f"cannot find value `{name}` in this scope")

    def move(self, name: str) -> None:
        for scope in reversed(self.scopes):
            if name in scope:
                scope[name] = (TOMBSTONE, scope[name][1])
                return
        raise ClownNameError(f"cannot find value `{name}` in this scope")

    def define(self, name: str, value: Value, mutable: bool) -> None:
        self.scopes[-1][name] = (value, mutable)


class Interpreter:
    def __init__(self, stdout: TextIO = sys.stdout) -> None:
        self.stdout = stdout
        self.env = Environment()
        self.functions: dict[str, FunctionDef] = {}

    def evaluate(self, node: Node) -> Value:
        match node.type:
            case "source_file":
                for child in node.children:
                    if child.type == "function_item":
                        self._register_function(child)
                for child in node.children:
                    if child.type != "function_item":
                        self.evaluate(child)
                main_func = self.functions.get("main")
                if main_func:
                    self.call_func(main_func, [])
                return None

            case "function_item":
                return None

            case "block":
                self.env.push_scope()
                result: Value = None
                try:
                    children = [c for c in node.children if c.type not in ("{", "}")]
                    for child in children:
                        result = self.evaluate(child)
                    if children and children[-1].type == "expression_statement":
                        if any(c.type == ";" for c in children[-1].children):
                            return None
                    return result
                finally:
                    self.env.pop_scope()

            case "integer_literal":
                return int(self._node_text(node))

            case "float_literal":
                return float(self._node_text(node))

            case "boolean_literal":
                return self._node_text(node) == "true"

            case "string_literal":
                return self._string_value(node)

            case "binary_expression":
                left = self.evaluate(self._require_child(node, 0))
                op = self._node_text(self._require_child(node, 1))
                if op == "&&":
                    if not left:
                        return False
                    return bool(self.evaluate(self._require_child(node, 2)))
                if op == "||":
                    if left:
                        return True
                    return bool(self.evaluate(self._require_child(node, 2)))
                right = self.evaluate(self._require_child(node, 2))
                return self._apply_binary(op, left, right, node)

            case "unary_expression":
                op = self._node_text(self._require_child(node, 0))
                operand = self.evaluate(self._require_child(node, 1))
                return self._apply_unary(op, operand, node)

            case "type_cast_expression":
                value = self.evaluate(self._require_child(node, 0))
                target_type = self._node_text(self._require_child(node, 2))
                return self._apply_cast(value, target_type, node)

            case "parenthesized_expression":
                if len(node.children) < 2:
                    raise self._error(ClownRuntimeError, "invalid parenthesized expression", node)
                return self.evaluate(node.children[1])

            case "if_expression":
                condition_node = node.child_by_field_name("condition")
                consequence_node = node.child_by_field_name("consequence")
                if not condition_node or not consequence_node:
                    raise self._error(ClownRuntimeError, "invalid if expression", node)
                condition = self.evaluate(condition_node)
                if condition:
                    return self.evaluate(consequence_node)
                alternative = node.child_by_field_name("alternative")
                if alternative:
                    return self.evaluate(alternative)
                return None

            case "else_clause":
                for child in node.children:
                    if child.type in ("block", "if_expression"):
                        return self.evaluate(child)
                return None

            case "while_expression":
                condition_node = node.child_by_field_name("condition")
                if not condition_node:
                    raise self._error(ClownRuntimeError, "invalid while expression", node)
                body = node.child_by_field_name("body")
                try:
                    while self.evaluate(condition_node):
                        if body:
                            try:
                                self.evaluate(body)
                            except ContinueSignal:
                                continue
                except BreakSignal:
                    pass
                return None

            case "for_expression":
                return self._eval_for(node)

            case "loop_expression":
                body = node.child_by_field_name("body")
                if not body:
                    raise self._error(ClownRuntimeError, "invalid loop expression", node)
                try:
                    while True:
                        try:
                            self.evaluate(body)
                        except ContinueSignal:
                            continue
                except BreakSignal as sig:
                    return sig.value
                return None

            case "range_expression":
                children = [c for c in node.children if c.type not in ("..", "..=")]
                if len(children) != 2:
                    raise self._error(ClownRuntimeError, "invalid range expression", node)
                start = self.evaluate(children[0])
                end = self.evaluate(children[1])
                inclusive = any(c.type == "..=" for c in node.children)
                if inclusive:
                    return range(cast(int, start), cast(int, end) + 1)
                return range(cast(int, start), cast(int, end))

            case "break_expression":
                children = [c for c in node.children if c.type != "break"]
                if children:
                    raise BreakSignal(self.evaluate(children[0]))
                raise BreakSignal(None)

            case "continue_expression":
                raise ContinueSignal()

            case "macro_invocation":
                return self._eval_macro(node)

            case "let_declaration":
                return self._eval_let(node)

            case "identifier":
                return self._get_identifier(self._node_text(node))

            case "call_expression":
                func_name = node.child_by_field_name("function")
                if not func_name:
                    raise self._error(ClownRuntimeError, "invalid call expression", node)
                args_node = node.child_by_field_name("arguments")
                args: list[Value] = []
                if args_node:
                    for child in args_node.children:
                        if child.type not in ("(", ")", ","):
                            args.append(self.evaluate(child))
                if func_name.type == "field_expression":
                    return self._call_method(func_name, args, node)
                if func_name.type == "scoped_identifier":
                    method = self._node_text(
                        func_name.children[-1]
                    ) if func_name.children else self._node_text(func_name)
                    return self._call_math(method, args, node)
                name = self._node_text(func_name)
                func_def = self.functions.get(name)
                if not func_def:
                    raise self._error(
                        ClownNameError, f"cannot find function `{name}`", node
                    )
                return self.call_func(func_def, args, node)

            case "return_expression":
                value_node = node.child_by_field_name("value")
                if not value_node:
                    for child in node.children:
                        if child.type != "return":
                            value_node = child
                            break
                if value_node:
                    raise ReturnSignal(self.evaluate(value_node))
                raise ReturnSignal(None)

            case "assignment_expression":
                lhs = self._require_child(node, 0)
                value = self.evaluate(self._require_child(node, 2))
                if lhs.type == "index_expression":
                    arr_name = self._node_text(lhs.children[0])
                    idx = self.evaluate(lhs.children[2])
                    obj, _ = self.env.get(arr_name)
                    if not isinstance(obj, list):
                        raise self._error(
                            ClownRuntimeError, "index requires an array", node
                        )
                    if not isinstance(idx, int):
                        raise self._error(
                            ClownRuntimeError, "index must be an integer", node
                        )
                    if idx < 0 or idx >= len(obj):
                        raise self._error(
                            ClownRuntimeError,
                            f"index {idx} out of bounds for array of length {len(obj)}",
                            node,
                        )
                    obj[idx] = value
                else:
                    self.env.set(self._node_text(lhs), value)
                return None

            case "expression_statement":
                return self.evaluate(self._require_child(node, 0))

            case "tuple_expression":
                elements = [
                    self.evaluate(c)
                    for c in node.children
                    if c.type not in ("(", ")", ",")
                ]
                return tuple(elements)

            case "array_expression":
                elements = [
                    self.evaluate(c)
                    for c in node.children
                    if c.type not in ("[", "]", ",")
                ]
                return elements

            case "index_expression":
                obj = self.evaluate(node.children[0])
                idx = self.evaluate(node.children[2])
                if not isinstance(obj, list):
                    raise self._error(
                        ClownRuntimeError, "index requires an array", node
                    )
                if not isinstance(idx, int):
                    raise self._error(
                        ClownRuntimeError, "index must be an integer", node
                    )
                if idx < 0 or idx >= len(obj):
                    raise self._error(
                        ClownRuntimeError,
                        f"index {idx} out of bounds for array of length {len(obj)}",
                        node,
                    )
                return obj[idx]

            case (
                "line_comment"
                | "primitive_type"
                | "type_identifier"
                | "mutable_specifier"
            ):
                return None

            case "ERROR":
                line = node.start_point[0] + 1
                col = node.start_point[1] + 1
                text = self._node_text(node)
                snippet = repr(text) if len(text) <= 40 else repr(text[:40] + "...")
                raise ClownSyntaxError(
                    f"syntax error at line {line}, column {col} near {snippet}"
                )

            case _:
                raise self._error(
                    OutOfDepthError,
                    f"theclown doesn't understand {node.type} yet",
                    node,
                )

    def call_func(
        self, func_def: FunctionDef, args: list[Value], node: Node | None = None
    ) -> Value:
        if len(args) != len(func_def.params):
            raise self._error(ClownRuntimeError, 
                f"function expects {len(func_def.params)} arguments, got {len(args)}",
                node,
            )
        previous_env = self.env
        self.env = Environment()
        try:
            for (param_name, mutable), arg_value in zip(func_def.params, args):
                self.env.define(param_name, arg_value, mutable)
            try:
                return self.evaluate(func_def.body)
            except ReturnSignal as e:
                return e.value
        finally:
            self.env = previous_env

    def _call_method(
        self, field_expr: Node, args: list[Value], node: Node
    ) -> Value:
        obj_node = field_expr.children[0] if field_expr.children else None
        method_node = field_expr.child_by_field_name("field")
        if not obj_node or not method_node:
            raise self._error(ClownRuntimeError, "invalid method call", node)
        obj = self.evaluate(obj_node)
        method = self._node_text(method_node)
        if isinstance(obj, list):
            if method == "len":
                return len(obj)
            if method == "push":
                if len(args) != 1:
                    raise self._error(
                        ClownRuntimeError, ".push() expects 1 argument", node
                    )
                obj.append(args[0])
                return None
            if method == "pop":
                if not obj:
                    raise self._error(
                        ClownRuntimeError, ".pop() on empty array", node
                    )
                return obj.pop()
        return self._call_math(method, [obj] + args, node)

    def _call_math(
        self, method: str, args: list[Value], node: Node
    ) -> Value:
        fn = _MATH_METHODS.get(method)
        if not fn:
            raise self._error(
                OutOfDepthError,
                f"theclown doesn't understand method `{method}` yet",
                node,
            )
        try:
            return fn(*args)
        except (ValueError, TypeError) as exc:
            raise self._error(
                ClownRuntimeError, f"{method}() error: {exc}", node
            ) from exc

    def _register_function(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node)
        params_node = node.child_by_field_name("parameters")
        params: list[tuple[str, bool]] = []
        if params_node:
            for param in params_node.children:
                if param.type == "parameter":
                    param_name = param.child_by_field_name("pattern")
                    if param_name:
                        mutable = any(c.type == "mutable_specifier" for c in param.children)
                        params.append((self._node_text(param_name), mutable))
        body = node.child_by_field_name("body")
        if body:
            self.functions[name] = FunctionDef(params=params, body=body)

    def _string_value(self, node: Node) -> str:
        for child in node.children:
            if child.type == "string_content":
                return self._node_text(child)
        return self._node_text(node).strip('"')

    def _node_text(self, node: Node) -> str:
        return node.text.decode() if node.text else ""

    def _error(
        self, cls: type[ClownError], msg: str, node: Node | None = None
    ) -> ClownError:
        if node is not None:
            line = node.start_point[0] + 1
            return cls(f"{msg} (line {line})")
        return cls(msg)

    def _require_child(self, node: Node, index: int) -> Node:
        child = node.child(index)
        if not child:
            raise self._error(ClownRuntimeError, "invalid syntax", node)
        return child

    def _eval_for(self, node: Node) -> None:
        pattern = node.child_by_field_name("pattern")
        iterable_node = node.child_by_field_name("value")
        body = node.child_by_field_name("body")
        if not pattern or not iterable_node or not body:
            raise self._error(ClownRuntimeError, "invalid for expression", node)
        loop_var = self._node_text(pattern)
        iterable = self.evaluate(iterable_node)
        if not isinstance(iterable, range):
            raise self._error(ClownRuntimeError, "for loop requires a range", node)
        self.env.push_scope()
        try:
            self.env.define(loop_var, 0, True)
            try:
                for val in iterable:
                    self.env.set(loop_var, val)
                    try:
                        self.evaluate(body)
                    except ContinueSignal:
                        continue
            except BreakSignal:
                pass
        finally:
            self.env.pop_scope()
        return None

    def _rust_repr(self, value: Value) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            if value == int(value) and value.is_integer():
                return str(int(value))
            return repr(value)
        if value is None:
            return "()"
        if isinstance(value, tuple):
            inner = ", ".join(self._rust_repr(v) for v in value)
            return f"({inner})"
        if isinstance(value, list):
            inner = ", ".join(self._rust_repr(v) for v in value)
            return f"[{inner}]"
        return str(value)

    def _is_copy_type(self, value: Value) -> bool:
        return isinstance(value, (int, float, bool)) or value is None

    def _get_identifier(self, name: str) -> Value:
        value, _ = self.env.get(name)
        if value is TOMBSTONE:
            raise ClownMoveError(f"use of moved value: `{name}`")
        return value

    def _apply_binary(
        self, op: str, left: Value, right: Value, node: Node | None = None
    ) -> Value:
        lval = cast(Any, left)
        rval = cast(Any, right)
        match op:
            case "+":
                return lval + rval
            case "-":
                return lval - rval
            case "*":
                return lval * rval
            case "/":
                if right == 0:
                    raise self._error(ClownRuntimeError, "division by zero", node)
                if isinstance(left, float) or isinstance(right, float):
                    return lval / rval
                return int(lval / rval)
            case "%":
                if right == 0:
                    raise self._error(ClownRuntimeError, "modulo by zero", node)
                if isinstance(left, float) or isinstance(right, float):
                    import math
                    return math.fmod(lval, rval)
                return lval - rval * int(lval / rval)
            case "==":
                return left == right
            case "!=":
                return left != right
            case "<":
                return lval < rval
            case ">":
                return lval > rval
            case "<=":
                return lval <= rval
            case ">=":
                return lval >= rval
            case _:
                raise self._error(OutOfDepthError, f"unknown operator: {op}", node)

    def _apply_unary(
        self, op: str, operand: Value, node: Node | None = None
    ) -> Value:
        oval = cast(Any, operand)
        match op:
            case "-":
                return -oval
            case "!":
                return not oval
            case _:
                raise self._error(
                    OutOfDepthError, f"unknown unary operator: {op}", node
                )

    def _apply_cast(
        self, value: Value, target_type: str, node: Node | None = None
    ) -> Value:
        match target_type:
            case "f64" | "f32":
                return float(value)  # type: ignore[arg-type]
            case "i64" | "i32" | "i16" | "i8" | "u64" | "u32" | "u16" | "u8" | "isize" | "usize":
                return int(value)  # type: ignore[arg-type]
            case "bool":
                return bool(value)
            case _:
                raise self._error(
                    OutOfDepthError,
                    f"theclown doesn't understand `as {target_type}` yet",
                    node,
                )

    def _eval_let(self, node: Node) -> None:
        pattern = node.child_by_field_name("pattern")
        if not pattern:
            return None
        mutable = any(child.type == "mutable_specifier" for child in node.children)
        value_node = node.child_by_field_name("value")

        if pattern.type == "tuple_pattern":
            names = [
                self._node_text(c)
                for c in pattern.children
                if c.type == "identifier"
            ]
            if not value_node:
                raise self._error(ClownRuntimeError, "uninitialized let is not supported", node)
            value = self.evaluate(value_node)
            if not isinstance(value, tuple) or len(value) != len(names):
                raise self._error(ClownRuntimeError, "tuple destructuring length mismatch", node)
            for n, v in zip(names, value):
                self.env.define(n, v, mutable)
            return None

        if pattern.type != "identifier":
            return None
        name = self._node_text(pattern)
        value: Value = None
        if value_node:
            if value_node.type == "identifier":
                src_name = self._node_text(value_node)
                src_value, _ = self.env.get(src_name)
                if not self._is_copy_type(src_value):
                    self.env.move(src_name)
                value = src_value
            else:
                value = self.evaluate(value_node)
        else:
            raise self._error(ClownRuntimeError, "uninitialized let is not supported", node)
        self.env.define(name, value, mutable)
        return None

    def _eval_macro(self, node: Node) -> None:
        macro_name = node.child_by_field_name("macro")
        if not macro_name:
            return None
        name = self._node_text(macro_name)
        if name == "vec":
            token_tree = next(
                (c for c in node.children if c.type == "token_tree"), None
            )
            if not token_tree:
                return []
            children = token_tree.children
            if children and children[0].type == "[" and children[-1].type == "]":
                children = children[1:-1]
            chunks = self._split_args(children)
            return [self._eval_token_expr(chunk) for chunk in chunks]
        if name != "println":
            raise self._error(
                OutOfDepthError, f"theclown doesn't understand {name}! yet", node
            )
        token_tree = next(
            (c for c in node.children if c.type == "token_tree"), None
        )
        if not token_tree:
            raise self._error(ClownRuntimeError, "invalid println! invocation", node)
        args = self._split_args(token_tree.children)
        if not args:
            print("", file=self.stdout)
            return None
        fmt_tokens = args[0]
        if len(fmt_tokens) != 1 or fmt_tokens[0].type != "string_literal":
            raise self._error(ClownRuntimeError, 
                "println! requires a format string as first argument", node
            )
        format_str = self._string_value(fmt_tokens[0])
        args = args[1:]
        kwargs = {
            name: self._rust_repr(self._get_identifier(name))
            for name in re.findall(r"\{([a-zA-Z_]\w*)\}", format_str)
        }
        if not args and not kwargs:
            print(format_str, file=self.stdout)
            return None
        values = [self._rust_repr(self._eval_token_expr(arg)) for arg in args]
        try:
            output = format_str.format(*values, **kwargs)
        except Exception as exc:
            raise self._error(ClownRuntimeError, "println! format error", node) from exc
        print(output, file=self.stdout)
        return None

    def _split_args(self, children: list[Node]) -> list[list[Node]]:
        tokens = children
        if tokens and tokens[0].type == "(" and tokens[-1].type == ")":
            tokens = tokens[1:-1]
        args: list[list[Node]] = []
        current: list[Node] = []
        depth = 0
        for child in tokens:
            if child.type == "(":
                depth += 1
            elif child.type == ")":
                depth -= 1
            if child.type == "," and depth == 0:
                if current:
                    args.append(current)
                    current = []
                continue
            current.append(child)
        if current:
            args.append(current)
        return args

    def _eval_token_expr(self, nodes: list[Node]) -> Value:
        if not nodes:
            raise self._error(ClownRuntimeError, "println! expects valid arguments")
        stream = _TokenStream(nodes)
        result = self._parse_expression(stream, 0)
        if not stream.at_end():
            raise self._error(ClownRuntimeError, "println! expects valid arguments", nodes[0])
        return result

    def _parse_expression(self, stream: _TokenStream, min_prec: int) -> Value:
        left = self._parse_unary(stream)
        while True:
            token = stream.peek()
            if token and token.type == "as" and 7 >= min_prec:
                stream.next()
                type_token = stream.next()
                if not type_token or type_token.type != "primitive_type":
                    raise self._error(ClownRuntimeError, "println! expects valid arguments", token)
                left = self._apply_cast(left, self._node_text(type_token), token)
                continue
            if not token or token.type not in _BINARY_PRECEDENCE:
                break
            prec = _BINARY_PRECEDENCE[token.type]
            if prec < min_prec:
                break
            op_token = stream.next()
            if not op_token:
                raise self._error(ClownRuntimeError, "println! expects valid arguments", token)
            op = op_token.type
            right = self._parse_expression(stream, prec + 1)
            left = self._apply_binary(op, left, right, op_token)
        return left

    def _parse_unary(self, stream: _TokenStream) -> Value:
        token = stream.peek()
        if token and token.type in _UNARY_OPERATORS:
            op_token = stream.next()
            if not op_token:
                raise self._error(ClownRuntimeError, "println! expects valid arguments", token)
            op = op_token.type
            return self._apply_unary(op, self._parse_unary(stream), op_token)
        return self._parse_primary(stream)

    def _parse_primary(self, stream: _TokenStream) -> Value:
        token = stream.next()
        if not token:
            raise self._error(ClownRuntimeError, "println! expects valid arguments")
        if token.type == "integer_literal":
            return int(self._node_text(token))
        if token.type == "float_literal":
            return float(self._node_text(token))
        if token.type == "boolean_literal":
            return self._node_text(token) == "true"
        if token.type == "string_literal":
            return self._string_value(token)
        if token.type == "identifier":
            next_token = stream.peek()
            if next_token and next_token.type == ".":
                stream.next()
                method_token = stream.next()
                if not method_token:
                    raise self._error(ClownRuntimeError, "println! expects valid arguments", token)
                method_name = self._node_text(method_token)
                arg_tree = stream.peek()
                method_args: list[Value] = []
                if arg_tree and arg_tree.type == "token_tree":
                    stream.next()
                    method_args = self._eval_token_tree_args(arg_tree)
                obj = self._get_identifier(self._node_text(token))
                if isinstance(obj, list):
                    if method_name == "len":
                        return len(obj)
                    if method_name == "push":
                        obj.append(method_args[0] if method_args else None)
                        return None
                    if method_name == "pop":
                        return obj.pop() if obj else None
                return self._call_math(method_name, [obj] + method_args, token)
            if next_token and next_token.type == "token_tree":
                stream.next()
                tt_children = next_token.children
                if tt_children and tt_children[0].type == "[":
                    obj = self._get_identifier(self._node_text(token))
                    if not isinstance(obj, list):
                        raise self._error(ClownRuntimeError, "index requires an array", token)
                    idx_val = self._eval_token_expr(tt_children[1:-1])
                    if not isinstance(idx_val, int):
                        raise self._error(ClownRuntimeError, "index must be an integer", token)
                    if idx_val < 0 or idx_val >= len(obj):
                        raise self._error(ClownRuntimeError, f"index {idx_val} out of bounds for array of length {len(obj)}", token)
                    return obj[idx_val]
                args = self._eval_token_tree_args(next_token)
                func_def = self.functions.get(self._node_text(token))
                if not func_def:
                    raise self._error(
                        ClownNameError,
                        f"cannot find value `{self._node_text(token)}` in this scope",
                        token,
                    )
                return self.call_func(func_def, args, token)
            return self._get_identifier(self._node_text(token))
        if token.type == "token_tree":
            return self._eval_token_tree_expr(token)
        if token.type == "(":
            value = self._parse_expression(stream, 0)
            closing = stream.next()
            if not closing or closing.type != ")":
                raise self._error(ClownRuntimeError, "println! expects valid arguments", token)
            return value
        raise self._error(ClownRuntimeError, "println! expects valid arguments", token)

    def _eval_token_tree_expr(self, token_tree: Node) -> Value:
        children = token_tree.children
        if not children:
            raise self._error(ClownRuntimeError, "println! expects valid arguments", token_tree)
        if children[0].type == "(" and children[-1].type == ")":
            inner = children[1:-1]
        else:
            inner = children
        return self._eval_token_expr(inner)

    def _eval_token_tree_args(self, token_tree: Node) -> list[Value]:
        chunks = self._split_args(token_tree.children)
        return [self._eval_token_expr(chunk) for chunk in chunks]


class _TokenStream:
    def __init__(self, tokens: list[Node]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self):
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def next(self):
        if self.index >= len(self.tokens):
            return None
        token = self.tokens[self.index]
        self.index += 1
        return token

    def at_end(self) -> bool:
        return self.index >= len(self.tokens)


_BINARY_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "==": 3,
    "!=": 3,
    "<": 4,
    ">": 4,
    "<=": 4,
    ">=": 4,
    "+": 5,
    "-": 5,
    "*": 6,
    "/": 6,
    "%": 6,
}

_UNARY_OPERATORS = {"-", "!"}

_MATH_METHODS: dict[str, Callable[..., float]] = {
    "sqrt": math.sqrt,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "ln": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "powi": lambda x, n: x ** int(n),
    "powf": pow,
    "min": min,
    "max": max,
}


def main() -> None:
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument("--dump-ast", action="store_true")
    argparser.add_argument("file", type=argparse.FileType("r"))
    args = argparser.parse_args()

    source = args.file.read()
    args.file.close()

    tree = TREE_PARSER.parse(bytes(source, "utf8"))
    root = tree.root_node

    if args.dump_ast:
        dump_ast(root)
        return

    interpreter = Interpreter(stdout=sys.stdout)
    try:
        interpreter.evaluate(root)
    except ClownError as e:
        print(f"{e.__class__.__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
