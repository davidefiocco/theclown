fn factorial(n: i32) -> i32 {
    if n <= 1 {
        1
    } else {
        n * factorial(n - 1)
    }
}

fn main() {
    println!("{}", factorial(0));
    println!("{}", factorial(5));
    println!("{}", factorial(10));
}
