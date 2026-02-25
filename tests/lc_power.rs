fn power(base: i32, mut exp: i32) -> i32 {
    let mut result = 1;
    let mut b = base;
    while exp > 0 {
        if exp % 2 == 1 {
            result = result * b;
        }
        b = b * b;
        exp = exp / 2;
    }
    result
}

fn main() {
    println!("{}", power(2, 10));
    println!("{}", power(3, 5));
    println!("{}", power(7, 0));
}
