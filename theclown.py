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


@dataclass
class StructInstance:
    type_name: str
    fields: dict[str, Any]


class _OptionNone:
    def __repr__(self) -> str:
        return "None"


@dataclass
class OptionSome:
    value: Any

    def __repr__(self) -> str:
        return f"Some({self.value!r})"


OPTION_NONE = _OptionNone()

Value = (
    int | float | bool | str | list | tuple | range
    | StructInstance | OptionSome | _OptionNone | None | _Tombstone
)
TOMBSTONE = _Tombstone()


@dataclass(frozen=True)
class FunctionDef:
    params: list[tuple[str, bool]]
    body: Node
    receiver: bool = False


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
        self.constants: dict[str, Value] = {}
        self.structs: dict[str, list[str]] = {}
        self.methods: dict[str, dict[str, FunctionDef]] = {}

    def evaluate(self, node: Node) -> Value:
        match node.type:
            case "source_file":
                _FIRST_PASS = ("function_item", "const_item", "struct_item", "impl_item")
                for child in node.children:
                    if child.type == "function_item":
                        self._register_function(child)
                    elif child.type == "const_item":
                        self._register_const(child)
                    elif child.type == "struct_item":
                        self._register_struct(child)
                    elif child.type == "impl_item":
                        self._register_impl(child)
                for child in node.children:
                    if child.type not in _FIRST_PASS:
                        self.evaluate(child)
                main_func = self.functions.get("main")
                if main_func:
                    self.call_func(main_func, [])
                return None

            case "function_item" | "const_item" | "struct_item" | "impl_item":
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

            case "match_expression":
                return self._eval_match(node)

            case "try_expression":
                inner = self.evaluate(self._require_child(node, 0))
                if isinstance(inner, _OptionNone):
                    raise ReturnSignal(OPTION_NONE)
                if isinstance(inner, OptionSome):
                    return inner.value
                raise self._error(
                    ClownRuntimeError,
                    "the `?` operator can only be applied to Option values",
                    node,
                )

            case "macro_invocation":
                return self._eval_macro(node)

            case "let_declaration":
                return self._eval_let(node)

            case "identifier" | "self":
                name = self._node_text(node)
                if name == "None":
                    return OPTION_NONE
                return self._get_identifier(name)

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
                    return self._call_scoped(func_name, args, node)
                name = self._node_text(func_name)
                if name == "Some":
                    if len(args) != 1:
                        raise self._error(
                            ClownRuntimeError, "Some() expects 1 argument", node
                        )
                    return OptionSome(args[0])
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
                self._assign_to(lhs, value, node)
                return None

            case "compound_assignment_expr":
                lhs = self._require_child(node, 0)
                op_text = self._node_text(self._require_child(node, 1))
                base_op = op_text[:-1]  # "+=" -> "+"
                rhs = self.evaluate(self._require_child(node, 2))
                old = self._read_lhs(lhs, node)
                new_val = self._apply_binary(base_op, old, rhs, node)
                self._assign_to(lhs, new_val, node)
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

            case "struct_expression":
                return self._eval_struct_expr(node)

            case "field_expression":
                obj = self.evaluate(node.children[0])
                field_node = node.child_by_field_name("field")
                if not field_node:
                    raise self._error(ClownRuntimeError, "invalid field access", node)
                field_name = self._node_text(field_node)
                if isinstance(obj, StructInstance):
                    if field_name not in obj.fields:
                        raise self._error(
                            ClownRuntimeError,
                            f"no field `{field_name}` on type `{obj.type_name}`",
                            node,
                        )
                    return obj.fields[field_name]
                raise self._error(
                    ClownRuntimeError, "field access on non-struct value", node
                )

            case "use_declaration":
                return None

            case (
                "line_comment"
                | "attribute_item"
                | "primitive_type"
                | "type_identifier"
                | "mutable_specifier"
                | "field_identifier"
                | "generic_type"
            ):
                return None

            case "reference_expression":
                for child in node.children:
                    if child.type not in ("&", "mutable_specifier"):
                        return self.evaluate(child)
                raise self._error(ClownRuntimeError, "invalid reference expression", node)

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
        if isinstance(obj, StructInstance):
            method_table = self.methods.get(obj.type_name, {})
            func_def = method_table.get(method)
            if func_def:
                return self._call_struct_method(func_def, obj, args, node)
        if isinstance(obj, (OptionSome, _OptionNone)):
            return self._call_option_method(obj, method, args, node)
        return self._call_math(method, [obj] + args, node)

    def _call_option_method(
        self, obj: OptionSome | _OptionNone, method: str,
        args: list[Value], node: Node,
    ) -> Value:
        match method:
            case "unwrap":
                if isinstance(obj, OptionSome):
                    return obj.value
                raise self._error(
                    ClownRuntimeError,
                    "called `Option::unwrap()` on a `None` value",
                    node,
                )
            case "unwrap_or":
                if len(args) != 1:
                    raise self._error(
                        ClownRuntimeError, ".unwrap_or() expects 1 argument", node
                    )
                if isinstance(obj, OptionSome):
                    return obj.value
                return args[0]
            case "is_some":
                return isinstance(obj, OptionSome)
            case "is_none":
                return isinstance(obj, _OptionNone)
            case _:
                raise self._error(
                    OutOfDepthError,
                    f"theclown doesn't understand Option method `{method}` yet",
                    node,
                )

    def _call_scoped(
        self, scoped_id: Node, args: list[Value], node: Node
    ) -> Value:
        parts = [
            self._node_text(c) for c in scoped_id.children if c.type != "::"
        ]
        if len(parts) == 2:
            type_name, method_name = parts
            method_table = self.methods.get(type_name, {})
            func_def = method_table.get(method_name)
            if func_def:
                if func_def.receiver:
                    raise self._error(
                        ClownRuntimeError,
                        f"`{type_name}::{method_name}` requires a receiver",
                        node,
                    )
                return self.call_func(func_def, args, node)
        method = self._node_text(
            scoped_id.children[-1]
        ) if scoped_id.children else self._node_text(scoped_id)
        return self._call_math(method, args, node)

    def _call_struct_method(
        self,
        func_def: FunctionDef,
        receiver: StructInstance,
        args: list[Value],
        node: Node,
    ) -> Value:
        if func_def.receiver:
            previous_env = self.env
            self.env = Environment()
            try:
                self.env.define("self", receiver, mutable=True)
                if len(args) != len(func_def.params):
                    raise self._error(
                        ClownRuntimeError,
                        f"method expects {len(func_def.params)} arguments, got {len(args)}",
                        node,
                    )
                for (pname, mutable), arg in zip(func_def.params, args):
                    self.env.define(pname, arg, mutable)
                try:
                    return self.evaluate(func_def.body)
                except ReturnSignal as e:
                    return e.value
            finally:
                self.env = previous_env
        return self.call_func(func_def, args, node)

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

    def _register_struct(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = self._node_text(name_node)
        fields: list[str] = []
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "field_declaration":
                    fname = child.child_by_field_name("name")
                    if fname:
                        fields.append(self._node_text(fname))
        self.structs[name] = fields

    def _register_impl(self, node: Node) -> None:
        type_node = node.child_by_field_name("type")
        if not type_node:
            return
        type_name = self._node_text(type_node)
        body = node.child_by_field_name("body")
        if not body:
            return
        if type_name not in self.methods:
            self.methods[type_name] = {}
        for child in body.children:
            if child.type == "function_item":
                fn_name_node = child.child_by_field_name("name")
                if not fn_name_node:
                    continue
                fn_name = self._node_text(fn_name_node)
                params_node = child.child_by_field_name("parameters")
                params: list[tuple[str, bool]] = []
                has_receiver = False
                if params_node:
                    for param in params_node.children:
                        if param.type == "self_parameter":
                            has_receiver = True
                            continue
                        if param.type == "parameter":
                            param_name = param.child_by_field_name("pattern")
                            if param_name:
                                mutable = any(
                                    c.type == "mutable_specifier"
                                    for c in param.children
                                )
                                params.append((self._node_text(param_name), mutable))
                fn_body = child.child_by_field_name("body")
                if fn_body:
                    self.methods[type_name][fn_name] = FunctionDef(
                        params=params, body=fn_body, receiver=has_receiver
                    )

    def _register_const(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if not name_node or not value_node:
            return
        name = self._node_text(name_node)
        value = self.evaluate(value_node)
        self.constants[name] = value

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
        if isinstance(value, StructInstance):
            fields = ", ".join(
                f"{k}: {self._rust_repr(v)}" for k, v in value.fields.items()
            )
            return f"{value.type_name} {{ {fields} }}"
        if isinstance(value, OptionSome):
            return f"Some({self._rust_repr(value.value)})"
        if isinstance(value, _OptionNone):
            return "None"
        return str(value)

    def _is_copy_type(self, value: Value) -> bool:
        return isinstance(value, (int, float, bool)) or value is None

    def _get_identifier(self, name: str) -> Value:
        try:
            value, _ = self.env.get(name)
        except ClownNameError:
            if name in self.constants:
                return self.constants[name]
            raise
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

    def _eval_struct_expr(self, node: Node) -> Value:
        name_node = node.child_by_field_name("name")
        if not name_node:
            raise self._error(ClownRuntimeError, "invalid struct expression", node)
        type_name = self._node_text(name_node)
        if type_name not in self.structs:
            raise self._error(
                ClownNameError, f"cannot find struct `{type_name}`", node
            )
        body = node.child_by_field_name("body")
        fields: dict[str, Value] = {}
        if body:
            for child in body.children:
                if child.type == "field_initializer":
                    fname_node = child.child_by_field_name("field")
                    val_node = child.child_by_field_name("value")
                    if fname_node and val_node:
                        fields[self._node_text(fname_node)] = self.evaluate(val_node)
                elif child.type == "shorthand_field_initializer":
                    fname = self._node_text(child).strip()
                    fields[fname] = self._get_identifier(fname)
        return StructInstance(type_name=type_name, fields=fields)

    def _eval_match(self, node: Node) -> Value:
        scrutinee_node = node.child_by_field_name("value")
        if not scrutinee_node:
            scrutinee_node = node.child(1)
        if not scrutinee_node:
            raise self._error(ClownRuntimeError, "invalid match expression", node)
        scrutinee = self.evaluate(scrutinee_node)

        match_body = node.child_by_field_name("body")
        if not match_body:
            raise self._error(ClownRuntimeError, "invalid match expression", node)

        for child in match_body.children:
            if child.type != "match_arm":
                continue
            pattern_node = next(
                (c for c in child.children if c.type == "match_pattern"), None
            )
            body_node = None
            past_arrow = False
            for c in child.children:
                if c.type == "=>":
                    past_arrow = True
                    continue
                if past_arrow and c.type not in (",",):
                    body_node = c
                    break
            if not pattern_node or not body_node:
                continue

            bindings: dict[str, Value] = {}
            if self._match_pattern(pattern_node, scrutinee, bindings):
                self.env.push_scope()
                try:
                    for bname, bval in bindings.items():
                        self.env.define(bname, bval, mutable=False)
                    return self.evaluate(body_node)
                finally:
                    self.env.pop_scope()

        raise self._error(
            ClownRuntimeError, "non-exhaustive match expression", node
        )

    def _match_pattern(
        self, pattern: Node, value: Value, bindings: dict[str, Value]
    ) -> bool:
        children = [
            c for c in pattern.children
            if c.type not in ("(", ")", ",", "|")
        ]

        if any(c.type == "|" for c in pattern.children):
            alternatives: list[list[Node]] = []
            current: list[Node] = []
            for c in pattern.children:
                if c.type == "|":
                    if current:
                        alternatives.append(current)
                        current = []
                else:
                    current.append(c)
            if current:
                alternatives.append(current)
            for alt in alternatives:
                if len(alt) == 1 and self._match_single(alt[0], value, bindings):
                    return True
            return False

        if len(children) == 1:
            return self._match_single(children[0], value, bindings)

        if isinstance(value, tuple) and len(children) == len(value):
            for child, elem in zip(children, value):
                if not self._match_single(child, elem, bindings):
                    return False
            return True

        return False

    def _match_single(
        self, node: Node, value: Value, bindings: dict[str, Value]
    ) -> bool:
        if node.type == "_":
            return True
        if node.type == "integer_literal":
            return value == int(self._node_text(node))
        if node.type == "float_literal":
            return value == float(self._node_text(node))
        if node.type == "boolean_literal":
            return value == (self._node_text(node) == "true")
        if node.type == "string_literal":
            return value == self._string_value(node)
        if node.type == "negative_literal":
            inner = node.children[-1] if node.children else node
            if inner.type == "integer_literal":
                return value == -int(self._node_text(inner))
            if inner.type == "float_literal":
                return value == -float(self._node_text(inner))
        if node.type == "or_pattern":
            for child in node.children:
                if child.type != "|" and self._match_single(child, value, bindings):
                    return True
            return False
        if node.type == "tuple_pattern":
            elems = [c for c in node.children if c.type not in ("(", ")", ",")]
            if isinstance(value, tuple) and len(elems) == len(value):
                for child, elem in zip(elems, value):
                    if not self._match_single(child, elem, bindings):
                        return False
                return True
            return False
        if node.type == "identifier":
            bindings[self._node_text(node)] = value
            return True
        if node.type == "match_pattern":
            return self._match_pattern(node, value, bindings)
        return False

    def _assign_to(self, lhs: Node, value: Value, node: Node) -> None:
        if lhs.type == "index_expression":
            arr_name = self._node_text(lhs.children[0])
            idx = self.evaluate(lhs.children[2])
            obj, _ = self.env.get(arr_name)
            if not isinstance(obj, list):
                raise self._error(ClownRuntimeError, "index requires an array", node)
            if not isinstance(idx, int):
                raise self._error(ClownRuntimeError, "index must be an integer", node)
            if idx < 0 or idx >= len(obj):
                raise self._error(
                    ClownRuntimeError,
                    f"index {idx} out of bounds for array of length {len(obj)}",
                    node,
                )
            obj[idx] = value
        elif lhs.type == "field_expression":
            obj = self.evaluate(lhs.children[0])
            field_node = lhs.child_by_field_name("field")
            if not field_node or not isinstance(obj, StructInstance):
                raise self._error(
                    ClownRuntimeError, "field assignment on non-struct", node
                )
            fname = self._node_text(field_node)
            if fname not in obj.fields:
                raise self._error(
                    ClownRuntimeError,
                    f"no field `{fname}` on type `{obj.type_name}`",
                    node,
                )
            obj.fields[fname] = value
        else:
            self.env.set(self._node_text(lhs), value)

    def _read_lhs(self, lhs: Node, node: Node) -> Value:
        if lhs.type == "index_expression":
            obj = self.evaluate(lhs.children[0])
            idx = self.evaluate(lhs.children[2])
            if not isinstance(obj, list):
                raise self._error(ClownRuntimeError, "index requires an array", node)
            if not isinstance(idx, int):
                raise self._error(ClownRuntimeError, "index must be an integer", node)
            if idx < 0 or idx >= len(obj):
                raise self._error(
                    ClownRuntimeError,
                    f"index {idx} out of bounds for array of length {len(obj)}",
                    node,
                )
            return obj[idx]
        if lhs.type == "field_expression":
            return self.evaluate(lhs)
        return self._get_identifier(self._node_text(lhs))

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
            if (
                value_node.type == "identifier"
                and self._node_text(value_node) != "None"
            ):
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

    def _eval_macro(self, node: Node) -> Value:
        macro_name = node.child_by_field_name("macro")
        if not macro_name:
            return None
        name = self._node_text(macro_name)
        token_tree = next(
            (c for c in node.children if c.type == "token_tree"), None
        )
        if name == "vec":
            if not token_tree:
                return []
            arg_texts = self._macro_arg_texts(token_tree)
            return [self.evaluate(self._reparse_expr(t)) for t in arg_texts]
        if name != "println":
            raise self._error(
                OutOfDepthError, f"theclown doesn't understand {name}! yet", node
            )
        if not token_tree:
            raise self._error(ClownRuntimeError, "invalid println! invocation", node)
        arg_texts = self._macro_arg_texts(token_tree)
        if not arg_texts:
            print("", file=self.stdout)
            return None
        fmt_node = self._reparse_expr(arg_texts[0])
        if not fmt_node or fmt_node.type != "string_literal":
            raise self._error(ClownRuntimeError,
                "println! requires a format string as first argument", node)
        format_str = self._string_value(fmt_node)
        expr_args = arg_texts[1:]
        kwargs = {
            n: self._rust_repr(self._get_identifier(n))
            for n in re.findall(r"\{([a-zA-Z_]\w*)\}", format_str)
        }
        if not expr_args and not kwargs:
            print(format_str, file=self.stdout)
            return None
        values = [
            self._rust_repr(self.evaluate(self._reparse_expr(t)))
            for t in expr_args
        ]
        try:
            output = format_str.format(*values, **kwargs)
        except Exception as exc:
            raise self._error(ClownRuntimeError, "println! format error", node) from exc
        print(output, file=self.stdout)
        return None

    def _reparse_expr(self, text: str) -> Node:
        wrapper = f"fn _() {{ let _ = {text}; }}"
        tree = TREE_PARSER.parse(bytes(wrapper, "utf8"))
        func = tree.root_node.children[0]
        block = next(c for c in func.children if c.type == "block")
        let_decl = next(c for c in block.children if c.type == "let_declaration")
        value = let_decl.child_by_field_name("value")
        if not value:
            raise ClownRuntimeError(f"failed to parse expression: {text}")
        return value

    def _macro_arg_texts(self, token_tree: Node) -> list[str]:
        children = token_tree.children
        if not children:
            return []
        if children[0].type in ("(", "[") and children[-1].type in (")", "]"):
            children = children[1:-1]
        groups: list[list[Node]] = []
        current: list[Node] = []
        depth = 0
        for child in children:
            if child.type in ("(", "["):
                depth += 1
            elif child.type in (")", "]"):
                depth -= 1
            if child.type == "," and depth == 0:
                if current:
                    groups.append(current)
                    current = []
                continue
            current.append(child)
        if current:
            groups.append(current)
        source = token_tree.text
        if not source:
            return []
        base = token_tree.start_byte
        return [
            source[g[0].start_byte - base : g[-1].end_byte - base].decode()
            for g in groups
        ]


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
