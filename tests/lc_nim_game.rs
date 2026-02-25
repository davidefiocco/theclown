fn can_win_nim(n: i32) -> bool {
    n % 4 != 0
}

fn main() {
    println!("{}", can_win_nim(1));
    println!("{}", can_win_nim(4));
    println!("{}", can_win_nim(7));
}
