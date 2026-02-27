import subprocess
import pytest


THECLOWN = ["uv", "run", "python", "theclown.py"]


def run_theclown(rs_file, check=False):
    result = subprocess.run(
        [*THECLOWN, rs_file],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"Expected success but got:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def test_struct_empty():
    result = run_theclown("tests/struct_empty.rs", check=True)
    assert result.returncode == 0


def test_dump_ast():
    result = subprocess.run(
        [*THECLOWN, "--dump-ast", "tests/struct_empty.rs"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "(source_file" in result.stdout or "source_file" in result.stdout
    assert "struct_item" in result.stdout


def test_enum_color():
    result = run_theclown("tests/enum_color.rs", check=True)
    assert result.stdout.strip() == "green"


def test_enum_basic():
    result = run_theclown("tests/enum_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["up", "left"]


def test_enum_tuple_variant():
    result = run_theclown("tests/enum_tuple_variant.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["78.5", "12"]


def test_bouncer_trait():
    result = run_theclown("tests/bouncer_trait.rs")
    assert result.returncode != 0
    assert "trait_item" in result.stderr


def test_use_noop():
    result = run_theclown("tests/use_noop.rs", check=True)
    assert result.returncode == 0


def test_impl_standalone():
    result = run_theclown("tests/impl_standalone.rs", check=True)
    assert result.returncode == 0


def test_attribute_noop():
    result = run_theclown("tests/attribute_noop.rs", check=True)
    assert result.stdout.strip() == "42"


def test_ref_passthrough():
    result = run_theclown("tests/ref_passthrough.rs", check=True)
    assert result.stdout.strip() == "2"


def test_arith_precedence():
    result = run_theclown("tests/arith_precedence.rs", check=True)
    assert result.stdout.strip() == "7"


def test_arith_parens():
    result = run_theclown("tests/arith_parens.rs", check=True)
    assert result.stdout.strip() == "9"


def test_arith_subtract():
    result = run_theclown("tests/arith_subtract.rs", check=True)
    assert result.stdout.strip() == "7"


def test_let_variables():
    result = run_theclown("tests/let_variables.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines[0] == "6"
    assert lines[1] == "15"


def test_error_immutable():
    result = run_theclown("tests/error_immutable.rs")
    assert result.returncode != 0
    assert (
        "ClownMutabilityError" in result.stderr
        or "cannot assign to immutable" in result.stderr
    )


def test_let_type_annotation():
    result = run_theclown("tests/let_type_annotation.rs", check=True)
    assert result.stdout.strip() == "5"


def test_block_expr():
    result = run_theclown("tests/block_expr.rs", check=True)
    assert result.stdout.strip() == "6"


def test_error_scope():
    result = run_theclown("tests/error_scope.rs")
    assert result.returncode != 0
    assert "ClownNameError" in result.stderr or "cannot find value" in result.stderr


def test_if_basic():
    result = run_theclown("tests/if_basic.rs", check=True)
    assert result.stdout.strip() == "1"


def test_while_loop():
    result = run_theclown("tests/while_loop.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["5", "4", "3", "2", "1"]


def test_if_else_if():
    result = run_theclown("tests/if_else_if.rs", check=True)
    assert result.stdout.strip() == "2"


def test_fn_multiple():
    result = run_theclown("tests/fn_multiple.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines[0] == "7"
    assert lines[1] == "10"


def test_fn_return():
    result = run_theclown("tests/fn_return.rs", check=True)
    assert result.stdout.strip() == "42"


def test_move_primitives():
    result = run_theclown("tests/move_primitives.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines[0] == "10"
    assert lines[1] == "10"


def test_move_strings():
    result = run_theclown("tests/move_strings.rs")
    assert result.returncode != 0
    assert "ClownMoveError" in result.stderr or "use of moved value" in result.stderr


def test_fib_recursive():
    result = run_theclown("tests/fib_recursive.rs", check=True)
    assert result.stdout.strip() == "55"


def test_adversarial_div_zero():
    result = run_theclown("tests/adversarial_div_zero.rs")
    assert result.returncode != 0
    assert "ClownRuntimeError" in result.stderr or "division by zero" in result.stderr


def test_adversarial_mod_zero():
    result = run_theclown("tests/adversarial_mod_zero.rs")
    assert result.returncode != 0
    assert "ClownRuntimeError" in result.stderr or "modulo by zero" in result.stderr


def test_adversarial_uninitialized():
    result = run_theclown("tests/adversarial_uninitialized.rs")
    assert result.returncode != 0
    assert "ClownRuntimeError" in result.stderr or "uninitialized" in result.stderr


def test_adversarial_multi_arg():
    result = run_theclown("tests/adversarial_multi_arg.rs", check=True)
    assert result.stdout.strip() == "1 2"


def test_println_nested_parens():
    result = run_theclown("tests/println_nested_parens.rs", check=True)
    assert result.stdout.strip() == "21"


def test_println_unary():
    result = run_theclown("tests/println_unary.rs", check=True)
    assert result.stdout.strip() == "1"


def test_println_multi_args():
    result = run_theclown("tests/println_multi_args.rs", check=True)
    assert result.stdout.strip() == "3 7"


def test_println_call():
    result = run_theclown("tests/println_call.rs", check=True)
    assert result.stdout.strip() == "5"


def test_println_bool():
    result = run_theclown("tests/println_bool.rs", check=True)
    assert result.stdout.strip() == "true"


def test_if_false_side_effect():
    result = run_theclown("tests/if_false_side_effect.rs", check=True)
    assert result.stdout.strip() == "0"


def test_short_circuit():
    result = run_theclown("tests/short_circuit.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines[0] == "false"
    assert lines[1] == "true"


def test_neg_div():
    result = run_theclown("tests/neg_div.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines[0] == "-3"
    assert lines[1] == "-1"


def test_error_wrong_arity():
    result = run_theclown("tests/error_wrong_arity.rs")
    assert result.returncode != 0
    assert "ClownRuntimeError" in result.stderr or "expects 2 arguments" in result.stderr


def test_for_range():
    result = run_theclown("tests/for_range.rs", check=True)
    assert result.stdout.strip().split("\n") == ["0", "1", "2", "3", "4"]


def test_for_range_inclusive():
    result = run_theclown("tests/for_range_inclusive.rs", check=True)
    assert result.stdout.strip().split("\n") == ["1", "2", "3", "4", "5"]


def test_for_sum():
    result = run_theclown("tests/for_sum.rs", check=True)
    assert result.stdout.strip() == "5050"


def test_loop_break():
    result = run_theclown("tests/loop_break.rs", check=True)
    assert result.stdout.strip() == "3"


def test_loop_break_value():
    result = run_theclown("tests/loop_break_value.rs", check=True)
    assert result.stdout.strip() == "42"


def test_while_break():
    result = run_theclown("tests/while_break.rs", check=True)
    assert result.stdout.strip() == "5"


def test_while_continue():
    result = run_theclown("tests/while_continue.rs", check=True)
    assert result.stdout.strip().split("\n") == ["1", "3", "5", "7", "9"]


def test_println_capture():
    result = run_theclown("tests/println_capture.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["42", "hello world", "42 and world"]


def test_tuple_basic():
    result = run_theclown("tests/tuple_basic.rs", check=True)
    assert result.stdout.strip() == "1 2"


def test_tuple_swap():
    result = run_theclown("tests/tuple_swap.rs", check=True)
    assert result.stdout.strip() == "2 1"


def test_tuple_nested_expr():
    result = run_theclown("tests/tuple_nested_expr.rs", check=True)
    assert result.stdout.strip() == "3 12"


def test_lc_reverse_integer():
    result = run_theclown("tests/lc_reverse_integer.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["54321", "-321", "0"]


def test_lc_palindrome_number():
    result = run_theclown("tests/lc_palindrome_number.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["true", "false", "true"]


def test_lc_fizzbuzz():
    result = run_theclown("tests/lc_fizzbuzz.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == [
        "1", "2", "Fizz", "4", "Buzz",
        "Fizz", "7", "8", "Fizz", "Buzz",
        "11", "Fizz", "13", "14", "FizzBuzz",
    ]


def test_lc_power_of_two():
    result = run_theclown("tests/lc_power_of_two.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["true", "true", "false"]


def test_lc_climbing_stairs():
    result = run_theclown("tests/lc_climbing_stairs.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["2", "8", "89"]


def test_lc_factorial():
    result = run_theclown("tests/lc_factorial.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["1", "120", "3628800"]


def test_lc_gcd():
    result = run_theclown("tests/lc_gcd.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["4", "6", "1"]


def test_lc_count_digits():
    result = run_theclown("tests/lc_count_digits.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["1", "5", "3"]


def test_lc_sum_digits():
    result = run_theclown("tests/lc_sum_digits.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["15", "27", "0"]


def test_lc_is_prime():
    result = run_theclown("tests/lc_is_prime.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["false", "true", "true", "false"]


def test_lc_sqrt_integer():
    result = run_theclown("tests/lc_sqrt_integer.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["0", "2", "2", "10"]


def test_lc_power():
    result = run_theclown("tests/lc_power.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["1024", "243", "1"]


def test_lc_add_digits():
    result = run_theclown("tests/lc_add_digits.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["2", "0", "6"]


def test_lc_happy_number():
    result = run_theclown("tests/lc_happy_number.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["true", "false", "true"]


def test_lc_collatz():
    result = run_theclown("tests/lc_collatz.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["0", "8", "9"]


def test_lc_count_bits():
    result = run_theclown("tests/lc_count_bits.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["0", "3", "8"]


def test_lc_ugly_number():
    result = run_theclown("tests/lc_ugly_number.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["true", "true", "false", "true"]


def test_lc_trailing_zeroes():
    result = run_theclown("tests/lc_trailing_zeroes.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["1", "2", "6"]


def test_lc_nim_game():
    result = run_theclown("tests/lc_nim_game.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["true", "false", "true"]


def test_lc_tribonacci():
    result = run_theclown("tests/lc_tribonacci.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["0", "4", "149"]


def test_syntax_error():
    result = run_theclown("tests/syntax_error.rs")
    assert result.returncode != 0
    assert "ClownSyntaxError" in result.stderr
    assert "line" in result.stderr


def test_syntax_error_bare_if():
    result = run_theclown("tests/syntax_error_bare_if.rs")
    assert result.returncode != 0
    assert "ClownSyntaxError" in result.stderr
    assert "line 2" in result.stderr


def test_syntax_error_bad_fn():
    result = run_theclown("tests/syntax_error_bad_fn.rs")
    assert result.returncode != 0
    assert "ClownSyntaxError" in result.stderr
    assert "line 1" in result.stderr


def test_syntax_error_swapped_braces():
    result = run_theclown("tests/syntax_error_swapped_braces.rs")
    assert result.returncode != 0
    assert "ClownSyntaxError" in result.stderr
    assert "line 1" in result.stderr


def test_println_empty():
    result = run_theclown("tests/println_empty.rs", check=True)
    assert result.stdout == "\n"


def test_float_basic():
    result = run_theclown("tests/float_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["5.140000000000001", "6.28", "2"]


def test_float_division():
    result = run_theclown("tests/float_division.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["3.5", "1"]


def test_float_negation():
    result = run_theclown("tests/float_negation.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["-4.5", "4.5"]


def test_cast_basic():
    result = run_theclown("tests/cast_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["42", "3"]


def test_cast_println():
    result = run_theclown("tests/cast_println.rs", check=True)
    assert result.stdout.strip() == "25"


def test_cast_unsupported():
    result = run_theclown("tests/cast_unsupported.rs")
    assert result.returncode != 0
    assert "OutOfDepthError" in result.stderr
    assert "as char" in result.stderr


def test_math_methods():
    result = run_theclown("tests/math_methods.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["4", "3.5", "-4", "-3", "5"]


def test_math_scoped():
    result = run_theclown("tests/math_scoped.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["5", "7"]


def test_math_trig():
    result = run_theclown("tests/math_trig.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["0", "1", "1"]


def test_array_basic():
    result = run_theclown("tests/array_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["10", "30", "3"]


def test_array_mut():
    result = run_theclown("tests/array_mut.rs", check=True)
    assert result.stdout.strip() == "10 2 30"


def test_array_oob():
    result = run_theclown("tests/array_oob.rs")
    assert result.returncode != 0
    assert "ClownRuntimeError" in result.stderr
    assert "out of bounds" in result.stderr


def test_vec_macro():
    result = run_theclown("tests/vec_macro.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["3", "3"]


def test_vec_pop():
    result = run_theclown("tests/vec_pop.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["30", "2"]


def test_array_move():
    result = run_theclown("tests/array_move.rs")
    assert result.returncode != 0
    assert "ClownMoveError" in result.stderr or "use of moved value" in result.stderr


def test_const_basic():
    result = run_theclown("tests/const_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["100", "3.14"]


def test_compound_assign():
    result = run_theclown("tests/compound_assign.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["15", "12", "24", "4", "1", "2"]


def test_match_basic():
    result = run_theclown("tests/match_basic.rs", check=True)
    assert result.stdout.strip() == "three"


def test_match_string():
    result = run_theclown("tests/match_string.rs", check=True)
    assert result.stdout.strip() == "great"


def test_match_or_pattern():
    result = run_theclown("tests/match_or_pattern.rs", check=True)
    assert result.stdout.strip() == "small"


def test_match_expr():
    result = run_theclown("tests/match_expr.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["zero", "one", "many", "many", "many"]


def test_struct_basic():
    result = run_theclown("tests/struct_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["1.5", "2.5"]


def test_struct_method():
    result = run_theclown("tests/struct_method.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["12", "14"]


def test_struct_mut():
    result = run_theclown("tests/struct_mut.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["0", "42"]


def test_struct_move():
    result = run_theclown("tests/struct_move.rs")
    assert result.returncode != 0
    assert "ClownMoveError" in result.stderr or "use of moved value" in result.stderr


def test_option_basic():
    result = run_theclown("tests/option_basic.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["42", "true", "false", "false", "true", "99"]


def test_option_question_mark():
    result = run_theclown("tests/option_question_mark.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert lines == ["14", "true", "true"]


def test_option_unwrap_panic():
    result = run_theclown("tests/option_unwrap_panic.rs")
    assert result.returncode != 0
    assert "ClownRuntimeError" in result.stderr
    assert "None" in result.stderr


def test_fft_recursive():
    result = run_theclown("tests/fft_recursive.rs", check=True)
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 256
    assert lines[0] == "64 0"
    assert lines[128] == "0 0"
    assert lines[255] == "41.24162 40.24162"
