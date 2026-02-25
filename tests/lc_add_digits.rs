fn add_digits(mut n: i32) -> i32 {
    while n >= 10 {
        let mut sum = 0;
        while n > 0 {
            sum = sum + n % 10;
            n = n / 10;
        }
        n = sum;
    }
    n
}

fn main() {
    println!("{}", add_digits(38));
    println!("{}", add_digits(0));
    println!("{}", add_digits(123));
}
