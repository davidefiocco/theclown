#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, TextIO, cast

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


Value = int | bool | str | tuple | range | None | _Tombstone
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
                return self._apply_binary(op, left, right)

            case "unary_expression":
                op = self._node_text(self._require_child(node, 0))
                operand = self.evaluate(self._require_child(node, 1))
                return self._apply_unary(op, operand)

            case "parenthesized_expression":
                if len(node.children) < 2:
                    raise ClownRuntimeError("invalid parenthesized expression")
                return self.evaluate(node.children[1])

            case "if_expression":
                condition_node = node.child_by_field_name("condition")
                consequence_node = node.child_by_field_name("consequence")
                if not condition_node or not consequence_node:
                    raise ClownRuntimeError("invalid if expression")
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
                    raise ClownRuntimeError("invalid while expression")
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
                    raise ClownRuntimeError("invalid loop expression")
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
                    raise ClownRuntimeError("invalid range expression")
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
                    raise ClownRuntimeError("invalid call expression")
                name = self._node_text(func_name)
                func_def = self.functions.get(name)
                if not func_def:
                    raise ClownNameError(f"cannot find function `{name}`")
                args_node = node.child_by_field_name("arguments")
                args = []
                if args_node:
                    for child in args_node.children:
                        if child.type not in ("(", ")", ","):
                            args.append(self.evaluate(child))
                return self.call_func(func_def, args)

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
                name = self._node_text(self._require_child(node, 0))
                value = self.evaluate(self._require_child(node, 2))
                self.env.set(name, value)
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
                raise OutOfDepthError(f"theclown doesn't understand {node.type} yet")

    def call_func(self, func_def: FunctionDef, args: list[Value]) -> Value:
        if len(args) != len(func_def.params):
            raise ClownRuntimeError(
                f"function expects {len(func_def.params)} arguments, got {len(args)}"
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

    def _require_child(self, node: Node, index: int) -> Node:
        child = node.child(index)
        if not child:
            raise ClownRuntimeError("invalid syntax")
        return child

    def _eval_for(self, node: Node) -> None:
        pattern = node.child_by_field_name("pattern")
        iterable_node = node.child_by_field_name("value")
        body = node.child_by_field_name("body")
        if not pattern or not iterable_node or not body:
            raise ClownRuntimeError("invalid for expression")
        loop_var = self._node_text(pattern)
        iterable = self.evaluate(iterable_node)
        if not isinstance(iterable, range):
            raise ClownRuntimeError("for loop requires a range")
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
        if value is None:
            return "()"
        if isinstance(value, tuple):
            inner = ", ".join(self._rust_repr(v) for v in value)
            return f"({inner})"
        return str(value)

    def _is_copy_type(self, value: Value) -> bool:
        return isinstance(value, (int, bool)) or value is None

    def _get_identifier(self, name: str) -> Value:
        value, _ = self.env.get(name)
        if value is TOMBSTONE:
            raise ClownMoveError(f"use of moved value: `{name}`")
        return value

    def _apply_binary(self, op: str, left: Value, right: Value) -> Value:
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
                    raise ClownRuntimeError("division by zero")
                return int(lval / rval)
            case "%":
                if right == 0:
                    raise ClownRuntimeError("modulo by zero")
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
                raise OutOfDepthError(f"unknown operator: {op}")

    def _apply_unary(self, op: str, operand: Value) -> Value:
        oval = cast(Any, operand)
        match op:
            case "-":
                return -oval
            case "!":
                return not oval
            case _:
                raise OutOfDepthError(f"unknown unary operator: {op}")

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
                raise ClownRuntimeError("uninitialized let is not supported")
            value = self.evaluate(value_node)
            if not isinstance(value, tuple) or len(value) != len(names):
                raise ClownRuntimeError("tuple destructuring length mismatch")
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
            raise ClownRuntimeError("uninitialized let is not supported")
        self.env.define(name, value, mutable)
        return None

    def _eval_macro(self, node: Node) -> None:
        macro_name = node.child_by_field_name("macro")
        if not macro_name:
            return None
        name = self._node_text(macro_name)
        if name != "println":
            raise OutOfDepthError(
                f"theclown doesn't understand {name}! yet"
            )
        token_tree = node.children[2]
        if not token_tree or token_tree.type != "token_tree":
            return None
        children = token_tree.children
        string_literal = children[1]
        if string_literal.type != "string_literal":
            return None
        format_str = self._string_value(string_literal)
        args = self._split_args(children)
        if args and len(args[0]) == 1 and args[0][0].type == "string_literal":
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
            raise ClownRuntimeError("println! format error") from exc
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
            raise ClownRuntimeError("println! expects valid arguments")
        stream = _TokenStream(nodes)
        result = self._parse_expression(stream, 0)
        if not stream.at_end():
            raise ClownRuntimeError("println! expects valid arguments")
        return result

    def _parse_expression(self, stream: _TokenStream, min_prec: int) -> Value:
        left = self._parse_unary(stream)
        while True:
            token = stream.peek()
            if not token or token.type not in _BINARY_PRECEDENCE:
                break
            prec = _BINARY_PRECEDENCE[token.type]
            if prec < min_prec:
                break
            op_token = stream.next()
            if not op_token:
                raise ClownRuntimeError("println! expects valid arguments")
            op = op_token.type
            right = self._parse_expression(stream, prec + 1)
            left = self._apply_binary(op, left, right)
        return left

    def _parse_unary(self, stream: _TokenStream) -> Value:
        token = stream.peek()
        if token and token.type in _UNARY_OPERATORS:
            op_token = stream.next()
            if not op_token:
                raise ClownRuntimeError("println! expects valid arguments")
            op = op_token.type
            return self._apply_unary(op, self._parse_unary(stream))
        return self._parse_primary(stream)

    def _parse_primary(self, stream: _TokenStream) -> Value:
        token = stream.next()
        if not token:
            raise ClownRuntimeError("println! expects valid arguments")
        if token.type == "integer_literal":
            return int(self._node_text(token))
        if token.type == "boolean_literal":
            return self._node_text(token) == "true"
        if token.type == "string_literal":
            return self._string_value(token)
        if token.type == "identifier":
            next_token = stream.peek()
            if next_token and next_token.type == "token_tree":
                stream.next()
                args = self._eval_token_tree_args(next_token)
                func_def = self.functions.get(self._node_text(token))
                if not func_def:
                    raise ClownNameError(
                        f"cannot find value `{self._node_text(token)}` in this scope"
                    )
                return self.call_func(func_def, args)
            return self._get_identifier(self._node_text(token))
        if token.type == "token_tree":
            return self._eval_token_tree_expr(token)
        if token.type == "(":
            value = self._parse_expression(stream, 0)
            closing = stream.next()
            if not closing or closing.type != ")":
                raise ClownRuntimeError("println! expects valid arguments")
            return value
        raise ClownRuntimeError("println! expects valid arguments")

    def _eval_token_tree_expr(self, token_tree: Node) -> Value:
        children = token_tree.children
        if not children:
            raise ClownRuntimeError("println! expects valid arguments")
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
