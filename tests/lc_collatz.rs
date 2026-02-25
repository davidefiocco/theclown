fn collatz_steps(mut n: i32) -> i32 {
    let mut steps = 0;
    while n != 1 {
        if n % 2 == 0 {
            n = n / 2;
        } else {
            n = 3 * n + 1;
        }
        steps = steps + 1;
    }
    steps
}

fn main() {
    println!("{}", collatz_steps(1));
    println!("{}", collatz_steps(6));
    println!("{}", collatz_steps(12));
}
